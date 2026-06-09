from pathlib import Path

import pytest

from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post, SyncState, VaultStats


async def test_initialize_db_creates_tables(db: DatabaseManager, tmp_db_path: Path) -> None:
    assert tmp_db_path.exists()
    import aiosqlite

    async with aiosqlite.connect(tmp_db_path) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert "posts" in tables
    assert "sync_state" in tables


async def test_initialize_db_idempotent(tmp_db_path: Path) -> None:
    mgr = DatabaseManager(tmp_db_path)
    await mgr.initialize_db()
    await mgr.initialize_db()  # second call must not raise


async def test_upsert_post_inserts(db: DatabaseManager, sample_post: Post) -> None:
    row_id = await db.upsert_post(sample_post)
    assert row_id > 0


async def test_upsert_post_deduplicates(db: DatabaseManager, sample_post: Post) -> None:
    await db.upsert_post(sample_post)
    await db.upsert_post(sample_post)  # second upsert on same linkedin_id
    posts = await db.get_all_posts()
    assert len(posts) == 1


async def test_upsert_updates_fields(db: DatabaseManager, sample_post: Post) -> None:
    await db.upsert_post(sample_post)
    updated = Post(
        linkedin_id=sample_post.linkedin_id,
        url="https://www.linkedin.com/feed/update/urn:li:activity:1234567890?updated=1",
        author_name="Jane Doe Updated",
        content="Updated content.",
        scraped_at="2024-06-02T00:00:00Z",
    )
    await db.upsert_post(updated)
    posts = await db.get_all_posts()
    assert len(posts) == 1
    assert posts[0].author_name == "Jane Doe Updated"


async def test_get_post_by_id(db: DatabaseManager, sample_post: Post) -> None:
    row_id = await db.upsert_post(sample_post)
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.linkedin_id == sample_post.linkedin_id
    assert post.author_name == sample_post.author_name


async def test_get_post_by_id_missing_returns_none(db: DatabaseManager) -> None:
    result = await db.get_post_by_id(999)
    assert result is None


async def test_get_post_by_linkedin_id(db: DatabaseManager, sample_post: Post) -> None:
    await db.upsert_post(sample_post)
    post = await db.get_post_by_linkedin_id(sample_post.linkedin_id)
    assert post is not None
    assert post.url == sample_post.url


async def test_tags_round_trip(db: DatabaseManager, enriched_post: Post) -> None:
    """tags must survive the JSON serialization round-trip as list[str]."""
    row_id = await db.upsert_post(enriched_post)
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert isinstance(post.tags, list)
    assert post.tags == ["Python", "Performance", "Open Source"]


async def test_is_outdated_round_trip(db: DatabaseManager, enriched_post: Post) -> None:
    """is_outdated must survive the int→bool conversion."""
    row_id = await db.upsert_post(enriched_post)
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert isinstance(post.is_outdated, bool)
    assert post.is_outdated is False


async def test_is_outdated_true(db: DatabaseManager, sample_post: Post) -> None:
    outdated = Post(
        linkedin_id=sample_post.linkedin_id,
        url=sample_post.url,
        author_name=sample_post.author_name,
        content=sample_post.content,
        scraped_at=sample_post.scraped_at,
        is_outdated=True,
        tags=["AI"],
        importance_score=2.0,
        enriched_at="2024-06-01T13:00:00Z",
        enrichment_model="glm-4-flash",
        summary="old post",
    )
    row_id = await db.upsert_post(outdated)
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.is_outdated is True


async def test_tags_none_round_trip(db: DatabaseManager, sample_post: Post) -> None:
    """Posts with no tags must come back as None, not JSON null."""
    row_id = await db.upsert_post(sample_post)
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.tags is None


async def test_update_post_status(db: DatabaseManager, sample_post: Post) -> None:
    row_id = await db.upsert_post(sample_post)
    await db.update_post_status(row_id, "read")
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.status == "read"
    assert post.status_updated_at is not None


async def test_update_post_enrichment(db: DatabaseManager, sample_post: Post) -> None:
    row_id = await db.upsert_post(sample_post)
    await db.update_post_enrichment(
        post_id=row_id,
        summary="A summary.",
        tags=["AI", "Python"],
        importance_score=7.0,
        is_outdated=False,
        enrichment_model="glm-4-flash",
    )
    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.summary == "A summary."
    assert post.tags == ["AI", "Python"]
    assert post.importance_score == 7.0
    assert post.is_outdated is False
    assert post.enrichment_model == "glm-4-flash"
    assert post.enriched_at is not None


async def test_get_all_posts_returns_all(db: DatabaseManager) -> None:
    posts = [
        Post(
            linkedin_id=f"urn:li:activity:{i}",
            url=f"https://linkedin.com/post/{i}",
            author_name=f"Author {i}",
            content=f"Content {i}",
            scraped_at="2024-06-01T12:00:00Z",
        )
        for i in range(5)
    ]
    for p in posts:
        await db.upsert_post(p)
    result = await db.get_all_posts()
    assert len(result) == 5


