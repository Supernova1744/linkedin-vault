"""
Scrape orchestration — ties together browser session, extraction, and DB persistence.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from linkedin_vault.config import Settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.scraper.browser import linkedin_browser_session, scroll_and_extract_raw_posts
from linkedin_vault.scraper.parser import raw_post_to_model
from linkedin_vault.utils.logging import get_logger

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ScrapeResult:
    """Summary statistics from a completed scrape run."""

    new_posts: int
    """Number of posts newly inserted into the database."""

    skipped_existing: int
    """Number of posts skipped because a matching ``linkedin_id`` was already
    in the database (incremental sync boundary hit)."""

    failed_extractions: int
    """Number of post elements that could not be converted to a valid Post
    (missing required fields or unextractable linkedin_id)."""

    duration_seconds: float
    """Wall-clock time for the full scrape, in seconds."""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_scrape(
    settings: Settings,
    db: DatabaseManager,
    headless: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ScrapeResult:
    """Run a full scrape pipeline.

    Steps:
    1. Ensure the database is initialised.
    2. Load an existing browser session (``~/.linkedin-vault/session.json`` by
       default) or perform a manual login.
    3. Navigate to the LinkedIn Saved Posts feed.
    4. Scroll and extract posts one at a time.
    5. For each extracted post:
       - If ``linkedin_id`` already exists in the DB → stop (incremental sync).
       - Otherwise, upsert the post.
    6. Persist the session and update ``sync_state``.
    7. Return a :class:`ScrapeResult` with counts and duration.

    Args:
        settings: Application settings (used for ``data_dir`` and session path).
        db: Initialised (or uninitialised) :class:`DatabaseManager`.
        headless: Whether to run the browser headlessly.  Defaults to ``False``
            so the user can interact for login.
        progress_callback: Optional ``(new_posts, total_processed)`` callback
            invoked after each successfully upserted post.  Useful for live
            progress displays.

    Returns:
        A :class:`ScrapeResult` describing the outcome.
    """
    await db.initialize_db()

    session_path = settings.data_dir / "session.json"
    scraped_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_posts = 0
    skipped_existing = 0
    failed_extractions = 0

    start = time.monotonic()

    try:
        async with linkedin_browser_session(session_path, headless=headless) as page:
            async for raw_post in scroll_and_extract_raw_posts(page):
                # Convert raw DOM data → Post model
                post = raw_post_to_model(raw_post, scraped_at)

                if post is None:
                    failed_extractions += 1
                    _logger.debug(
                        "Skipping unextractable post (url=%r).", raw_post.url
                    )
                    continue

                # Incremental sync: stop at the first post already in the DB.
                # LinkedIn's Saved Posts feed is LIFO — oldest saves appear last —
                # so the first DB hit means everything that follows is already stored.
                existing = await db.get_post_by_linkedin_id(post.linkedin_id)
                if existing is not None:
                    skipped_existing += 1
                    _logger.info(
                        "Reached already-stored post %s — stopping incremental sync.",
                        post.linkedin_id,
                    )
                    break

                await db.upsert_post(post)
                new_posts += 1
                _logger.debug("Saved new post: %s by %s", post.linkedin_id, post.author_name)

                if progress_callback is not None:
                    total_processed = new_posts + skipped_existing + failed_extractions
                    progress_callback(new_posts, total_processed)

    except Exception as exc:
        _logger.error("Scrape failed with an unexpected error: %s", exc, exc_info=True)
        # Still fall through to update sync state with whatever was collected

    duration = time.monotonic() - start

    # Update sync state even on partial success
    try:
        sync = await db.get_sync_state()
        await db.update_sync_state(
            last_scraped_at=scraped_at,
            total_posts_scraped=sync.total_posts_scraped + new_posts,
            last_sync_duration_seconds=duration,
        )
    except Exception as exc:
        _logger.warning("Failed to update sync state: %s", exc)

    _logger.info(
        "Scrape complete in %.1fs — new: %d, skipped: %d, failed: %d",
        duration,
        new_posts,
        skipped_existing,
        failed_extractions,
    )

    return ScrapeResult(
        new_posts=new_posts,
        skipped_existing=skipped_existing,
        failed_extractions=failed_extractions,
        duration_seconds=duration,
    )
