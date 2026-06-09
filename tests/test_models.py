from typing import Any

import pytest

from linkedin_vault.db.models import (
    POST_STATUS_READ,
    POST_STATUS_SAVED_LATER,
    POST_STATUS_SKIPPED,
    POST_STATUS_UNREAD,
    VALID_POST_STATUSES,
    Post,
    SyncState,
    VaultStats,
)


def _make_post(**kwargs: Any) -> Post:
    defaults: dict[str, Any] = dict(
        linkedin_id="urn:li:activity:1",
        url="https://linkedin.com/post/1",
        author_name="Alice",
        content="Some content",
        scraped_at="2024-06-01T12:00:00Z",
    )
    defaults.update(kwargs)
    return Post(**defaults)


def test_post_default_status() -> None:
    p = _make_post()
    assert p.status == POST_STATUS_UNREAD


def test_post_valid_statuses() -> None:
    all_statuses = (
        POST_STATUS_UNREAD,
        POST_STATUS_READ,
        POST_STATUS_SKIPPED,
        POST_STATUS_SAVED_LATER,
    )
    for status in all_statuses:
        p = _make_post(status=status)
        assert p.status == status


def test_post_invalid_status_raises() -> None:
    with pytest.raises(ValueError, match="Invalid status"):
        _make_post(status="invalid_status")


def test_post_importance_score_bounds() -> None:
    p = _make_post(importance_score=0.0)
    assert p.importance_score == 0.0
    p = _make_post(importance_score=10.0)
    assert p.importance_score == 10.0


def test_post_importance_score_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="importance_score"):
        _make_post(importance_score=10.1)
    with pytest.raises(ValueError, match="importance_score"):
        _make_post(importance_score=-0.1)


def test_post_optional_fields_default_to_none() -> None:
    p = _make_post()
    assert p.id is None
    assert p.author_profile_url is None
    assert p.post_date is None
    assert p.summary is None
    assert p.tags is None
    assert p.importance_score is None
    assert p.is_outdated is None
    assert p.enriched_at is None
    assert p.enrichment_model is None
    assert p.status_updated_at is None


def test_post_with_all_fields() -> None:
    p = Post(
        id=1,
        linkedin_id="urn:li:activity:100",
        url="https://linkedin.com/post/100",
        author_name="Bob",
        author_profile_url="https://linkedin.com/in/bob",
        content="Content here",
        post_date="2024-01-01T00:00:00Z",
        scraped_at="2024-06-01T12:00:00Z",
        summary="A short summary",
        tags=["Python", "AI"],
        importance_score=9.5,
        is_outdated=False,
        enriched_at="2024-06-02T00:00:00Z",
        enrichment_model="glm-4-flash",
        status="read",
        status_updated_at="2024-06-02T01:00:00Z",
    )
    assert p.id == 1
    assert p.tags == ["Python", "AI"]
    assert p.is_outdated is False
    assert p.importance_score == 9.5


def test_sync_state_instantiation() -> None:
    s = SyncState(
        last_scraped_at="2024-06-01T12:00:00Z",
        total_posts_scraped=100,
        last_sync_duration_seconds=42.5,
    )
    assert s.total_posts_scraped == 100
    assert s.last_sync_duration_seconds == pytest.approx(42.5)


def test_sync_state_nullable_fields() -> None:
    s = SyncState(
        last_scraped_at=None,
        total_posts_scraped=0,
        last_sync_duration_seconds=None,
    )
    assert s.last_scraped_at is None
    assert s.last_sync_duration_seconds is None


def test_vault_stats_instantiation() -> None:
    vs = VaultStats(
        total_posts=50,
        enriched_posts=30,
        unread_posts=20,
        total_posts_scraped=55,
        last_scraped_at="2024-06-01T12:00:00Z",
    )
    assert vs.total_posts == 50
    assert vs.enriched_posts == 30
    assert vs.unread_posts == 20


def test_valid_post_statuses_set() -> None:
    assert "unread" in VALID_POST_STATUSES
    assert "read" in VALID_POST_STATUSES
    assert "skipped" in VALID_POST_STATUSES
    assert "saved_later" in VALID_POST_STATUSES
    assert len(VALID_POST_STATUSES) == 4
