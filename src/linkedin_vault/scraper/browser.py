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

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright

from linkedin_vault.scraper.parser import (
    SELECTOR_POST_CONTAINER,
    RawPost,
    extract_post_from_element,
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

PAGE_LOAD_TIMEOUT = 30_000      # ms — general page load
LOGIN_POLL_TIMEOUT = 300_000    # ms — 5 min window for manual login
SCROLL_WAIT_MS = 2_000          # ms — pause after each scroll to allow lazy load
ELEMENT_WAIT_TIMEOUT = 5_000    # ms — per-element selector waits

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Context manager: full browser session lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def linkedin_browser_session(
    session_path: Path,
    headless: bool = False,
) -> AsyncGenerator[Page, None]:
    """Async context manager that yields a Playwright :class:`Page` pointed at
    the LinkedIn Saved Posts feed.

    On entry:
    - Launches Chromium (headed by default so the user can interact).
    - Loads a previously saved ``storage_state`` from *session_path* if it
      exists, so returning users skip the login step.
    - If the session has expired (or no file exists), opens the LinkedIn login
      page and waits up to 5 minutes for the user to log in manually.

    On exit (normal or exceptional):
    - Persists the current session cookies/storage back to *session_path*.
    - Closes the browser.
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context_kwargs: dict[str, object] = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "locale": "en-US",
        }
        if session_path.exists():
            _logger.info("Loading existing browser session from %s", session_path)
            context_kwargs["storage_state"] = str(session_path)

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        try:
            _logger.info("Navigating to saved posts page…")
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
                await _perform_manual_login(page)

            yield page

        finally:
            # Always persist the session so the next run skips login
            try:
                import os
                session_path.parent.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(session_path))
                os.chmod(session_path, 0o600)
                _logger.info("Browser session saved to %s", session_path)
            except PlaywrightError as exc:
                _logger.warning("Could not save browser session: %s", exc)
            finally:
                await browser.close()


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
# Scrolling + extraction
# ---------------------------------------------------------------------------


_DIAG_SELECTORS = [
    "[data-urn*='activity']",
    "[data-urn*='ugcPost']",
    "[data-urn*='savedItem']",
    "[data-urn*='miniUpdateV2']",
    "[data-urn*='share']",
    ".feed-shared-update-v2",
    ".occludable-update",
    ".entity-result",
    "[data-id]",
]

_DIAG_JS = """
(selectors) => {
    const out = {url: location.href, title: document.title, hits: {}, urnSamples: []};
    for (const sel of selectors) {
        const n = document.querySelectorAll(sel).length;
        if (n) out.hits[sel] = n;
    }
    const allUrn = Array.from(document.querySelectorAll('[data-urn]'));
    out.urnSamples = allUrn.slice(0, 12).map(el => ({
        tag: el.tagName,
        urn: (el.getAttribute('data-urn') || '').substring(0, 80),
        cls: el.className.substring(0, 60)
    }));
    return out;
}
"""


async def _run_page_diagnostic(page: Page) -> dict:
    """Run JS on the page to identify what selectors and data-urn values exist."""
    try:
        return await page.evaluate(_DIAG_JS, _DIAG_SELECTORS)  # type: ignore[arg-type]
    except Exception as exc:
        _logger.debug("Page diagnostic JS failed: %s", exc)
        return {}


async def _write_diagnostic_file(diag: dict) -> str:
    """Write diagnostic info to ~/.linkedin-vault/debug_diagnostic.txt."""
    from pathlib import Path
    path = Path.home() / ".linkedin-vault" / "debug_diagnostic.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"URL:   {diag.get('url', '?')}",
        f"Title: {diag.get('title', '?')}",
        "",
        "Selector hits (count > 0):",
    ]
    hits = diag.get("hits", {})
    if hits:
        for sel, n in hits.items():
            lines.append(f"  {n:4d}  {sel}")
    else:
        lines.append("  (none — no known selectors matched anything)")
    lines += ["", "data-urn samples (first 12):"]
    for s in diag.get("urnSamples", []):
        lines.append(f"  <{s['tag'].lower()}> class={s['cls']!r}  urn={s['urn']!r}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


async def _save_debug_screenshot(page: Page) -> str | None:
    """Save a screenshot to ~/.linkedin-vault/debug_screenshot.png and return the path."""
    try:
        from pathlib import Path
        screenshot_path = Path.home() / ".linkedin-vault" / "debug_screenshot.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=False)
        return str(screenshot_path)
    except Exception as exc:
        _logger.debug("Could not save debug screenshot: %s", exc)
        return None


async def scroll_and_extract_raw_posts(
    page: Page,
    max_no_new_scrolls: int = 3,
) -> AsyncGenerator[RawPost, None]:
    """Async generator — yields :class:`RawPost` objects from the Saved Posts
    feed, scrolling lazily until no new posts load.

    Stops when ``max_no_new_scrolls`` consecutive scrolls produce zero new
    post containers (i.e. the feed is fully loaded).

    The caller controls early termination: ``break``-ing out of the ``async for``
    loop (e.g. on hitting a post already in the DB) cleanly closes the generator.

    Args:
        page: A Playwright :class:`Page` already pointed at the saved posts URL.
        max_no_new_scrolls: Stop after this many scrolls with no new containers.
    """
    # Give LinkedIn's JS framework extra time to render the feed after navigation
    await page.wait_for_timeout(3_000)

    _logger.info("Page URL after navigation: %s", page.url)

    # Run diagnostic immediately — writes to file even if scrape succeeds,
    # so the selector hit-counts are always available for debugging.
    diag = await _run_page_diagnostic(page)
    diag_path = await _write_diagnostic_file(diag)
    _logger.info("Page diagnostic written to %s", diag_path)
    _logger.info("Selector hits: %s", diag.get("hits", {}))

    # Wait for the first post to appear (returns early if the page is empty)
    try:
        await page.wait_for_selector(SELECTOR_POST_CONTAINER, timeout=PAGE_LOAD_TIMEOUT)
    except PlaywrightError:
        screenshot = await _save_debug_screenshot(page)
        _logger.warning(
            "No post containers found within %ds. URL: %s. "
            "Diagnostic: %s  Screenshot: %s",
            PAGE_LOAD_TIMEOUT // 1000,
            page.url,
            diag_path,
            screenshot or "n/a",
        )
        return

    seen_ids: set[str] = set()
    no_new_scroll_count = 0

    while no_new_scroll_count < max_no_new_scrolls:
        try:
            containers = await page.query_selector_all(SELECTOR_POST_CONTAINER)
        except PlaywrightError as exc:
            _logger.warning("query_selector_all failed: %s", exc)
            break

        new_in_batch = 0
        for container in containers:
            # Build a stable dedup key: prefer data-urn, fall back to the
            # first post-link href found inside the container.
            try:
                uid = await container.get_attribute("data-urn") or ""
                if not uid:
                    link = await container.query_selector(
                        "a[href*='/feed/update/'], a[href*='/posts/'], a[href*='/pulse/']"
                    )
                    if link:
                        uid = (await link.get_attribute("href")) or ""
            except PlaywrightError:
                continue

            if not uid or uid in seen_ids:
                continue

            seen_ids.add(uid)
            new_in_batch += 1

            try:
                raw = await extract_post_from_element(container)
            except Exception as exc:
                _logger.warning("extract_post_from_element raised unexpectedly: %s", exc)
                continue

            yield raw

        if new_in_batch == 0:
            no_new_scroll_count += 1
            _logger.debug(
                "No new posts after scroll (%d/%d).",
                no_new_scroll_count,
                max_no_new_scrolls,
            )
        else:
            no_new_scroll_count = 0
            _logger.debug("Found %d new post(s) in this batch.", new_in_batch)

        # Scroll 2x viewport height to trigger LinkedIn's lazy loader
        try:
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await page.wait_for_timeout(SCROLL_WAIT_MS)
        except PlaywrightError as exc:
            _logger.warning("Scroll failed: %s", exc)
            break

    _logger.info("Scroll complete. Total unique containers seen: %d.", len(seen_ids))
