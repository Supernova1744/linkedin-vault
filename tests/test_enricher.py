"""
Tests for the Phase 3 enricher package.

All tests are pure-logic or use httpx mocks — no live network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.enricher.base import LLMProviderError
from linkedin_vault.enricher.factory import get_provider
from linkedin_vault.enricher.ollama import OllamaProvider
from linkedin_vault.enricher.prompt import build_enrichment_prompt, parse_enrichment_response
from linkedin_vault.enricher.zai import ZAI_KNOWN_MODELS, ZAIProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_JSON = json.dumps(
    {
        "summary": "The author shares insights on Python performance.",
        "tags": ["Python", "Open Source"],  # both must be in ALLOWED_TAGS
        "importance_score": 7.5,
        "is_outdated": False,
    }
)


def _make_async_client_mock(
    status_code: int = 200,
    response_json: dict | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Return a mock that behaves like ``httpx.AsyncClient`` used as async ctx manager."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    if response_json is not None:
        mock_response.json = MagicMock(return_value=response_json)
    mock_response.text = "error body"

    mock_client = AsyncMock()
    if side_effect is not None:
        mock_client.get = AsyncMock(side_effect=side_effect)
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock(return_value=mock_response)

    # Make it work as `async with httpx.AsyncClient(...) as client:`
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# ---------------------------------------------------------------------------
# parse_enrichment_response
# ---------------------------------------------------------------------------


def test_parse_enrichment_response_valid() -> None:
    result = parse_enrichment_response(_VALID_JSON)
    assert result.summary == "The author shares insights on Python performance."
    assert result.tags == ["Python", "Open Source"]
    assert result.importance_score == 7.5
    assert result.is_outdated is False
    assert result.model_used == ""  # set by calling provider


def test_parse_enrichment_response_clamps_score_high() -> None:
    raw = json.dumps(
        {
            "summary": "Test post.",
            "tags": ["AI"],
            "importance_score": 15.0,
            "is_outdated": False,
        }
    )
    result = parse_enrichment_response(raw)
    assert result.importance_score == 10.0


def test_parse_enrichment_response_clamps_score_low() -> None:
    raw = json.dumps(
        {
            "summary": "Test post.",
            "tags": ["AI"],
            "importance_score": -2.0,
            "is_outdated": False,
        }
    )
    result = parse_enrichment_response(raw)
    assert result.importance_score == 0.0


def test_parse_enrichment_response_missing_field() -> None:
    raw = json.dumps(
        {
            "tags": ["AI"],
            "importance_score": 5.0,
            "is_outdated": False,
            # "summary" is intentionally absent
        }
    )
    with pytest.raises(ValueError, match="summary"):
        parse_enrichment_response(raw)


def test_parse_enrichment_response_strips_json_fence() -> None:
    fenced = "```json\n" + _VALID_JSON + "\n```"
    result = parse_enrichment_response(fenced)
    assert result.importance_score == 7.5


def test_parse_enrichment_response_extracts_embedded_json() -> None:
    """Handles prose + JSON when the fence stripping doesn't fire."""
    wrapped = "Here is your analysis:\n" + _VALID_JSON + "\nHope that helps!"
    result = parse_enrichment_response(wrapped)
    assert result.tags == ["Python", "Open Source"]


# ---------------------------------------------------------------------------
# build_enrichment_prompt
# ---------------------------------------------------------------------------


def test_build_enrichment_prompt_contains_content() -> None:
    content = "Unique post content XYZ123"
    prompt = build_enrichment_prompt(
        content=content,
        author_name="Alice",
        post_date="2025-01-10",
        today="2026-06-06",
    )
    assert content in prompt


def test_build_enrichment_prompt_outdated_check() -> None:
    today = "2026-06-06"
    prompt = build_enrichment_prompt(
        content="Some post.",
        author_name="Bob",
        post_date="2024-01-01",
        today=today,
    )
    # Both today's date and the outdated-check rule must appear in the prompt
    assert today in prompt
    assert "12 months" in prompt


def test_build_enrichment_prompt_handles_missing_post_date() -> None:
    prompt = build_enrichment_prompt(
        content="Post without a date.",
        author_name="Carol",
        post_date=None,
        today="2026-06-06",
    )
    assert "unknown" in prompt.lower()


# ---------------------------------------------------------------------------
# ZAIProvider.list_models — fallback on error
# ---------------------------------------------------------------------------


async def test_zai_provider_list_models_fallback() -> None:
    """A 500 response from /models must return ZAI_KNOWN_MODELS, not raise."""
    mock_client = _make_async_client_mock(status_code=500)

    with patch("linkedin_vault.enricher.zai.httpx.AsyncClient", return_value=mock_client):
        provider = ZAIProvider(api_key="test-key-abc")
        result = await provider.list_models()

    assert result == ZAI_KNOWN_MODELS


async def test_zai_provider_list_models_success() -> None:
    """A successful /models response must be parsed and returned."""
    response_data = {"data": [{"id": "glm-4-flash"}, {"id": "glm-4"}]}
    mock_client = _make_async_client_mock(status_code=200, response_json=response_data)

    with patch("linkedin_vault.enricher.zai.httpx.AsyncClient", return_value=mock_client):
        provider = ZAIProvider(api_key="test-key-abc")
        result = await provider.list_models()

    assert result == ["glm-4-flash", "glm-4"]


# ---------------------------------------------------------------------------
# OllamaProvider.list_models — connection error → LLMProviderError
# ---------------------------------------------------------------------------


async def test_ollama_provider_list_models_connection_error() -> None:
    """A ConnectError must be converted to LLMProviderError('Ollama is not running')."""
    mock_client = _make_async_client_mock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("linkedin_vault.enricher.ollama.httpx.AsyncClient", return_value=mock_client):
        provider = OllamaProvider(base_url="http://localhost:11434")
        with pytest.raises(LLMProviderError, match="Ollama is not running"):
            await provider.list_models()


