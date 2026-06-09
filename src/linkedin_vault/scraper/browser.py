"""
LinkedIn browser automation — session management, login, and scrolling.

NOTE: LinkedIn's DOM changes frequently. Selectors may need updating.
      All DOM selector constants are defined in parser.py to keep them
      co-located with the extraction logic that uses them.

This module owns:
- Browser/context lifecycle (Playwright Chromium)
- Session persistence to disk (storage_state JSON)
- Manual login detection and waiting
- Infinite-scroll traversal of the Saved Posts feed
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright

from linkedin_vault.scraper.parser import (
    RawPost,
    extract_raws_from_api_batch,
)
from linkedin_vault.utils.logging import get_logger

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

SAVED_POSTS_URL = "https://www.linkedin.com/my-items/saved-posts/"
LOGIN_URL = "https://www.linkedin.com/login"

# URL fragments that indicate the user is NOT yet logged in
_LOGIN_URL_PATTERNS = ("/login", "/checkpoint", "/authwall")

# ---------------------------------------------------------------------------
# Browser / timing configuration
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

PAGE_LOAD_TIMEOUT = 30_000  # ms — general page load
LOGIN_POLL_TIMEOUT = 300_000  # ms — 5 min window for manual login
SCROLL_WAIT_MS = 2_000  # ms — pause after each scroll to allow lazy load
ELEMENT_WAIT_TIMEOUT = 5_000  # ms — per-element selector waits

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LinkedInSessionExpiredError(Exception):
    """Raised by :func:`linkedin_browser_session` when the LinkedIn session has
    expired and the browser is headless — interactive login is not possible."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_status(callback: Callable[[str], None] | None) -> Callable[[str], None]:
    """Return a status reporter that calls *callback* (if set) and logs via INFO."""

    def _status(msg: str) -> None:
        if callback:
            callback(msg)
        _logger.info(msg)

    return _status


@asynccontextmanager
async def _browser_session(
    session_path: Path,
    headless: bool = False,
    status_callback: Callable[[str], None] | None = None,
) -> AsyncGenerator[Page, None]:
    """Private: launch Chromium, load session state, yield the page, persist session on exit.

    Callers navigate and interact; this context manager owns only the
    browser/context lifecycle and the session-save-on-exit logic.
    """
    _status = _make_status(status_callback)
    async with async_playwright() as playwright:
        _status("launching browser…")
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context_kwargs: dict[str, Any] = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-US",
        }
        if session_path.exists():
            _logger.info("Loading existing session from %s", session_path)
            context_kwargs["storage_state"] = str(session_path)
        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()
        try:
            yield page
        finally:
            try:
                session_path.parent.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(session_path))
                os.chmod(session_path, 0o600)
                _logger.info("Session saved to %s", session_path)
            except PlaywrightError as exc:
                _logger.warning("Could not save session: %s", exc)
            finally:
                await browser.close()


# ---------------------------------------------------------------------------
# Context manager: full browser session lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def linkedin_browser_session(
    session_path: Path,
    headless: bool = False,
    status_callback: Callable[[str], None] | None = None,
) -> AsyncGenerator[Page, None]:
    """Async context manager that yields a Playwright :class:`Page` pointed at
    the LinkedIn Saved Posts feed.

    On entry:
    - Launches Chromium (headed by default so the user can interact).
    - Loads a previously saved ``storage_state`` from *session_path* if it
      exists, so returning users skip the login step.
    - If the session has expired (or no file exists), opens the LinkedIn login
      page and waits up to 5 minutes for the user to log in manually.
      When *headless* is ``True`` and the session is expired, raises
      :class:`LinkedInSessionExpiredError` instead (interactive login impossible).

    On exit (normal or exceptional):
    - Persists the current session cookies/storage back to *session_path*.
    - Closes the browser.
    """
    _status = _make_status(status_callback)
    async with _browser_session(session_path, headless, status_callback) as page:
        _status("loading LinkedIn saved posts page…")
        await page.goto(
            SAVED_POSTS_URL,
            timeout=PAGE_LOAD_TIMEOUT,
            wait_until="domcontentloaded",
        )
        # Detect redirect to login/checkpoint/authwall
        if not page.url.startswith(SAVED_POSTS_URL.rstrip("/")) or any(
            pat in page.url for pat in _LOGIN_URL_PATTERNS
        ):
            _logger.info("Not on saved-posts page (URL: %s); triggering login.", page.url)
            if headless:
                raise LinkedInSessionExpiredError(
                    "LinkedIn session expired. "
                    "Use 'Login to LinkedIn' to authenticate, then scrape again."
                )
            _status("session expired — please log in to LinkedIn in the browser window…")
            await _perform_manual_login(page)
            _status("logged in! loading saved posts…")
        yield page


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------


