"""
Scrape orchestration — ties together browser session, extraction, and DB persistence.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from linkedin_vault.config import Settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.scraper.browser import (
    LinkedInSessionExpiredError,
    linkedin_browser_session,
    scroll_and_extract_raw_posts,
)
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

    scrape_mode: Literal["fast_incremental", "full_scan"] = field(default="full_scan")
    """Scraping strategy used for this run.

    ``fast_incremental``: vault was previously complete — stop at the first
    duplicate post (LIFO boundary).  ``full_scan``: previous scrape was
    incomplete — scan the entire feed to recover any orphaned posts.
    """


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def run_scrape(
    settings: Settings,
    db: DatabaseManager,
    headless: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    status_callback: Callable[[str], None] | None = None,
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
    if status_callback:
        status_callback("initialising database…")
    await db.initialize_db()

    session_path = settings.data_dir / "session.json"
    scraped_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine scrape strategy based on whether the last run completed fully.
    # fast_incremental: vault is known-complete — stop at first dup (LIFO boundary).
    # full_scan: last run was interrupted — scan everything to recover orphaned posts.
    sync_before = await db.get_sync_state()
    scrape_mode: Literal["fast_incremental", "full_scan"] = (
        "fast_incremental" if sync_before.last_scrape_was_complete else "full_scan"
    )
    _logger.info("Scrape mode: %s", scrape_mode)

    new_posts = 0
    skipped_existing = 0
    failed_extractions = 0
    _completed_naturally = False  # set True only when the loop exits without exception

    start = time.monotonic()

    try:
        async with linkedin_browser_session(
            session_path, headless=headless, status_callback=status_callback
        ) as page:
            async for raw_post in scroll_and_extract_raw_posts(
                page, status_callback=status_callback
            ):
                # Convert raw DOM data → Post model
                post = raw_post_to_model(raw_post, scraped_at)

                if post is None:
                    failed_extractions += 1
                    _logger.debug("Skipping unextractable post (url=%r).", raw_post.url)
                    continue

                existing = await db.get_post_by_linkedin_id(post.linkedin_id)
                if existing is not None:
                    skipped_existing += 1
                    if scrape_mode == "fast_incremental":
                        # Vault is complete: the LIFO boundary is reached.
                        # Everything below is already stored — safe to stop.
                        _logger.info(
                            "Reached already-stored post %s — stopping fast incremental sync.",
                            post.linkedin_id,
                        )
                        break
                    else:
                        # Full scan: skip the duplicate but keep scrolling to
                        # recover posts that were missed during the interrupted run.
                        _logger.debug(
                            "Skipping already-stored post %s — full scan continues.",
                            post.linkedin_id,
                        )
                        continue

                await db.upsert_post(post)
                new_posts += 1
                _logger.debug("Saved new post: %s by %s", post.linkedin_id, post.author_name)

                if progress_callback is not None:
                    total_processed = new_posts + skipped_existing + failed_extractions
                    progress_callback(new_posts, total_processed)

            # Loop exited cleanly (exhausted or break) — vault state is known.
            _completed_naturally = True

    except LinkedInSessionExpiredError:
        raise  # caller handles this specially — don't swallow it
    except Exception as exc:
        _logger.error("Scrape failed with an unexpected error: %s", exc, exc_info=True)
        # _completed_naturally stays False — we don't know if the feed was fully seen

    duration = time.monotonic() - start

    # Update sync state even on partial success
    try:
        sync_after = await db.get_sync_state()
        await db.update_sync_state(
            last_scraped_at=scraped_at,
            total_posts_scraped=sync_after.total_posts_scraped + new_posts,
            last_sync_duration_seconds=duration,
            last_scrape_was_complete=_completed_naturally,
        )
    except Exception as exc:
        _logger.warning("Failed to update sync state: %s", exc)

    _logger.info(
        "Scrape complete in %.1fs — mode: %s, new: %d, skipped: %d, failed: %d, complete: %s",
        duration,
        scrape_mode,
        new_posts,
        skipped_existing,
        failed_extractions,
        _completed_naturally,
    )

    return ScrapeResult(
        new_posts=new_posts,
        skipped_existing=skipped_existing,
        failed_extractions=failed_extractions,
        duration_seconds=duration,
        scrape_mode=scrape_mode,
    )
