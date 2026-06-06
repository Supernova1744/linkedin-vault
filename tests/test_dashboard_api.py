"""Tests for the Phase-4 dashboard API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post

# ---------------------------------------------------------------------------
# Fixture: initialised DB + API client wired to the same temp path
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_client(tmp_path: Path):
    """Yield (client, db) with a fresh isolated database per test."""
    from linkedin_vault.dashboard.app import app  # late import so static dir is resolved

    db_path = tmp_path / "test_dashboard.db"
    db = DatabaseManager(db_path)
    await db.initialize_db()

    # Inject the test db_path into app state; the lifespan will pick it up
    app.state.db_path = db_path

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, db

    app.state.db_path = None  # prevent stale path from leaking to the next test


# ---------------------------------------------------------------------------
# Helper: minimal valid Post
# ---------------------------------------------------------------------------


def make_post(n: int, **kwargs: Any) -> Post:
    defaults: dict[str, Any] = dict(
        linkedin_id=f"urn:li:activity:{n}",
        url=f"https://linkedin.com/post/{n}",
        author_name=f"Author {n}",
        content=f"Content for post {n}",
        scraped_at=f"2024-01-{n:02d}T00:00:00Z",
    )
    defaults.update(kwargs)
    return Post(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_get_posts_empty_db(db_client):
    client, _ = db_client
    resp = await client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["posts"] == []
    assert data["total"] == 0
    assert data["page"] == 1


async def test_get_posts_with_results(db_client):
    client, db = db_client
    await db.upsert_post(make_post(1, author_name="Alice"))
    resp = await client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["posts"]) == 1
    assert data["posts"][0]["author_name"] == "Alice"
    assert isinstance(data["posts"][0]["tags"], list)  # tags always a list


async def test_get_post_by_id(db_client):
    client, db = db_client
    post_id = await db.upsert_post(make_post(2, author_name="Bob"))
    resp = await client.get(f"/api/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["author_name"] == "Bob"
    assert resp.json()["id"] == post_id


async def test_get_post_not_found(db_client):
    client, _ = db_client
    resp = await client.get("/api/posts/99999")
    assert resp.status_code == 404


async def test_patch_post_status_valid(db_client):
    client, db = db_client
    post_id = await db.upsert_post(make_post(3))
    resp = await client.patch(f"/api/posts/{post_id}/status", json={"status": "read"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    updated = await db.get_post_by_id(post_id)
    assert updated is not None
    assert updated.status == "read"
    assert updated.status_updated_at is not None


async def test_patch_post_status_invalid(db_client):
    client, db = db_client
    post_id = await db.upsert_post(make_post(4))
    resp = await client.patch(f"/api/posts/{post_id}/status", json={"status": "nonsense"})
    assert resp.status_code == 422


async def test_get_stats(db_client):
    client, db = db_client
    await db.upsert_post(make_post(5))
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 1
    assert data["unread_posts"] == 1
    assert data["enriched_posts"] == 0
    assert "last_scraped_at" in data


async def test_get_tags(db_client):
    client, db = db_client
    enriched = make_post(
        6,
        tags=["Python", "AI", "Machine Learning"],
        summary="Some summary",
        importance_score=8.0,
        is_outdated=False,
        enriched_at="2024-01-06T01:00:00Z",
        enrichment_model="test-model",
    )
    await db.upsert_post(enriched)

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    tags = resp.json()["tags"]
    assert "AI" in tags
    assert "Python" in tags
    assert "Machine Learning" in tags
    # Result is sorted alphabetically
    assert tags == sorted(tags)


async def test_search_posts(db_client):
    client, db = db_client
    await db.upsert_post(make_post(7, author_name="Grace", content="Python programming tips"))
    await db.upsert_post(
        make_post(8, author_name="Heidi", content="JavaScript frameworks comparison")
    )

    resp = await client.get("/api/posts?q=Python")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["posts"][0]["author_name"] == "Grace"


async def test_search_posts_empty_query_returns_all(db_client):
    """An empty q= param must NOT trigger FTS5 — it should return all posts."""
    client, db = db_client
    await db.upsert_post(make_post(9))
    await db.upsert_post(make_post(10))

    resp = await client.get("/api/posts?q=")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_delete_post(db_client):
    client, db = db_client
    post_id = await db.upsert_post(make_post(11, author_name="Ivan"))

    # Verify it exists
    assert (await db.get_post_by_id(post_id)) is not None

    resp = await client.delete(f"/api/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Subsequent GET must return 404
    resp2 = await client.get(f"/api/posts/{post_id}")
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# Phase-5 pagination, edge-case, and error-path additions
# ---------------------------------------------------------------------------


async def test_get_posts_pagination(db_client):
    """12 posts, page=2 page_size=5: returns 5 items, total=12, pages=3."""
    client, db = db_client
    for n in range(1, 13):
        await db.upsert_post(make_post(n))

    resp = await client.get("/api/posts?page=2&page_size=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 12
    assert len(data["posts"]) == 5
    assert data["pages"] == 3


async def test_get_posts_last_page_partial(db_client):
    """12 posts, page=3 page_size=5: last page has only 2 items (12 - 5 - 5 = 2)."""
    client, db = db_client
    for n in range(1, 13):
        await db.upsert_post(make_post(n))

    resp = await client.get("/api/posts?page=3&page_size=5")
    assert resp.status_code == 200
    assert len(resp.json()["posts"]) == 2


async def test_get_posts_page_zero_rejected(db_client):
    """page=0 is below the ge=1 constraint and must return 422."""
    client, _ = db_client
    resp = await client.get("/api/posts?page=0")
    assert resp.status_code == 422


async def test_get_posts_page_size_too_large_rejected(db_client):
    """page_size=101 exceeds the le=100 constraint and must return 422."""
    client, _ = db_client
    resp = await client.get("/api/posts?page_size=101")
    assert resp.status_code == 422


async def test_get_posts_tag_filter(db_client):
    """tag=Python returns only posts that carry that tag."""
    client, db = db_client
    python_post = make_post(
        1,
        tags=["Python", "AI"],
        summary="Python post",
        importance_score=7.0,
        is_outdated=False,
        enriched_at="2024-01-01T01:00:00Z",
        enrichment_model="test-model",
    )
    js_post = make_post(
        2,
        tags=["JavaScript"],
        summary="JS post",
        importance_score=6.0,
        is_outdated=False,
        enriched_at="2024-01-02T01:00:00Z",
        enrichment_model="test-model",
    )
    await db.upsert_post(python_post)
    await db.upsert_post(js_post)

    resp = await client.get("/api/posts?tag=Python")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["posts"][0]["author_name"] == "Author 1"


async def test_get_posts_status_filter(db_client):
    """status=unread returns only posts with status='unread'."""
    client, db = db_client
    post_id = await db.upsert_post(make_post(1))
    await db.update_post_status(post_id, "read")
    await db.upsert_post(make_post(2))  # stays unread

    resp = await client.get("/api/posts?status=unread")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["posts"][0]["author_name"] == "Author 2"


async def test_patch_status_not_found_returns_404(db_client):
    """PATCH /api/posts/99999/status must return 404 when the post doesn't exist."""
    client, _ = db_client
    resp = await client.patch("/api/posts/99999/status", json={"status": "read"})
    assert resp.status_code == 404