async def test_get_all_posts_status_filter(db: DatabaseManager) -> None:
    p1 = Post(
        linkedin_id="urn:li:activity:100",
        url="https://linkedin.com/post/100",
        author_name="A",
        content="Content",
        scraped_at="2024-06-01T12:00:00Z",
        status="unread",
    )
    p2 = Post(
        linkedin_id="urn:li:activity:200",
        url="https://linkedin.com/post/200",
        author_name="B",
        content="Content 2",
        scraped_at="2024-06-01T12:00:00Z",
        status="read",
    )
    await db.upsert_post(p1)
    await db.upsert_post(p2)
    unread = await db.get_all_posts(status_filter="unread")
    assert len(unread) == 1
    assert unread[0].linkedin_id == "urn:li:activity:100"


async def test_search_posts(db: DatabaseManager) -> None:
    p = Post(
        linkedin_id="urn:li:activity:fts1",
        url="https://linkedin.com/post/fts1",
        author_name="Dr. Smith",
        content="Machine learning transformers are revolutionizing NLP tasks",
        scraped_at="2024-06-01T12:00:00Z",
    )
    await db.upsert_post(p)
    results = await db.search_posts("transformers")
    assert len(results) >= 1
    assert any(r.linkedin_id == "urn:li:activity:fts1" for r in results)


async def test_search_posts_special_chars(db: DatabaseManager) -> None:
    """FTS5 special chars in query must not raise."""
    results = await db.search_posts("C++")
    assert isinstance(results, list)


async def test_get_sync_state_initial(db: DatabaseManager) -> None:
    state = await db.get_sync_state()
    assert isinstance(state, SyncState)
    assert state.total_posts_scraped == 0
    assert state.last_scraped_at is None


async def test_update_sync_state(db: DatabaseManager) -> None:
    await db.update_sync_state(
        last_scraped_at="2024-06-01T12:00:00Z",
        total_posts_scraped=42,
        last_sync_duration_seconds=15.3,
    )
    state = await db.get_sync_state()
    assert state.total_posts_scraped == 42
    assert state.last_scraped_at == "2024-06-01T12:00:00Z"
    assert state.last_sync_duration_seconds == pytest.approx(15.3)


async def test_get_stats_empty_db(db: DatabaseManager) -> None:
    stats = await db.get_stats()
    assert isinstance(stats, VaultStats)
    assert stats.total_posts == 0
    assert stats.enriched_posts == 0
    assert stats.unread_posts == 0


async def test_get_stats_with_data(
    db: DatabaseManager, sample_post: Post, enriched_post: Post
) -> None:
    p2 = Post(
        linkedin_id="urn:li:activity:999",
        url="https://linkedin.com/post/999",
        author_name="Bob",
        content="Another post",
        scraped_at="2024-06-01T12:00:00Z",
        status="read",
    )
    await db.upsert_post(sample_post)
    await db.upsert_post(enriched_post)  # updates the first post via upsert
    await db.upsert_post(p2)

    stats = await db.get_stats()
    assert stats.total_posts == 2
    assert stats.enriched_posts == 1
    assert stats.unread_posts == 1


async def test_delete_post(db: DatabaseManager, sample_post: Post) -> None:
    row_id = await db.upsert_post(sample_post)
    await db.delete_post(row_id)
    result = await db.get_post_by_id(row_id)
    assert result is None


# ---------------------------------------------------------------------------
# Phase-5 regression and coverage additions
# ---------------------------------------------------------------------------


async def test_upsert_preserves_status_on_re_scrape(db: DatabaseManager, sample_post: Post) -> None:
    """Re-upserting a post (as happens on re-scrape) must not reset a non-default status."""
    row_id = await db.upsert_post(sample_post)
    await db.update_post_status(row_id, "read")

    # Simulate re-scrape: same linkedin_id, so ON CONFLICT path runs
    await db.upsert_post(sample_post)

    post = await db.get_post_by_id(row_id)
    assert post is not None
    assert post.status == "read"  # status column is intentionally excluded from ON CONFLICT SET


async def test_search_posts_double_quote_returns_empty_not_error(
    db: DatabaseManager,
) -> None:
    """A query with a double-quote must be escaped and return [] rather than OperationalError."""
    results = await db.search_posts('foo"bar')
    assert results == []


async def test_search_posts_empty_string_returns_empty(
    db: DatabaseManager, sample_post: Post
) -> None:
    """An empty query string must short-circuit to [] without touching FTS5."""
    await db.upsert_post(sample_post)
    results = await db.search_posts("")
    assert results == []