async def test_ollama_provider_list_models_success() -> None:
    """A successful /api/tags response must be parsed and returned."""
    response_data = {"models": [{"name": "llama3.2"}, {"name": "mistral"}]}
    mock_client = _make_async_client_mock(status_code=200, response_json=response_data)

    with patch("linkedin_vault.enricher.ollama.httpx.AsyncClient", return_value=mock_client):
        provider = OllamaProvider(base_url="http://localhost:11434")
        result = await provider.list_models()

    assert result == ["llama3.2", "mistral"]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_get_provider_returns_zai(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "test.db",
        llm_provider=LLMProvider.ZAI,
        llm_model="glm-4-flash",
        zai_api_key="test-key",
    )
    provider = get_provider(settings)
    assert isinstance(provider, ZAIProvider)


def test_get_provider_returns_ollama(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "test.db",
        llm_provider=LLMProvider.OLLAMA,
        llm_model="llama3.2",
    )
    provider = get_provider(settings)
    assert isinstance(provider, OllamaProvider)


# ---------------------------------------------------------------------------
# Null-field regression tests (Phase-5 bug fixes)
# ---------------------------------------------------------------------------


def test_parse_enrichment_response_null_tags_raises_value_error() -> None:
    """tags: null must raise ValueError (was TypeError before the fix)."""
    raw = json.dumps({"summary": "x", "tags": None, "importance_score": 5.0, "is_outdated": False})
    with pytest.raises(ValueError, match="tags"):
        parse_enrichment_response(raw)


def test_parse_enrichment_response_null_importance_score_raises_value_error() -> None:
    """importance_score: null must raise ValueError."""
    raw = json.dumps(
        {"summary": "x", "tags": ["AI"], "importance_score": None, "is_outdated": False}
    )
    with pytest.raises(ValueError, match="importance_score"):
        parse_enrichment_response(raw)


def test_parse_enrichment_response_top_level_null_raises_value_error() -> None:
    """A top-level JSON null (not a dict) must raise ValueError mentioning 'JSON object'."""
    with pytest.raises(ValueError, match="JSON object"):
        parse_enrichment_response("null")


def test_parse_enrichment_response_tags_filtered_to_allowed() -> None:
    """Tags not in ALLOWED_TAGS are silently dropped; recognised ones are kept."""
    raw = json.dumps(
        {
            "summary": "x",
            "tags": ["AI", "FakeTag", "Python"],
            "importance_score": 5.0,
            "is_outdated": False,
        }
    )
    result = parse_enrichment_response(raw)
    assert "AI" in result.tags
    assert "Python" in result.tags
    assert "FakeTag" not in result.tags


def test_parse_enrichment_response_tags_not_a_list_raises() -> None:
    """tags must be a list; a bare string value must raise ValueError."""
    raw = json.dumps({"summary": "x", "tags": "AI", "importance_score": 5.0, "is_outdated": False})
    with pytest.raises(ValueError, match="list"):
        parse_enrichment_response(raw)


# ---------------------------------------------------------------------------
# ZAIProvider.enrich_post — retry behaviour
# ---------------------------------------------------------------------------


async def test_zai_provider_enrich_post_retries_on_429_then_succeeds() -> None:
    """429 on attempts 1 and 2, 200 on attempt 3: valid EnrichmentResult is returned."""
    success_body = json.dumps(
        {"summary": "x", "tags": ["AI"], "importance_score": 7.0, "is_outdated": False}
    )
    success_json = {"choices": [{"message": {"content": success_body}}]}

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = "rate limited"

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json = MagicMock(return_value=success_json)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_429, mock_429, mock_200])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("linkedin_vault.enricher.zai.httpx.AsyncClient", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        provider = ZAIProvider(api_key="test-key")
        result = await provider.enrich_post(
            content="test content",
            author_name="Alice",
            post_date="2024-01-15",
            model="glm-4-flash",
            today="2026-06-06",
        )

    assert result.tags == ["AI"]
    assert result.importance_score == 7.0
    assert result.model_used == "glm-4-flash"
    assert mock_client.post.call_count == 3  # three total attempts
    assert mock_sleep.call_count == 2  # sleep before attempt 2 and attempt 3


async def test_zai_provider_enrich_post_exhausted_retries_raises() -> None:
    """All MAX_RETRIES (3) attempts return 429: LLMProviderError raised after 3 calls."""
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = "rate limited"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_429)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("linkedin_vault.enricher.zai.httpx.AsyncClient", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        provider = ZAIProvider(api_key="test-key")
        with pytest.raises(LLMProviderError):
            await provider.enrich_post(
                content="test content",
                author_name="Alice",
                post_date=None,
                model="glm-4-flash",
                today="2026-06-06",
            )

    assert mock_client.post.call_count == 3  # MAX_RETRIES = 3


async def test_zai_provider_enrich_post_401_no_retry() -> None:
    """401 Unauthorized is not in RETRYABLE_STATUS_CODES: raises after exactly 1 call."""
    mock_401 = MagicMock()
    mock_401.status_code = 401
    mock_401.text = "unauthorized"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_401)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("linkedin_vault.enricher.zai.httpx.AsyncClient", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        provider = ZAIProvider(api_key="test-key")
        with pytest.raises(LLMProviderError):
            await provider.enrich_post(
                content="test content",
                author_name="Alice",
                post_date=None,
                model="glm-4-flash",
                today="2026-06-06",
            )

    assert mock_client.post.call_count == 1  # no retry for non-transient errors
    assert mock_sleep.call_count == 0
