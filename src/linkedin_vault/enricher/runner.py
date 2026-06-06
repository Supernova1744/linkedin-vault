"""
Enrichment orchestration — ties together the LLM provider, the database, and
per-post error handling.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from linkedin_vault.config import Settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.enricher.factory import get_provider
from linkedin_vault.utils.logging import get_logger

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentRunResult:
    """Summary statistics from a completed enrichment run."""

    enriched: int
    """Number of posts successfully enriched during this run."""

    skipped_already_enriched: int
    """Number of posts that were already enriched and therefore not touched
    (only non-zero when ``re_enrich=False``)."""

    failed: int
    """Number of posts where LLM enrichment raised an error."""

    duration_seconds: float
    """Wall-clock time for the full enrichment run, in seconds."""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_enrichment(
    settings: Settings,
    db: DatabaseManager,
    limit: int | None = None,
    re_enrich: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> EnrichmentRunResult:
    """Run the LLM enrichment pipeline.

    Steps:
    1. Initialise the database.
    2. Fetch posts that need enrichment (``enriched_at IS NULL`` unless
       ``re_enrich=True``).
    3. For each post: call the configured LLM provider, write results to DB.
    4. Sleep ``enrich_delay_seconds`` between posts to respect rate limits.
    5. Return an :class:`EnrichmentRunResult` with counts and duration.

    Args:
        settings:          Application settings (provider, model, delay).
        db:                Initialised (or uninitialised) :class:`DatabaseManager`.
        limit:             Maximum number of posts to process.  ``None`` = all.
        re_enrich:         If ``True``, re-process posts that are already enriched.
        progress_callback: Optional ``(current, total)`` callback invoked after
                           each post is processed (success or failure).

    Returns:
        An :class:`EnrichmentRunResult` describing the outcome.
    """
    await db.initialize_db()
    start = time.monotonic()

    provider = get_provider(settings)
    model = settings.llm_model
    today = datetime.now(UTC).date().isoformat()

    # Fetch the count of already-enriched posts *before* we start so we can
    # report a meaningful skipped count rather than leaving it at zero.
    stats = await db.get_stats()
    skipped_already_enriched = stats.enriched_posts if not re_enrich else 0

    posts = await db.get_posts_for_enrichment(re_enrich=re_enrich, limit=limit)
    total = len(posts)

    _logger.info(
        "Starting enrichment: model=%r, posts_to_process=%d, re_enrich=%s",
        model,
        total,
        re_enrich,
    )

    enriched = 0
    failed = 0

    for i, post in enumerate(posts):
        if progress_callback is not None:
            progress_callback(i, total)

        assert post.id is not None, f"Post missing DB id: {post.linkedin_id}"

        try:
            result = await provider.enrich_post(
                content=post.content,
                author_name=post.author_name,
                post_date=post.post_date,
                model=model,
                today=today,
            )
            await db.update_post_enrichment(
                post_id=post.id,
                summary=result.summary,
                tags=result.tags,
                importance_score=result.importance_score,
                is_outdated=result.is_outdated,
                enrichment_model=result.model_used,
            )
            enriched += 1
            _logger.debug(
                "Enriched post id=%d by %s (score=%.1f, tags=%s)",
                post.id,
                post.author_name,
                result.importance_score,
                result.tags,
            )
        except Exception as exc:
            failed += 1
            _logger.error(
                "Failed to enrich post id=%d (%s): %s",
                post.id,
                post.author_name,
                exc,
                exc_info=True,
            )

        # Rate-limit: sleep between posts (skip delay after the last one)
        if i < total - 1 and settings.enrich_delay_seconds > 0:
            await asyncio.sleep(settings.enrich_delay_seconds)

    # Final progress tick
    if progress_callback is not None:
        progress_callback(total, total)

    duration = time.monotonic() - start

    _logger.info(
        "Enrichment complete in %.1fs — enriched: %d, skipped: %d, failed: %d",
        duration,
        enriched,
        skipped_already_enriched,
        failed,
    )

    return EnrichmentRunResult(
        enriched=enriched,
        skipped_already_enriched=skipped_already_enriched,
        failed=failed,
        duration_seconds=duration,
    )