async def _perform_manual_login(page: Page) -> None:
    """Navigate to the LinkedIn login page and wait for the user to complete
    the login flow manually (up to 5 minutes).

    Raises :class:`TimeoutError` if the user does not log in in time.
    """
    _logger.info(
        "Opening LinkedIn login page. Please log in in the browser window that just opened."
    )
    await page.goto(LOGIN_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")

    # Wait until the URL leaves all login/checkpoint patterns
    _logger.info("Waiting for login completion (timeout: 5 minutes)…")
    await page.wait_for_function(
        "(patterns) => patterns.every(p => !window.location.href.includes(p))",
        arg=list(_LOGIN_URL_PATTERNS),
        timeout=LOGIN_POLL_TIMEOUT,
    )

    _logger.info("Login detected. Navigating to saved posts…")
    await page.goto(SAVED_POSTS_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")


# ---------------------------------------------------------------------------
# Standalone login helper (headed — for session refresh from TUI)
# ---------------------------------------------------------------------------


async def do_login(
    session_path: Path,
    status_callback: Callable[[str], None] | None = None,
) -> None:
    """Open a headed browser and wait for the user to log in to LinkedIn.

    Always navigates to the LinkedIn login page.  If an existing session is
    still valid, LinkedIn redirects immediately and this returns in seconds.
    Saves the refreshed session to *session_path* on completion.

    Raises :class:`TimeoutError` if the user does not log in within 5 minutes.
    """
    _status = _make_status(status_callback)
    async with _browser_session(
        session_path, headless=False, status_callback=status_callback
    ) as page:
        _status("opening LinkedIn login page…")
        await page.goto(LOGIN_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="domcontentloaded")
        _status("waiting for login (up to 5 minutes)…")
        await page.wait_for_function(
            "(patterns) => patterns.every(p => !window.location.href.includes(p))",
            arg=list(_LOGIN_URL_PATTERNS),
            timeout=LOGIN_POLL_TIMEOUT,
        )
        _status("logged in! saving session…")


# ---------------------------------------------------------------------------
# Network-interception scrolling  (primary scraping path)
# ---------------------------------------------------------------------------

# LinkedIn's saved-posts GraphQL endpoint — we intercept all responses to it.
_VOYAGER_GRAPHQL = "voyager/api/graphql"

# Scrolls with no new API batches before giving up.
_MAX_STALE_SCROLLS = 8


async def scroll_and_extract_raw_posts(
    page: Page,
    max_stale_scrolls: int = _MAX_STALE_SCROLLS,
    status_callback: Callable[[str], None] | None = None,
) -> AsyncGenerator[RawPost, None]:
    """Async generator — intercepts LinkedIn's GraphQL XHR responses while
    scrolling the Saved Posts feed and yields :class:`RawPost` objects.

    LinkedIn does NOT render post content as stable DOM elements; it loads
    posts via paginated XHR calls to ``/voyager/api/graphql``.  Intercepting
    those JSON responses is the only reliable extraction strategy.

    Stops after ``max_stale_scrolls`` consecutive scrolls with no new API
    batches (i.e. the feed is fully loaded).

    Args:
        page:              A Playwright :class:`Page` pointed at the saved
                           posts URL.
        max_stale_scrolls: Number of empty scrolls before stopping.
    """
    _logger.info("Starting network-interception scrape on %s", page.url)

    # Collected raw API response bodies; appended by the async callback below.
    raw_batches: list[dict] = []
    seen_ids: set[str] = set()

    async def _on_response(response) -> None:  # type: ignore[no-untyped-def]
        if _VOYAGER_GRAPHQL not in response.url:
            return
        if response.status != 200:
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        try:
            body = await response.body()
            data = json.loads(body)
            included = data.get("included", [])
            # Only keep batches that contain post items (have summary.text)
            if any(
                isinstance(it, dict)
                and isinstance(it.get("summary"), dict)
                and it["summary"].get("text")
                for it in included
            ):
                raw_batches.append(data)
                _logger.debug("Captured API batch (%d total)", len(raw_batches))
        except Exception as exc:
            _logger.debug("Failed to parse API response: %s", exc)

    page.on("response", _on_response)

    # Let the first batch load before starting scroll loop
    if status_callback:
        status_callback("waiting for posts to load…")
    await page.wait_for_timeout(4_000)

    stale = 0
    prev_batch_count = 0
    scroll_num = 0

    while stale < max_stale_scrolls:
        scroll_num += 1
        if status_callback:
            status_callback(f"scan {scroll_num}…")

        # Process any newly arrived batches
        if len(raw_batches) > prev_batch_count:
            for data in raw_batches[prev_batch_count:]:
                for raw in extract_raws_from_api_batch(data, seen_ids):
                    yield raw
            prev_batch_count = len(raw_batches)
            stale = 0
            _logger.debug("Posts so far: %d  (batches: %d)", len(seen_ids), len(raw_batches))
        else:
            stale += 1
            _logger.debug("No new batches after scroll (%d/%d).", stale, max_stale_scrolls)

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(SCROLL_WAIT_MS)
        except PlaywrightError as exc:
            _logger.warning("Scroll failed: %s", exc)
            break

    _logger.info(
        "Scroll complete. Total posts extracted: %d  API batches: %d",
        len(seen_ids),
        len(raw_batches),
    )
