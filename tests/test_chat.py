"""Comprehensive tests for the Agentic RAG chat feature.

Covers:
  1. SessionStore unit tests
  2. retrieve_posts unit tests
  3. extract_citation_ids unit tests
  4. Settings helper tests (get_chat_provider / get_chat_model)
  5. FastAPI route integration tests (POST /api/chat, DELETE, GET /api/settings)
  6. Synthesiser unit tests (_format_context, _call_zai, _call_ollama)
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from linkedin_vault.chat.retriever import retrieve_posts
from linkedin_vault.chat.session import MAX_HISTORY_TURNS, ChatSession, SessionStore
from linkedin_vault.chat.synthesiser import (
    _call_ollama,
    _call_zai,
    _format_context,
    extract_citation_ids,
)
from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import Post
from linkedin_vault.enricher.base import LLMProviderError


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def make_post(n: int, **kwargs: Any) -> Post:
    """Build a minimal valid Post with id=n; keyword args override defaults."""
    defaults: dict[str, Any] = dict(
        id=n,
        linkedin_id=f"urn:li:activity:{n}",
        url=f"https://linkedin.com/post/{n}",
        author_name=f"Author {n}",
        content=f"Content for post {n}",
        scraped_at=f"2024-01-{min(n, 28):02d}T00:00:00Z",
    )
    defaults.update(kwargs)
    return Post(**defaults)


# ---------------------------------------------------------------------------
# Fixture: isolated database + manually-wired session store
#
# NOTE: httpx's ASGITransport does NOT emit the ASGI lifespan protocol, so
# app.state.session_store is never set by the lifespan.  We mirror the
# existing db_client pattern: set both pieces of app state explicitly so
# that every route that reads them works correctly.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def chat_client(tmp_path: Path):
    """Yield (client, db) wired to a fresh isolated database for chat tests."""
    from linkedin_vault.dashboard.app import app  # late import: resolves static dir

    db_path = tmp_path / "test_chat.db"
    db = DatabaseManager(db_path)
    await db.initialize_db()

    app.state.db_path = db_path
    app.state.session_store = SessionStore()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, db

    # Prevent stale state from leaking into the next test
    app.state.db_path = None
    app.state.session_store = None


# ===========================================================================
# 1. SessionStore unit tests
# ===========================================================================


class TestSessionStore:
    def test_get_or_create_none_creates_new_session(self):
        store = SessionStore()
        session = store.get_or_create(None)
        assert isinstance(session, ChatSession)
        # session_id must be a valid UUID string
        uuid.UUID(session.session_id)

    def test_get_or_create_existing_id_returns_same_session(self):
        store = SessionStore()
        s1 = store.get_or_create(None)
        s2 = store.get_or_create(s1.session_id)
        assert s1 is s2

    def test_get_or_create_unknown_id_creates_new_session(self):
        """An unrecognised id must not crash — a brand-new session is returned."""
        store = SessionStore()
        unknown_id = str(uuid.uuid4())
        session = store.get_or_create(unknown_id)
        assert isinstance(session, ChatSession)
        # A new id is generated — the unknown id itself is NOT adopted
        assert session.session_id != unknown_id

    def test_delete_existing_returns_true_and_removes_session(self):
        store = SessionStore()
        session = store.get_or_create(None)
        old_id = session.session_id

        assert store.delete(old_id) is True

        # After deletion get_or_create with the same id creates a NEW session
        new_session = store.get_or_create(old_id)
        assert new_session.session_id != old_id

    def test_delete_unknown_id_returns_false(self):
        store = SessionStore()
        assert store.delete(str(uuid.uuid4())) is False

    def test_add_turn_appends_user_and_assistant_messages(self):
        store = SessionStore()
        session = store.get_or_create(None)

        store.add_turn(session, "hello", "hi there")

        assert len(session.messages) == 2
        assert session.messages[0] == {"role": "user", "content": "hello"}
        assert session.messages[1] == {"role": "assistant", "content": "hi there"}

    def test_add_turn_trims_to_max_history_turns(self):
        """After MAX_HISTORY_TURNS+1 exchanges the oldest pair is discarded."""
        store = SessionStore()
        session = store.get_or_create(None)

        for i in range(MAX_HISTORY_TURNS + 1):
            store.add_turn(session, f"user-{i}", f"assistant-{i}")

        # Must not exceed the cap
        assert len(session.messages) == MAX_HISTORY_TURNS * 2

        # Turn 0 must have been evicted; turn MAX_HISTORY_TURNS must be last
        last_turn_idx = MAX_HISTORY_TURNS
        assert session.messages[-2]["content"] == f"user-{last_turn_idx}"
        assert session.messages[-1]["content"] == f"assistant-{last_turn_idx}"

        # Turn 0 must no longer appear anywhere
        all_contents = {m["content"] for m in session.messages}
        assert "user-0" not in all_contents
        assert "assistant-0" not in all_contents


# ===========================================================================
# 2. retrieve_posts unit tests
# ===========================================================================


async def test_retrieve_uses_fts5_when_results_available():
    mock_db = MagicMock()
    posts = [make_post(1), make_post(2)]
    mock_db.search_posts_keywords = AsyncMock(return_value=posts)
    mock_db.get_all_posts = AsyncMock(return_value=[])

    result = await retrieve_posts(mock_db, "python", top_k=5)

    mock_db.search_posts_keywords.assert_awaited_once_with("python", limit=5)
    mock_db.get_all_posts.assert_not_awaited()
    assert result == posts


async def test_retrieve_falls_back_to_importance_when_fts5_empty():
    """When FTS5 returns nothing, fall back to top-K sorted by importance_score."""
    mock_db = MagicMock()
    mock_db.search_posts_keywords = AsyncMock(return_value=[])
    fallback_posts = [
        make_post(1, importance_score=5.0),
        make_post(2, importance_score=9.0),
        make_post(3, importance_score=3.0),
    ]
    mock_db.get_all_posts = AsyncMock(return_value=fallback_posts)

    result = await retrieve_posts(mock_db, "obscure query", top_k=3)

    mock_db.search_posts_keywords.assert_awaited_once()
    # Fallback fetches top_k * 5 to have a large pool to sort from
    mock_db.get_all_posts.assert_awaited_once_with(limit=15)
    # Must be sorted descending by importance_score
    assert result[0].id == 2  # score 9.0
    assert result[1].id == 1  # score 5.0
    assert result[2].id == 3  # score 3.0


async def test_retrieve_respects_top_k_limit_in_fts5_path():
    mock_db = MagicMock()
    mock_db.search_posts_keywords = AsyncMock(
        return_value=[make_post(i) for i in range(1, 4)]
    )
    mock_db.get_all_posts = AsyncMock(return_value=[])

    result = await retrieve_posts(mock_db, "relevant", top_k=3)

    mock_db.search_posts_keywords.assert_awaited_once_with("relevant", limit=3)
    assert len(result) <= 3


async def test_retrieve_respects_top_k_limit_in_fallback_path():
    mock_db = MagicMock()
    mock_db.search_posts_keywords = AsyncMock(return_value=[])
    mock_db.get_all_posts = AsyncMock(
        return_value=[make_post(i, importance_score=float(i)) for i in range(1, 6)]
    )

    result = await retrieve_posts(mock_db, "relevant", top_k=2)

    assert len(result) <= 2


# ===========================================================================
# 3. extract_citation_ids unit tests
# ===========================================================================


def test_extract_citation_ids_single():
    result = extract_citation_ids("See [Post 42] for details.")
    assert result == {42}


def test_extract_citation_ids_multiple():
    result = extract_citation_ids("[Post 1] is related, and also check [Post 99].")
    assert result == {1, 99}


def test_extract_citation_ids_returns_empty_set_when_none():
    result = extract_citation_ids("No citations here at all.")
    assert result == set()


# ===========================================================================
# 4. Settings helper tests
# ===========================================================================


def test_settings_chat_get_chat_provider_falls_back_to_llm_provider():
    settings = Settings(llm_provider=LLMProvider.ZAI, chat_provider=None)
    assert settings.get_chat_provider() == LLMProvider.ZAI


def test_settings_chat_get_chat_provider_returns_override_when_set():
    settings = Settings(llm_provider=LLMProvider.ZAI, chat_provider=LLMProvider.OLLAMA)
    assert settings.get_chat_provider() == LLMProvider.OLLAMA


def test_settings_chat_get_chat_model_falls_back_to_llm_model():
    settings = Settings(llm_model="base-model", chat_model="")
    assert settings.get_chat_model() == "base-model"


def test_settings_chat_get_chat_model_returns_override_when_set():
    settings = Settings(llm_model="base-model", chat_model="chat-specific-model")
    assert settings.get_chat_model() == "chat-specific-model"


# ===========================================================================
# 5. FastAPI route integration tests
# ===========================================================================


async def test_api_chat_empty_message_returns_400(chat_client):
    client, _ = chat_client
    resp = await client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 400


async def test_api_chat_whitespace_only_message_returns_400(chat_client):
    client, _ = chat_client
    resp = await client.post("/api/chat", json={"message": "   "})
    assert resp.status_code == 400


async def test_api_chat_success_returns_required_fields_and_citations(chat_client):
    client, _ = chat_client
    answer_text = "Based on [Post 1], Python is popular."
    mock_post = make_post(1, content="Python tips", importance_score=8.0, tags=["Python"])

    with (
        patch(
            "linkedin_vault.dashboard.app.retrieve_posts",
            new=AsyncMock(return_value=[mock_post]),
        ),
        patch(
            "linkedin_vault.dashboard.app.synthesise",
            new=AsyncMock(return_value=answer_text),
        ),
        patch(
            "linkedin_vault.dashboard.app.load_settings",
            return_value=Settings(chat_top_k=5),
        ),
    ):
        resp = await client.post("/api/chat", json={"message": "Tell me about Python"})

    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    # UUID-shaped string
    uuid.UUID(data["session_id"])
    assert data["answer"] == answer_text
    assert data["retrieved_count"] == 1
    # Citation for Post 1 must be present and correct
    assert len(data["citations"]) == 1
    assert data["citations"][0]["post_id"] == 1
    assert data["citations"][0]["author_name"] == "Author 1"


async def test_api_chat_returns_same_session_id_on_second_call(chat_client):
    client, _ = chat_client

    with (
        patch(
            "linkedin_vault.dashboard.app.retrieve_posts",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "linkedin_vault.dashboard.app.synthesise",
            new=AsyncMock(return_value="Answer one"),
        ),
        patch(
            "linkedin_vault.dashboard.app.load_settings",
            return_value=Settings(chat_top_k=5),
        ),
    ):
        resp1 = await client.post("/api/chat", json={"message": "first question"})

    assert resp1.status_code == 200
    session_id = resp1.json()["session_id"]

    with (
        patch(
            "linkedin_vault.dashboard.app.retrieve_posts",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "linkedin_vault.dashboard.app.synthesise",
            new=AsyncMock(return_value="Answer two"),
        ),
        patch(
            "linkedin_vault.dashboard.app.load_settings",
            return_value=Settings(chat_top_k=5),
        ),
    ):
        resp2 = await client.post(
            "/api/chat", json={"message": "second question", "session_id": session_id}
        )

    assert resp2.status_code == 200
    assert resp2.json()["session_id"] == session_id


async def test_api_chat_llm_provider_error_returns_503(chat_client):
    client, _ = chat_client

    with (
        patch(
            "linkedin_vault.dashboard.app.retrieve_posts",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "linkedin_vault.dashboard.app.synthesise",
            new=AsyncMock(side_effect=LLMProviderError("provider down")),
        ),
        patch(
            "linkedin_vault.dashboard.app.load_settings",
            return_value=Settings(chat_top_k=5),
        ),
    ):
        resp = await client.post("/api/chat", json={"message": "What is AI?"})

    assert resp.status_code == 503
    assert "provider down" in resp.json()["detail"]


async def test_api_delete_chat_existing_session_returns_ok(chat_client):
    client, _ = chat_client

    with (
        patch(
            "linkedin_vault.dashboard.app.retrieve_posts",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "linkedin_vault.dashboard.app.synthesise",
            new=AsyncMock(return_value="hello"),
        ),
        patch(
            "linkedin_vault.dashboard.app.load_settings",
            return_value=Settings(chat_top_k=5),
        ),
    ):
        resp = await client.post("/api/chat", json={"message": "Hello"})

    session_id = resp.json()["session_id"]

    del_resp = await client.delete(f"/api/chat/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True


async def test_api_delete_chat_unknown_session_still_returns_200(chat_client):
    """DELETE /api/chat/{id} must return 200 even when the id is unknown — no 404."""
    client, _ = chat_client
    resp = await client.delete(f"/api/chat/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


async def test_api_get_settings_returns_correct_field_names_and_types(chat_client):
    client, _ = chat_client
    test_settings = Settings(
        llm_provider=LLMProvider.ZAI,
        llm_model="glm-4-flash",
        chat_provider=LLMProvider.OLLAMA,
        chat_model="llama3",
        chat_top_k=10,
    )

    with patch("linkedin_vault.dashboard.app.load_settings", return_value=test_settings):
        resp = await client.get("/api/settings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider"] == "zai"
    assert data["llm_model"] == "glm-4-flash"
    assert data["chat_provider"] == "ollama"
    assert data["chat_model"] == "llama3"
    assert data["chat_top_k"] == 10
    assert isinstance(data["chat_top_k"], int)


# ===========================================================================
# 6. Synthesiser unit tests
# ===========================================================================


def test_synthesiser_format_context_single_post_contains_all_fields():
    post = Post(
        id=42,
        linkedin_id="urn:li:activity:123",
        url="https://linkedin.com/post/123",
        author_name="Alice Smith",
        content="Python is great for data science!",
        scraped_at="2024-01-01T00:00:00Z",
        post_date="2024-01-01",
        summary="A post about Python.",
        tags=["Python", "Data Science"],
        importance_score=7.5,
    )

    result = _format_context([post])

    assert "[Post 42]" in result
    assert "Alice Smith" in result
    assert "Python is great for data science!" in result
    assert "A post about Python." in result
    assert "Python" in result
    assert "Data Science" in result
    assert "7.5" in result
    assert "2024-01-01" in result


async def test_synthesiser_call_zai_returns_answer_text():
    messages = [{"role": "user", "content": "hello"}]
    model = "glm-4-flash"
    settings = Settings(zai_api_key="test-key", zai_base_url="https://api.z.ai/v1")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "This is the answer from ZAI."}}]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("linkedin_vault.chat.synthesiser.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _call_zai(messages, model, settings)

    assert result == "This is the answer from ZAI."
    mock_client.post.assert_awaited_once()


async def test_synthesiser_call_ollama_returns_answer_text():
    messages = [{"role": "user", "content": "hello"}]
    model = "llama3"
    settings = Settings(ollama_base_url="http://localhost:11434")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"message": {"content": "Ollama answer here."}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("linkedin_vault.chat.synthesiser.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await _call_ollama(messages, model, settings)

    assert result == "Ollama answer here."
    mock_client.post.assert_awaited_once()


async def test_synthesiser_call_ollama_raises_llm_provider_error_on_connect_error():
    messages = [{"role": "user", "content": "hello"}]
    model = "llama3"
    settings = Settings(ollama_base_url="http://localhost:11434")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("linkedin_vault.chat.synthesiser.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(LLMProviderError, match="Ollama not reachable"):
            await _call_ollama(messages, model, settings)
