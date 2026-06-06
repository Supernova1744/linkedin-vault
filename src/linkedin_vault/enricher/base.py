"""
Abstract base for LLM enrichment providers.

Defines the shared exception hierarchy, the per-post result dataclass, retry
constants, and the abstract interface that every concrete provider must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMProviderError(Exception):
    """Raised when an LLM provider encounters an unrecoverable error."""


class TransientLLMError(LLMProviderError):
    """Raised by provider implementations for retryable HTTP errors (429, 502, 503)
    and network timeouts so the retry loop can distinguish them from hard failures."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentResult:
    """Per-post enrichment result from an LLM analysis."""

    summary: str
    tags: list[str]
    importance_score: float  # 0.0 - 10.0
    is_outdated: bool
    model_used: str  # e.g. "glm-4-flash" or "llama3.2"


# ---------------------------------------------------------------------------
# Retry constants (used by concrete providers)
# ---------------------------------------------------------------------------

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 502, 503})
MAX_RETRIES: int = 3
BASE_BACKOFF_SECONDS: float = 1.0

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseLLMProvider(ABC):
    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return available model names for this provider."""

    @abstractmethod
    async def enrich_post(
        self,
        content: str,
        author_name: str,
        post_date: str | None,
        model: str,
        today: str,  # ISO-8601 date string e.g. "2026-06-06"
    ) -> EnrichmentResult:
        """Analyse a single post and return enrichment fields."""
