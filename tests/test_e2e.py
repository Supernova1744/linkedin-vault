"""End-to-end smoke tests for LinkedIn Vault.

Covers two layers:
  1. Dashboard API: stats, chat, settings endpoints respond correctly
  2. Security invariants: .env injection defence, Ollama URL validation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from linkedin_vault.config import Settings, _sanitize_env_value, save_settings_to_file
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post
from linkedin_vault.utils.url_validation import validate_ollama_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Dashboard API e2e
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def e2e_client(tmp_path: Path):
    """Full wired FastAPI client with an isolated real SQLite database."""
    from linkedin_vault.chat.session import SessionStore
    from linkedin_vault.dashboard.app import app

    db_path = tmp_path / "e2e.db"
    db = DatabaseManager(db_path)
    await db.initialize_db()

    app.state.db_path = db_path
    app.state.session_store = SessionStore()
    app.state.settings = Settings()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, db

    app.state.db_path = None
    app.state.session_store = None
    app.state.settings = None


@pytest.mark.asyncio
async def test_dashboard_stats_empty_db(e2e_client) -> None:
    """GET /api/stats returns zeros for an empty database."""
    client, _ = e2e_client
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 0
    assert data["enriched_posts"] == 0


@pytest.mark.asyncio
async def test_dashboard_posts_empty(e2e_client) -> None:
    """GET /api/posts returns empty list for empty database."""
    client, _ = e2e_client
    resp = await client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["posts"] == []


@pytest.mark.asyncio
async def test_dashboard_chat_with_real_db(e2e_client) -> None:
    """POST /api/chat returns an answer even with no posts (fallback path)."""
    client, db = e2e_client

    # Seed one post so retrieval has something to find
    post = Post(
        linkedin_id="urn:li:activity:e2e1",
        url="https://linkedin.com/post/e2e1",
        author_name="Test Author",
        content="Python is a great programming language for data science and AI.",
        scraped_at="2026-06-07T10:00:00Z",
    )
    await db.upsert_post(post)

    # Patch both providers so the test passes regardless of the local .env config.
    with (
        patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_zai,
        patch(
            "linkedin_vault.chat.synthesiser._call_ollama", new_callable=AsyncMock
        ) as mock_ollama,
    ):
        mock_zai.return_value = "Python is used for data science [1]."
        mock_ollama.return_value = "Python is used for data science [1]."
        resp = await client.post(
            "/api/chat",
            json={"message": "What do you have about Python?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert data["retrieved_count"] >= 0


@pytest.mark.asyncio
async def test_dashboard_chat_session_continuity(e2e_client) -> None:
    """Sending the same session_id across two requests maintains conversation history."""
    client, _ = e2e_client

    with (
        patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_zai,
        patch(
            "linkedin_vault.chat.synthesiser._call_ollama", new_callable=AsyncMock
        ) as mock_ollama,
    ):
        mock_zai.return_value = "Hello!"
        mock_ollama.return_value = "Hello!"
        resp1 = await client.post("/api/chat", json={"message": "Hi there"})
        assert resp1.status_code == 200
        session_id = resp1.json()["session_id"]

        mock_zai.return_value = "Still here!"
        mock_ollama.return_value = "Still here!"
        resp2 = await client.post(
            "/api/chat", json={"session_id": session_id, "message": "Still there?"}
        )
        assert resp2.status_code == 200
        assert resp2.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_dashboard_chat_clear_session(e2e_client) -> None:
    """DELETE /api/chat/{session_id} removes a session."""
    client, _ = e2e_client

    with (
        patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_zai,
        patch(
            "linkedin_vault.chat.synthesiser._call_ollama", new_callable=AsyncMock
        ) as mock_ollama,
    ):
        mock_zai.return_value = "Hi!"
        mock_ollama.return_value = "Hi!"
        resp = await client.post("/api/chat", json={"message": "hello"})
    session_id = resp.json()["session_id"]

    del_resp = await client.delete(f"/api/chat/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_dashboard_settings_endpoint(e2e_client) -> None:
    """GET /api/settings returns the expected structure."""
    client, _ = e2e_client
    resp = await client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_provider" in data
    assert "chat_top_k" in data


# ---------------------------------------------------------------------------
# 2. Security invariants
# ---------------------------------------------------------------------------


def test_env_injection_newline_stripped() -> None:
    """Newlines in values are stripped before writing to .env."""
    assert _sanitize_env_value("sk-key\nMALICIOUS=injected") == "sk-keyMALICIOUS=injected"
    assert _sanitize_env_value("value\r\nother") == "valueother"
    assert _sanitize_env_value("clean") == "clean"


def test_save_settings_newline_does_not_inject(tmp_path: Path) -> None:
    """save_settings_to_file: a value with \\n cannot inject an extra KEY=VALUE line."""
    env_path = tmp_path / ".linkedin-vault" / ".env"

    with patch("linkedin_vault.config.Path.home", return_value=tmp_path):
        save_settings_to_file({"LLM_MODEL": "glm-4\nZAI_API_KEY=stolen"})

    content = env_path.read_text()
    # No line should start with the injected key — injection stripped the \n so
    # the payload is now an inert substring of the value, not a standalone entry.
    for line in content.splitlines():
        assert not line.strip().startswith("ZAI_API_KEY=stolen"), (
            f"Injection created a standalone key-value line: {line!r}"
        )
    assert "LLM_MODEL=" in content  # the legitimate key was written


def test_save_settings_file_permissions(tmp_path: Path) -> None:
    """save_settings_to_file creates .env with mode 600."""
    import stat

    env_path = tmp_path / ".linkedin-vault" / ".env"

    with patch("linkedin_vault.config.Path.home", return_value=tmp_path):
        save_settings_to_file({"LLM_MODEL": "test"})

    mode = stat.S_IMODE(env_path.stat().st_mode)
    assert mode == 0o600, f".env has mode {oct(mode)}, expected 0o600"


def test_validate_ollama_url_rejects_file_scheme() -> None:
    """file:// URLs must be rejected — scheme is not http/https."""
    valid, msg = validate_ollama_url("file:///etc/passwd")
    assert valid is False
    assert "file" in msg


