"""
Unit tests for linkedin_vault.scraper.parser — pure parsing logic only.

These tests do NOT use Playwright or require a browser.  Only sync/pure
functions and the RawPost dataclass are exercised here.
"""

from datetime import UTC, datetime, timedelta

from linkedin_vault.scraper.parser import (
    RawPost,
    extract_linkedin_id,
    parse_post_date,
    raw_post_to_model,
)

# ---------------------------------------------------------------------------
# extract_linkedin_id
# ---------------------------------------------------------------------------


def test_extract_linkedin_id_standard_url() -> None:
    url = "https://www.linkedin.com/feed/update/urn:li:activity:1234567890"
    assert extract_linkedin_id(url) == "urn:li:activity:1234567890"


def test_extract_linkedin_id_url_with_query_params() -> None:
    url = "https://www.linkedin.com/feed/update/urn:li:activity:9876543210?trackingId=abc123"
    assert extract_linkedin_id(url) == "urn:li:activity:9876543210"


def test_extract_linkedin_id_bare_urn() -> None:
    assert extract_linkedin_id("urn:li:activity:5555555555") == "urn:li:activity:5555555555"


def test_extract_linkedin_id_no_activity_urn() -> None:
    assert extract_linkedin_id("https://www.linkedin.com/in/someone") is None


def test_extract_linkedin_id_empty_string() -> None:
    assert extract_linkedin_id("") is None


def test_extract_linkedin_id_preserves_full_urn() -> None:
    """The returned value must be the full URN string, not just the numeric ID."""
    result = extract_linkedin_id("https://www.linkedin.com/feed/update/urn:li:activity:111")
    assert result == "urn:li:activity:111"
    assert result is not None and result.startswith("urn:li:activity:")


# ---------------------------------------------------------------------------
# parse_post_date — relative formats
# ---------------------------------------------------------------------------


def _parse_and_rehydrate(raw: str) -> datetime:
    """Parse a raw date string and return it as a timezone-aware datetime."""
    result = parse_post_date(raw)
    assert result is not None, f"Expected a date string for {raw!r}, got None"
    return datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_parse_post_date_relative_weeks() -> None:
    parsed = _parse_and_rehydrate("1w")
    expected = datetime.now(UTC) - timedelta(weeks=1)
    assert abs((parsed - expected).total_seconds()) < 86_400  # within 1 day


def test_parse_post_date_relative_days() -> None:
    parsed = _parse_and_rehydrate("3d")
    expected = datetime.now(UTC) - timedelta(days=3)
    assert abs((parsed - expected).total_seconds()) < 86_400


def test_parse_post_date_relative_hours() -> None:
    parsed = _parse_and_rehydrate("14h")
    expected = datetime.now(UTC) - timedelta(hours=14)
    assert abs((parsed - expected).total_seconds()) < 3_600  # within 1 hour


def test_parse_post_date_relative_months() -> None:
    parsed = _parse_and_rehydrate("2mo")
    expected = datetime.now(UTC) - timedelta(days=60)
    assert abs((parsed - expected).total_seconds()) < 86_400


def test_parse_post_date_relative_years() -> None:
    parsed = _parse_and_rehydrate("1yr")
    expected = datetime.now(UTC) - timedelta(days=365)
    assert abs((parsed - expected).total_seconds()) < 86_400


def test_parse_post_date_result_uses_z_suffix() -> None:
    """ISO 8601 output must end with 'Z', not '+00:00'."""
    result = parse_post_date("1w")
    assert result is not None
    assert result.endswith("Z"), f"Expected Z suffix, got: {result!r}"
    assert "+00:00" not in result


# ---------------------------------------------------------------------------
# parse_post_date — absolute formats
# ---------------------------------------------------------------------------


def test_parse_post_date_absolute_with_year() -> None:
    assert parse_post_date("Jan 15, 2024") == "2024-01-15T00:00:00Z"


def test_parse_post_date_absolute_full_month_name() -> None:
    assert parse_post_date("January 15, 2024") == "2024-01-15T00:00:00Z"


def test_parse_post_date_absolute_without_year() -> None:
    result = parse_post_date("Jan 15")
    assert result is not None
    current_year = datetime.now(UTC).year
    assert result.startswith(str(current_year))
    assert "01-15T00:00:00Z" in result


# ---------------------------------------------------------------------------
# parse_post_date — invalid / edge cases
# ---------------------------------------------------------------------------


def test_parse_post_date_invalid_returns_none() -> None:
    assert parse_post_date("definitely not a date") is None


def test_parse_post_date_empty_string_returns_none() -> None:
    assert parse_post_date("") is None


def test_parse_post_date_whitespace_only_returns_none() -> None:
    assert parse_post_date("   ") is None


# ---------------------------------------------------------------------------
# raw_post_to_model
# ---------------------------------------------------------------------------


def test_raw_post_to_model_valid(sample_raw_post: RawPost) -> None:
    scraped_at = "2024-06-01T12:00:00Z"
    post = raw_post_to_model(sample_raw_post, scraped_at)

    assert post is not None
    assert post.linkedin_id == "urn:li:activity:1234567890"
    assert post.url == sample_raw_post.url
    assert post.author_name == "Jane Doe"
    assert post.author_profile_url == "https://www.linkedin.com/in/janedoe"
    assert post.content == sample_raw_post.content
    assert post.scraped_at == scraped_at
    # post_date is derived from post_date_raw="2w" — just check it's a string
    assert post.post_date is not None
    assert post.post_date.endswith("Z")


def test_raw_post_to_model_missing_url() -> None:
    raw = RawPost(
        url=None,
        author_name="Jane",
        author_profile_url=None,
        content="Some content",
        post_date_raw=None,
    )
    assert raw_post_to_model(raw, "2024-06-01T12:00:00Z") is None


def test_raw_post_to_model_missing_author() -> None:
    raw = RawPost(
        url="https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
        author_name=None,
        author_profile_url=None,
        content="Some content",
        post_date_raw=None,
    )
    assert raw_post_to_model(raw, "2024-06-01T12:00:00Z") is None


def test_raw_post_to_model_missing_content() -> None:
    raw = RawPost(
        url="https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
        author_name="Jane",
        author_profile_url=None,
        content=None,
        post_date_raw=None,
    )
    assert raw_post_to_model(raw, "2024-06-01T12:00:00Z") is None


def test_raw_post_to_model_url_without_activity_urn() -> None:
    """URL present but contains no activity URN → cannot derive linkedin_id → None."""
    raw = RawPost(
        url="https://www.linkedin.com/in/someone",
        author_name="Jane",
        author_profile_url=None,
        content="Some content",
        post_date_raw=None,
    )
    assert raw_post_to_model(raw, "2024-06-01T12:00:00Z") is None


def test_raw_post_to_model_optional_fields_none() -> None:
    """author_profile_url and post_date_raw being None is acceptable."""
    raw = RawPost(
        url="https://www.linkedin.com/feed/update/urn:li:activity:999",
        author_name="Bob",
        author_profile_url=None,
        content="Hello world",
        post_date_raw=None,
    )
    post = raw_post_to_model(raw, "2024-06-01T12:00:00Z")
    assert post is not None
    assert post.author_profile_url is None
    assert post.post_date is None
