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
