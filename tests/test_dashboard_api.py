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
    await db.upsert_post(make_post(8, author_name="Heidi", content="JavaScript frameworks comparison"))

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