async def test_patch_status_backward_transition(db_client):
    """read → unread transition is allowed; final status is 'unread'."""
    client, db = db_client
    post_id = await db.upsert_post(make_post(1))

    resp = await client.patch(f"/api/posts/{post_id}/status", json={"status": "read"})
    assert resp.status_code == 200

    resp = await client.patch(f"/api/posts/{post_id}/status", json={"status": "unread"})
    assert resp.status_code == 200

    post = await db.get_post_by_id(post_id)
    assert post is not None
    assert post.status == "unread"


async def test_patch_status_missing_body_returns_422(db_client):
    """PATCH with an empty JSON body (missing 'status' key) must return 422."""
    client, db = db_client
    post_id = await db.upsert_post(make_post(1))
    resp = await client.patch(f"/api/posts/{post_id}/status", json={})
    assert resp.status_code == 422


async def test_delete_not_found_returns_404(db_client):
    """DELETE /api/posts/99999 must return 404 when the post doesn't exist."""
    client, _ = db_client
    resp = await client.delete("/api/posts/99999")
    assert resp.status_code == 404


async def test_get_post_noninteger_id_returns_422(db_client):
    """GET /api/posts/abc — non-integer path parameter must return 422."""
    client, _ = db_client
    resp = await client.get("/api/posts/abc")
    assert resp.status_code == 422


async def test_get_tags_empty_db_returns_empty_list(db_client):
    """GET /api/tags on a database with no enriched posts must return an empty list."""
    client, _ = db_client
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    assert resp.json()["tags"] == []


async def test_get_posts_page_beyond_last_returns_empty(db_client):
    """Requesting a page past the last page returns 200 with an empty posts list."""
    client, db = db_client
    await db.upsert_post(make_post(1))

    resp = await client.get("/api/posts?page=99")
    assert resp.status_code == 200
    data = resp.json()
    assert data["posts"] == []
    assert data["total"] == 1  # total reflects actual row count, not the (empty) page
