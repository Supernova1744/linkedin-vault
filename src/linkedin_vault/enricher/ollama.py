"""
Ollama provider — local LLM inference via the Ollama REST API.

Ollama exposes a mostly OpenAI-compatible interface at http://localhost:11434.
We use the native /api/chat and /api/tags endpoints rather than the OpenAI
compatibility shim to get reliable streaming control.
"""

from __future__ import annotations

import asyncio

import httpx

from linkedin_vault.enricher.base import (
    BASE_BACKOFF_SECONDS,
    MAX_RETRIES,
    RETRYABLE_STATUS_CODES,
    BaseLLMProvider,
    EnrichmentResult,
    LLMProviderError,
    TransientLLMError,
)
from linkedin_vault.enricher.prompt import (
    SYSTEM_PROMPT,
    build_enrichment_prompt,
    parse_enrichment_response,
)
from linkedin_vault.utils.logging import get_logger

_logger = get_logger(__name__)

_TIMEOUT = 120.0  # Local models can be slow; allow a generous timeout.


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """Return locally available Ollama model names.

        Raises:
            LLMProviderError: if Ollama is not reachable at the configured URL.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
        except httpx.ConnectError as exc:
            raise LLMProviderError(f"Ollama is not running at {self._base_url}") from exc
        except httpx.TimeoutException as exc:
            raise LLMProviderError(f"Ollama did not respond at {self._base_url}: {exc}") from exc

        if response.status_code >= 400:
            raise LLMProviderError(f"HTTP {response.status_code} from Ollama /api/tags")

        data = response.json()
        return [m["name"] for m in data.get("models", [])]

    async def enrich_post(
        self,
        content: str,
        author_name: str,
        post_date: str | None,
        model: str,
        today: str,
    ) -> EnrichmentResult:
        """Call Ollama /api/chat and parse the structured JSON response.

        Retries up to :data:`MAX_RETRIES` times on transient HTTP errors
        (429, 502, 503) with exponential back-off.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_enrichment_prompt(content, author_name, post_date, today),
            },
        ]
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        url = f"{self._base_url}/api/chat"

        async def _attempt() -> EnrichmentResult:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.post(url, json=payload)
            except httpx.ConnectError as exc:
                raise LLMProviderError(f"Ollama is not running at {self._base_url}") from exc
            except httpx.TimeoutException as exc:
                raise TransientLLMError(f"Ollama request timed out: {exc}") from exc

            if response.status_code in RETRYABLE_STATUS_CODES:
                raise TransientLLMError(f"Transient HTTP {response.status_code} from Ollama")
            if response.status_code >= 400:
                raise LLMProviderError(
                    f"HTTP {response.status_code} from Ollama: {response.text[:200]}"
                )

            raw_content: str = response.json()["message"]["content"]
            result = parse_enrichment_response(raw_content)
            result.model_used = model
            return result

        last_exc: TransientLLMError | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return await _attempt()
            except TransientLLMError as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    delay = BASE_BACKOFF_SECONDS * (2**attempt)
                    _logger.warning(
                        "Ollama transient error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc
