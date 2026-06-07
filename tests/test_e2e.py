"""End-to-end smoke tests for LinkedIn Vault.

Covers three layers:
  1. TUI headless: app starts, correct first screen is shown, navigation works
  2. Dashboard API: stats, chat, settings endpoints respond correctly
  3. Security invariants: .env injection defence, Ollama URL validation
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from linkedin_vault.config import LLMProvider, Settings, _sanitize_env_value, save_settings_to_file
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post, VaultStats
from linkedin_vault.utils.url_validation import validate_ollama_url


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**kwargs: Any) -> Settings:
    """Build a Settings via model_construct — no .env reading."""
    defaults: dict[str, Any] = {
        "llm_provider": LLMProvider.ZAI,
        "llm_model": "glm-4-flash",
        "zai_api_key": "sk-test-key",
        "ollama_base_url": "http://localhost:11434",
        "chat_top_k": 8,
        "chat_model": "",
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


def _fake_stats(**kwargs: Any) -> VaultStats:
    base: dict[str, Any] = {
        "total_posts": 5,
        "enriched_posts": 3,
        "unread_posts": 2,
        "total_posts_scraped": 10,
        "last_scraped_at": "2026-06-07T10:00:00",
    }
    base.update(kwargs)
    return VaultStats(**base)


# ---------------------------------------------------------------------------
# 1. TUI headless smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tui_shows_home_screen_when_configured(tmp_path: Path) -> None:
    """When llm_model and zai_api_key are set, app pushes HomeScreen."""
    from linkedin_vault.tui.app import LinkedInVaultApp
    from linkedin_vault.tui.screens.home_screen import HomeScreen

    settings = _settings()
    mock_db = AsyncMock()
    mock_db.initialize_db = AsyncMock()
    mock_db.get_stats = AsyncMock(return_value=_fake_stats())
    mock_db.get_db_path = lambda: tmp_path / "vault.db"

    with patch("linkedin_vault.tui.app.load_settings", return_value=settings), \
         patch("linkedin_vault.tui.app.DatabaseManager", return_value=mock_db):
        app = LinkedInVaultApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert isinstance(pilot.app.screen, HomeScreen), (
                f"Expected HomeScreen, got {type(pilot.app.screen).__name__}"
            )


@pytest.mark.asyncio
async def test_tui_shows_setup_screen_when_no_model(tmp_path: Path) -> None:
    """When llm_model is empty, app pushes SetupScreen first."""
    from linkedin_vault.tui.app import LinkedInVaultApp
    from linkedin_vault.tui.screens.setup_screen import SetupScreen

    settings = _settings(llm_model="")
    mock_db = AsyncMock()
    mock_db.initialize_db = AsyncMock()
    mock_db.get_db_path = lambda: tmp_path / "vault.db"

    with patch("linkedin_vault.tui.app.load_settings", return_value=settings), \
         patch("linkedin_vault.tui.app.DatabaseManager", return_value=mock_db):
        app = LinkedInVaultApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert isinstance(pilot.app.screen, SetupScreen), (
                f"Expected SetupScreen, got {type(pilot.app.screen).__name__}"
            )


@pytest.mark.asyncio
async def test_tui_shows_setup_screen_when_zai_key_missing(tmp_path: Path) -> None:
    """ZAI provider with empty API key → SetupScreen (first-run)."""
    from linkedin_vault.tui.app import LinkedInVaultApp
    from linkedin_vault.tui.screens.setup_screen import SetupScreen

    settings = _settings(zai_api_key="")
    mock_db = AsyncMock()
    mock_db.initialize_db = AsyncMock()
    mock_db.get_db_path = lambda: tmp_path / "vault.db"

    with patch("linkedin_vault.tui.app.load_settings", return_value=settings), \
         patch("linkedin_vault.tui.app.DatabaseManager", return_value=mock_db):
        app = LinkedInVaultApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert isinstance(pilot.app.screen, SetupScreen)


@pytest.mark.asyncio
async def test_tui_home_menu_navigation(tmp_path: Path) -> None:
    """j moves cursor down, k moves it back up in the home menu."""
    from textual.widgets import ListView

    from linkedin_vault.tui.app import LinkedInVaultApp
    from linkedin_vault.tui.screens.home_screen import HomeScreen

    settings = _settings()
    mock_db = AsyncMock()
    mock_db.initialize_db = AsyncMock()
    mock_db.get_stats = AsyncMock(return_value=_fake_stats())
    mock_db.get_db_path = lambda: tmp_path / "vault.db"

    with patch("linkedin_vault.tui.app.load_settings", return_value=settings), \
         patch("linkedin_vault.tui.app.DatabaseManager", return_value=mock_db):
        app = LinkedInVaultApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            assert isinstance(pilot.app.screen, HomeScreen)

            menu = pilot.app.screen.query_one("#main-menu", ListView)
            assert menu.index == 0  # starts at top

            await pilot.press("j")
            await pilot.pause(0.05)
            assert menu.index == 1  # moved down

            await pilot.press("k")
            await pilot.pause(0.05)
            assert menu.index == 0  # back to top


@pytest.mark.asyncio
async def test_tui_s_key_opens_settings(tmp_path: Path) -> None:
    """Pressing 's' from HomeScreen pushes SettingsScreen."""
    from linkedin_vault.tui.app import LinkedInVaultApp
    from linkedin_vault.tui.screens.settings_screen import SettingsScreen

    settings = _settings()
    mock_db = AsyncMock()
    mock_db.initialize_db = AsyncMock()
    mock_db.get_stats = AsyncMock(return_value=_fake_stats())
    mock_db.get_db_path = lambda: tmp_path / "vault.db"

    with patch("linkedin_vault.tui.app.load_settings", return_value=settings), \
         patch("linkedin_vault.tui.app.DatabaseManager", return_value=mock_db), \
         patch("linkedin_vault.tui.screens.settings_screen.load_settings", return_value=settings):
        app = LinkedInVaultApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("s")
            await pilot.pause(0.1)
            assert isinstance(pilot.app.screen, SettingsScreen), (
                f"Expected SettingsScreen, got {type(pilot.app.screen).__name__}"
            )


# ---------------------------------------------------------------------------
# 2. Dashboard API e2e
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

    with patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Python is used for data science [1]."
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

    with patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Hello!"
        resp1 = await client.post("/api/chat", json={"message": "Hi there"})
        assert resp1.status_code == 200
        session_id = resp1.json()["session_id"]

        mock_llm.return_value = "Still here!"
        resp2 = await client.post(
            "/api/chat", json={"session_id": session_id, "message": "Still there?"}
        )
        assert resp2.status_code == 200
        assert resp2.json()["session_id"] == session_id


@pytest.mark.asyncio
async def test_dashboard_chat_clear_session(e2e_client) -> None:
    """DELETE /api/chat/{session_id} removes a session."""
    client, _ = e2e_client

    with patch("linkedin_vault.chat.synthesiser._call_zai", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Hi!"
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
# 3. Security invariants
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