def test_validate_ollama_url_rejects_ftp_scheme() -> None:
    valid, msg = validate_ollama_url("ftp://attacker.com/api")
    assert valid is False
    assert msg


def test_validate_ollama_url_accepts_localhost() -> None:
    valid, msg = validate_ollama_url("http://localhost:11434")
    assert valid is True
    assert msg == ""


def test_validate_ollama_url_accepts_127_0_0_1() -> None:
    valid, msg = validate_ollama_url("http://127.0.0.1:11434")
    assert valid is True
    assert msg == ""


def test_validate_ollama_url_warns_on_non_localhost() -> None:
    """Non-localhost http(s) URL is valid but raises a warning message."""
    valid, msg = validate_ollama_url("http://192.168.1.100:11434")
    assert valid is True
    assert "Warning" in msg or "not localhost" in msg


def test_validate_ollama_url_empty_is_ok() -> None:
    """Empty string is treated as 'not set' — no error, no warning."""
    valid, msg = validate_ollama_url("")
    assert valid is True
    assert msg == ""


def test_validate_ollama_url_accepts_ipv6_loopback() -> None:
    """http://[::1]:11434 is IPv6 loopback — should be accepted without warning."""
    valid, msg = validate_ollama_url("http://[::1]:11434")
    assert valid is True
    assert msg == "" or "Warning" not in msg  # no warning for loopback


def test_validate_ollama_url_warns_on_ipv6_non_loopback() -> None:
    """http://[2001:db8::1]:11434 is a non-loopback IPv6 — should warn."""
    valid, msg = validate_ollama_url("http://[2001:db8::1]:11434")
    assert valid is True
    assert "Warning" in msg or "not localhost" in msg
