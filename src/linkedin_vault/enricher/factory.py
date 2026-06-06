"""
Provider factory — maps Settings.llm_provider to the concrete implementation.
"""

from __future__ import annotations

from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.enricher.base import BaseLLMProvider


def get_provider(settings: Settings) -> BaseLLMProvider:
    """Return the correct :class:`BaseLLMProvider` instance for the current settings.

    Args:
        settings: Application settings containing ``llm_provider``, ``zai_api_key``,
                  ``zai_base_url``, and ``ollama_base_url``.

    Returns:
        A concrete provider ready for use.

    Raises:
        ValueError: if ``settings.llm_provider`` is not recognised.
    """
    if settings.llm_provider == LLMProvider.ZAI:
        from linkedin_vault.enricher.zai import ZAIProvider

        return ZAIProvider(api_key=settings.zai_api_key, base_url=settings.zai_base_url)

    if settings.llm_provider == LLMProvider.OLLAMA:
        from linkedin_vault.enricher.ollama import OllamaProvider

        return OllamaProvider(base_url=settings.ollama_base_url)

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")