async def test_get_posts_filtered_pagination(db: DatabaseManager) -> None:
    """25 posts inserted, page=2 page_size=10 returns 10 posts with total=25."""
    for i in range(1, 26):
        post = Post(
            linkedin_id=f"urn:li:activity:pg{i}",
            url=f"https://linkedin.com/post/pg{i}",
            author_name=f"Author {i}",
            content=f"Content {i}",
            scraped_at=f"2024-01-{i:02d}T00:00:00Z",
        )
        await db.upsert_post(post)

    posts, total = await db.get_posts_filtered(page=2, page_size=10)
    assert total == 25
    assert len(posts) == 10


async def test_get_posts_filtered_tag_filter(db: DatabaseManager) -> None:
    """tag='Python' returns only posts that contain that tag."""
    p_python = Post(
        linkedin_id="urn:li:activity:tag-py",
        url="https://linkedin.com/post/tag-py",
        author_name="Alice",
        content="Python is great",
        scraped_at="2024-01-01T00:00:00Z",
        tags=["Python", "AI"],
        summary="summary",
        importance_score=7.0,
        is_outdated=False,
        enriched_at="2024-01-01T01:00:00Z",
        enrichment_model="test",
    )
    p_js = Post(
        linkedin_id="urn:li:activity:tag-js",
        url="https://linkedin.com/post/tag-js",
        author_name="Bob",
        content="JavaScript is everywhere",
        scraped_at="2024-01-02T00:00:00Z",
        tags=["JavaScript"],
        summary="summary",
        importance_score=6.0,
        is_outdated=False,
        enriched_at="2024-01-02T01:00:00Z",
        enrichment_model="test",
    )
    await db.upsert_post(p_python)
    await db.upsert_post(p_js)

    posts, total = await db.get_posts_filtered(tag="Python")
    assert total == 1
    assert posts[0].linkedin_id == "urn:li:activity:tag-py"


async def test_get_posts_filtered_status_filter(db: DatabaseManager) -> None:
    """status_filter='unread' returns only unread posts."""
    p_unread = Post(
        linkedin_id="urn:li:activity:st-unread",
        url="https://linkedin.com/post/st-unread",
        author_name="Alice",
        content="unread post",
        scraped_at="2024-01-01T00:00:00Z",
        status="unread",
    )
    p_read = Post(
        linkedin_id="urn:li:activity:st-read",
        url="https://linkedin.com/post/st-read",
        author_name="Bob",
        content="read post",
        scraped_at="2024-01-02T00:00:00Z",
        status="read",
    )
    await db.upsert_post(p_unread)
    await db.upsert_post(p_read)

    posts, total = await db.get_posts_filtered(status_filter="unread")
    assert total == 1
    assert posts[0].status == "unread"


async def test_get_posts_for_enrichment_unenriched_only(
    db: DatabaseManager, sample_post: Post
) -> None:
    """re_enrich=False returns only posts with enriched_at IS NULL."""
    await db.upsert_post(sample_post)  # unenriched

    enriched = Post(
        linkedin_id="urn:li:activity:already-enriched",
        url="https://linkedin.com/post/already-enriched",
        author_name="Bob",
        content="enriched post content",
        scraped_at="2024-01-02T00:00:00Z",
        summary="summary",
        tags=["AI"],
        importance_score=5.0,
        is_outdated=False,
        enriched_at="2024-01-02T01:00:00Z",
        enrichment_model="glm-4-flash",
    )
    await db.upsert_post(enriched)

    posts = await db.get_posts_for_enrichment(re_enrich=False)
    assert len(posts) == 1
    assert posts[0].linkedin_id == sample_post.linkedin_id


async def test_get_posts_for_enrichment_all(db: DatabaseManager, sample_post: Post) -> None:
    """re_enrich=True returns all posts regardless of enriched_at."""
    await db.upsert_post(sample_post)  # unenriched

    enriched = Post(
        linkedin_id="urn:li:activity:enriched-all",
        url="https://linkedin.com/post/enriched-all",
        author_name="Bob",
        content="enriched post content",
        scraped_at="2024-01-02T00:00:00Z",
        summary="summary",
        tags=["AI"],
        importance_score=5.0,
        is_outdated=False,
        enriched_at="2024-01-02T01:00:00Z",
        enrichment_model="glm-4-flash",
    )
    await db.upsert_post(enriched)

    posts = await db.get_posts_for_enrichment(re_enrich=True)
    assert len(posts) == 2


async def test_get_post_by_linkedin_id_not_found(db: DatabaseManager) -> None:
    """Returns None for a linkedin_id that doesn't exist in the database."""
    result = await db.get_post_by_linkedin_id("urn:li:activity:nonexistent-9999")
    assert result is None


async def test_update_post_status_all_statuses(db: DatabaseManager, sample_post: Post) -> None:
    """All four valid status values can be round-tripped through update_post_status."""
    row_id = await db.upsert_post(sample_post)
    for status in ("unread", "read", "skipped", "saved_later"):
        await db.update_post_status(row_id, status)
        post = await db.get_post_by_id(row_id)
        assert post is not None
        assert post.status == status
