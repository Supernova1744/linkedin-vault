"""
LinkedIn post data extraction.

Primary scraping strategy: **network interception**.
LinkedIn's saved-posts page loads posts via XHR calls to
/voyager/api/graphql.  We intercept those JSON responses and parse the
``included`` array — this is stable regardless of DOM changes.

The DOM selectors below are kept as a reference / fallback, but the main
scraping path no longer depends on them.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle

from linkedin_vault.db.models import Post

# ---------------------------------------------------------------------------
# DOM Selectors
# All selectors live here.  browser.py imports what it needs from this module.
# Each list is tried in order; the first match wins.
# ---------------------------------------------------------------------------

# Post card container — LinkedIn uses several data-urn prefixes depending on
# post type.  All variants known as of 2025 are listed here.
# If scraping breaks, inspect the page DOM and add new data-urn patterns here.
SELECTOR_POST_CONTAINER = (
    "[data-urn*='activity'],"
    "[data-urn*='ugcPost'],"
    "[data-urn*='miniUpdateV2'],"
    "[data-urn*='savedItem'],"
    "[data-urn*='share'],"
    ".feed-shared-update-v2,"
    ".occludable-update,"
    "li.artdeco-list__item"
)

# Author display name
SELECTORS_AUTHOR_NAME: list[str] = [
    ".update-components-actor__name span[aria-hidden='true']",
    ".update-components-actor__name",
    ".actors-name span",
    "[data-test-id='actor-name']",
    ".app-aware-link span[aria-hidden='true']",
    ".entity-result__title-text a span[aria-hidden='true']",
]

# Author profile href
SELECTORS_AUTHOR_LINK: list[str] = [
    "a.update-components-actor__container-link",
    "a[href*='/in/'][aria-label]",
    "a[href*='/in/']",
    ".entity-result__title-text a",
]

# Post body text
SELECTORS_POST_CONTENT: list[str] = [
    ".update-components-text .text-view-model",
    ".update-components-text span[dir='ltr']",
    ".update-components-text",
    ".feed-shared-update-v2__description .break-words",
    ".feed-shared-update-v2__description",
    ".attributed-text-segment-list__content",
    ".feed-shared-inline-show-more-text",
    ".entity-result__content",
]

# Post timestamp / publication date
SELECTORS_POST_DATE: list[str] = [
    "time.update-components-actor__sub-description",
    ".update-components-actor__sub-description time",
    ".update-components-actor__sub-description span:not([aria-hidden])",
    "time[datetime]",
    "time",
]

# Permalink to the post
SELECTORS_POST_LINK: list[str] = [
    "a[href*='/feed/update/urn:li:activity']",
    "a[href*='/feed/update/urn:li:ugcPost']",
    "a[href*='activity:']",
    "a[href*='ugcPost:']",
    "a[href*='/posts/']",
    "a[href*='/pulse/']",
]

# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

# Matches LinkedIn relative timestamps: "2w", "3mo", "14h", "1d", "1yr"
_RELATIVE_RE = re.compile(
    r"^(\d+)\s*(h(?:r|rs)?|d(?:ay|ays)?|w(?:k|ks)?|mo(?:nth|nths)?|yr(?:s)?)$",
    re.IGNORECASE,
)

_ABSOLUTE_FMTS_WITH_YEAR = ["%b %d, %Y", "%B %d, %Y", "%b. %d, %Y"]
_ABSOLUTE_FMTS_WITHOUT_YEAR = ["%b %d", "%B %d", "%b. %d"]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


@dataclass
class RawPost:
    """Raw data extracted from the LinkedIn DOM before validation."""

    url: str | None
    author_name: str | None
    author_profile_url: str | None
    content: str | None
    post_date_raw: str | None


# ---------------------------------------------------------------------------
# Network-interception parser  (primary scraping path)
# ---------------------------------------------------------------------------


def extract_raws_from_api_batch(
    data: dict,
    seen_ids: set[str],
) -> list[RawPost]:
    """Parse a single LinkedIn Voyager GraphQL response into :class:`RawPost` objects.

    LinkedIn loads saved posts via XHR to ``/voyager/api/graphql``.  Each
    response contains an ``included`` array; items that have a ``summary.text``
    field are post cards.

    Args:
        data:     Parsed JSON body of one XHR response.
        seen_ids: Mutable set of activity/ugcPost IDs already processed this
                  session.  Updated in-place; duplicates are skipped.

    Returns:
        A list of :class:`RawPost` instances (may be empty).
    """
    posts: list[RawPost] = []
    included = data.get("included", [])

    for item in included:
        if not isinstance(item, dict):
            continue

        # Content lives in item["summary"]["text"]
        summary_node = item.get("summary")
        if not isinstance(summary_node, dict):
            continue
        content = summary_node.get("text", "").strip()
        if not content:
            continue

        # Derive a stable activity/ugcPost URN for deduplication + DB key.
        # Try entityUrn and trackingUrn first, then fall back to navigationUrl.
        uid: str | None = None
        nav_url: str = item.get("navigationUrl", "")
        for urn_field in ("entityUrn", "trackingUrn"):
            m = re.search(r"urn:li:(?:activity|ugcPost):\d+", item.get(urn_field, ""))
            if m:
                uid = m.group(0)
                break
        if not uid:
            m = re.search(r"urn:li:(?:activity|ugcPost):\d+", nav_url)
            if m:
                uid = m.group(0)
        if not uid or uid in seen_ids:
            continue
        seen_ids.add(uid)

        author = ((item.get("title") or {}).get("text") or "").strip() or None

        # "secondarySubtitle" is typically "2w • 🌐" — strip the icon part
        secondary = (item.get("secondarySubtitle") or {}).get("text", "")
        date_raw = secondary.split("•")[0].strip() or None

        # Normalise the navigation URL to an absolute URL that contains the URN
        if nav_url.startswith("/"):
            nav_url = f"https://www.linkedin.com{nav_url}"
        elif not nav_url.startswith("http"):
            # Construct from the URN directly so extract_linkedin_id works
            nav_url = f"https://www.linkedin.com/feed/update/{uid}"

        posts.append(
            RawPost(
                url=nav_url or None,
                author_name=author,
                author_profile_url=None,
                content=content,
                post_date_raw=date_raw,
            )
        )

    return posts


# ---------------------------------------------------------------------------
# Pure parsing functions (no Playwright, safe to test without a browser)
# ---------------------------------------------------------------------------


def extract_linkedin_id(url: str) -> str | None:
    """Extract a stable LinkedIn post URN from a URL or URN string.

    Handles ``urn:li:activity:XXXX``, ``urn:li:ugcPost:XXXX``, and
    embedded URNs inside composite strings like ``urn:li:fs_miniUpdateV2``.

    Returns the first matching URN string, or ``None`` if none is found.
    """
    match = re.search(r"(urn:li:(?:activity|ugcPost):\d+)", url)
    return match.group(1) if match else None


def parse_post_date(raw_date: str) -> str | None:
    """Convert LinkedIn timestamp text to an ISO 8601 UTC string with ``Z`` suffix.

    Handles:
    - Relative: ``"1h"``, ``"3d"``, ``"2w"``, ``"1mo"``, ``"1yr"``
    - Absolute with year: ``"Jan 15, 2024"``
    - Absolute without year: ``"Jan 15"`` (assumes current calendar year)
    - Returns ``None`` for unrecognisable input.
    """
    if not raw_date:
        return None

    text = raw_date.strip()

    # --- Relative dates ---
    m = _RELATIVE_RE.match(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        now = datetime.now(UTC)
        if unit.startswith("h"):
            delta = timedelta(hours=amount)
        elif unit.startswith("d"):
            delta = timedelta(days=amount)
        elif unit.startswith("w"):
            delta = timedelta(weeks=amount)
        elif unit.startswith("mo"):
            delta = timedelta(days=amount * 30)
        elif unit.startswith("yr"):
            delta = timedelta(days=amount * 365)
        else:
            return None
        return (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Absolute dates with year ---
    for fmt in _ABSOLUTE_FMTS_WITH_YEAR:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue

    # --- Absolute dates without year ---
    # strptime defaults to year 1900 (not a leap year), which causes "Feb 29"
    # to raise ValueError before .replace() is ever reached.  Parse against a
    # known leap-year anchor (2000) first, then replace with the target year.
    current_year = datetime.now(UTC).year
    for fmt in _ABSOLUTE_FMTS_WITHOUT_YEAR:
        anchor_fmt = f"{fmt} %Y"
        anchor_text = f"{text} 2000"
        try:
            base_dt = datetime.strptime(anchor_text, anchor_fmt)
        except ValueError:
            continue
        for year_candidate in (current_year, current_year + 1):
            try:
                return base_dt.replace(year=year_candidate).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

    logger.debug("parse_post_date: unrecognised format %r", text)
    return None


def raw_post_to_model(raw: RawPost, scraped_at: str) -> Post | None:
    """Convert a :class:`RawPost` to a :class:`Post` model.

    Returns ``None`` if any of the required fields (``url``, ``author_name``,
    ``content``) are missing, or if a ``linkedin_id`` cannot be derived from
    the URL.
    """
    if not raw.url or not raw.author_name or not raw.content:
        return None

    linkedin_id = extract_linkedin_id(raw.url)
    if linkedin_id is None:
        logger.debug("raw_post_to_model: cannot extract linkedin_id from URL %r", raw.url)
        return None

    post_date = parse_post_date(raw.post_date_raw) if raw.post_date_raw else None

    return Post(
        linkedin_id=linkedin_id,
        url=raw.url,
        author_name=raw.author_name,
        author_profile_url=raw.author_profile_url,
        content=raw.content,
        post_date=post_date,
        scraped_at=scraped_at,
    )


# ---------------------------------------------------------------------------
# Async DOM extraction (requires Playwright at call-time)
# ---------------------------------------------------------------------------


async def _try_get_text(element: ElementHandle, selectors: list[str]) -> str | None:
    """Try each selector in order; return the inner text of the first match."""
    for sel in selectors:
        try:
            handle = await element.query_selector(sel)
            if handle:
                text = await handle.inner_text()
                if text and text.strip():
                    return text.strip()
        except Exception:
            continue
    return None


async def _try_get_attr(
    element: ElementHandle, selectors: list[str], attr: str
) -> str | None:
    """Try each selector in order; return the named attribute of the first match."""
    for sel in selectors:
        try:
            handle = await element.query_selector(sel)
            if handle:
                value = await handle.get_attribute(attr)
                if value and value.strip():
                    return value.strip()
        except Exception:
            continue
    return None


async def extract_post_from_element(element: ElementHandle) -> RawPost:
    """Extract raw post data from a single LinkedIn post card DOM element.

    Never raises — all extraction errors are logged as warnings and the
    corresponding field is returned as ``None``.
    """
    url: str | None = None
    author_name: str | None = None
    author_profile_url: str | None = None
    content: str | None = None
    post_date_raw: str | None = None

    # -- Post URL / permalink --
    try:
        href = await _try_get_attr(element, SELECTORS_POST_LINK, "href")
        if href:
            url = href if href.startswith("http") else f"https://www.linkedin.com{href}"
        else:
            # Fall back to constructing URL from the data-urn attribute
            urn = await element.get_attribute("data-urn")
            if urn and "activity" in urn:
                url = f"https://www.linkedin.com/feed/update/{urn}"
    except Exception as exc:
        logger.warning("Failed to extract post URL: %s", exc)

    # -- Author name --
    try:
        author_name = await _try_get_text(element, SELECTORS_AUTHOR_NAME)
    except Exception as exc:
        logger.warning("Failed to extract author name: %s", exc)

    # -- Author profile URL --
    try:
        href = await _try_get_attr(element, SELECTORS_AUTHOR_LINK, "href")
        if href:
            author_profile_url = (
                href if href.startswith("http") else f"https://www.linkedin.com{href}"
            )
    except Exception as exc:
        logger.warning("Failed to extract author profile URL: %s", exc)

    # -- Post content --
    try:
        content = await _try_get_text(element, SELECTORS_POST_CONTENT)
    except Exception as exc:
        logger.warning("Failed to extract post content: %s", exc)

    # -- Post date --
    try:
        # First try the datetime attribute on <time>; fall back to visible text
        for sel in SELECTORS_POST_DATE:
            try:
                handle = await element.query_selector(sel)
                if handle:
                    # Try the HTML datetime attribute first (machine-readable)
                    dt_attr = await handle.get_attribute("datetime")
                    if dt_attr and dt_attr.strip():
                        post_date_raw = dt_attr.strip()
                        break
                    # Fall back to visible text ("2w", "Jan 15", etc.)
                    text = await handle.inner_text()
                    if text and text.strip():
                        post_date_raw = text.strip()
                        break
            except Exception:
                continue
    except Exception as exc:
        logger.warning("Failed to extract post date: %s", exc)

    return RawPost(
        url=url,
        author_name=author_name,
        author_profile_url=author_profile_url,
        content=content,
        post_date_raw=post_date_raw,
    )
