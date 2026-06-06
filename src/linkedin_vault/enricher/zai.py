"""
z.ai LLM provider — OpenAI-compatible REST API.

z.ai exposes the same chat-completions and models endpoints as OpenAI, so we
use ``httpx`` directly rather than the OpenAI SDK to keep the dependency tree
minimal.
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

_TIMEOUT = 30.0

# Fallback list used when the /models endpoint is unavailable.
ZAI_KNOWN_MODELS: list[str] = [
    "glm-4",
    "glm-4-flash",
    "glm-4-air",
    "glm-4-airx",
    "glm-3-turbo",
    "glm-4-long",
]


class ZAIProvider(BaseLLMProvider):
    """z.ai provider (https://api.z.ai/v1)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.z.ai/v1",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # BaseLLMProvider interface
    # ------------------------------------------------------------------

    async def list_models(self) -> list[str]:
        """Return available model IDs.

        Falls back to :data:`ZAI_KNOWN_MODELS` on any error so that callers
        can still present a sensible list even when the API is unreachable.
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if response.status_code >= 400:
                    raise LLMProviderError(f"HTTP {response.status_code} from z.ai /models")
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            _logger.debug("z.ai /models request failed; returning built-in model list.")
            return list(ZAI_KNOWN_MODELS)

    async def enrich_post(
        self,
        content: str,
        author_name: str,
        post_date: str | None,
        model: str,
        today: str,
    ) -> EnrichmentResult:
        """Call z.ai chat/completions and parse the structured JSON response.

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
            "temperature": 0.3,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        async def _attempt() -> EnrichmentResult:
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    response = await client.post(url, json=payload, headers=headers)
            except httpx.TimeoutException as exc:
                raise TransientLLMError(f"z.ai request timed out: {exc}") from exc

            if response.status_code in RETRYABLE_STATUS_CODES:
                raise TransientLLMError(
                    f"Transient HTTP {response.status_code} from z.ai"
                )
            if response.status_code >= 400:
                raise LLMProviderError(
                    f"HTTP {response.status_code} from z.ai: {response.text[:200]}"
                )

            raw_content: str = response.json()["choices"][0]["message"]["content"]
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
                        "z.ai transient error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc
