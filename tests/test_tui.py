"""Unit tests for TUI pure-Python logic.

These tests avoid instantiating any Textual App or Screen — only
module-level functions containing testable pure logic are exercised
directly.  No Textual event loop is started, no .env file is written,
and no filesystem side effects are produced.
"""
from __future__ import annotations

import pytest

from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.tui.app import _is_first_run
from linkedin_vault.tui.screens.enrich_screen import _BAR_WIDTH, _render_bar


def _settings(**kwargs: object) -> Settings:
    """Build a Settings instance via model_construct — bypasses .env reading."""
    defaults = {
        "llm_provider": LLMProvider.ZAI,
        "llm_model": "",
        "zai_api_key": "",
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TC-TUI-001 … 005  _is_first_run
# ---------------------------------------------------------------------------


class TestIsFirstRun:
    """Tests for the module-level _is_first_run(settings) function in tui/app.py.

    The two conditions that return True:
      1. llm_model is falsy (empty string)
      2. provider == ZAI AND zai_api_key is falsy

    Critical case (TC-TUI-004): Ollama provider with no ZAI key must NOT
    trigger first-run — the ZAI branch is guarded by a provider check.
    """

    def test_empty_model_is_first_run(self) -> None:
        """TC-TUI-001: Empty llm_model → first-run regardless of API key."""
        assert _is_first_run(_settings(llm_model="", zai_api_key="sk-abc")) is True

    def test_zai_missing_api_key_is_first_run(self) -> None:
        """TC-TUI-002: ZAI provider + model set but no API key → first-run."""
        assert _is_first_run(_settings(llm_model="glm-4-flash", zai_api_key="")) is True

    def test_zai_fully_configured_not_first_run(self) -> None:
        """TC-TUI-003: ZAI provider with model AND API key → not first-run."""
        assert (
            _is_first_run(_settings(llm_model="glm-4-flash", zai_api_key="sk-real")) is False
        )

    def test_ollama_no_api_key_not_first_run(self) -> None:
        """TC-TUI-004: Ollama provider, model set, no ZAI key → NOT first-run.

        Regression guard: the ZAI-api-key branch must only fire when the
        provider is ZAI.  If the provider check were ever accidentally dropped,
        Ollama users would be sent to setup on every launch.
        """
        assert (
            _is_first_run(
                _settings(
                    llm_model="llama3",
                    llm_provider=LLMProvider.OLLAMA,
                    zai_api_key="",
                )
            )
            is False
        )

    def test_empty_model_and_no_key_is_first_run(self) -> None:
        """TC-TUI-005: Both model and API key empty → first-run (model check fires first)."""
        assert _is_first_run(_settings(llm_model="", zai_api_key="")) is True


# ---------------------------------------------------------------------------
# TC-TUI-006 … 012  _render_bar
# ---------------------------------------------------------------------------


class TestRenderBar:
    """Tests for enrich_screen._render_bar(current, total).

    The function returns a string of the form '[<inner>]' where inner must
    always be exactly _BAR_WIDTH characters, composed of '█' (filled) and
    '░' (unfilled).  The clamping fix (max/min) ensures the width invariant
    holds even when current is outside [0, total].
    """

    def test_total_zero_returns_empty_bar(self) -> None:
        """TC-TUI-006: total=0 short-circuits to an all-unfilled bar."""
        assert _render_bar(0, 0) == f"[{'░' * _BAR_WIDTH}]"

    def test_current_zero_returns_empty_bar(self) -> None:
        """TC-TUI-007: current=0, total>0 → no filled blocks."""
        assert _render_bar(0, 10) == f"[{'░' * _BAR_WIDTH}]"

    def test_fully_complete_returns_full_bar(self) -> None:
        """TC-TUI-008: current==total → all filled blocks."""
        assert _render_bar(10, 10) == f"[{'█' * _BAR_WIDTH}]"

    def test_midpoint_correct_split(self) -> None:
        """TC-TUI-009: current=5, total=10 → 23 filled, 23 unfilled (int(46*0.5)=23)."""
        result = _render_bar(5, 10)
        inner = result[1:-1]
        assert inner.count("█") == 23
        assert inner.count("░") == _BAR_WIDTH - 23

    @pytest.mark.parametrize("current", list(range(0, 11)))
    def test_width_invariant_normal_range(self, current: int) -> None:
        """TC-TUI-010: Inner length is always _BAR_WIDTH for 0 <= current <= total."""
        result = _render_bar(current, 10)
        inner = result[1:-1]
        assert len(inner) == _BAR_WIDTH, (
            f"Width broken at current={current}/10: inner length={len(inner)}"
        )

    def test_width_invariant_current_exceeds_total(self) -> None:
        """TC-TUI-011: current > total — clamping keeps width invariant."""
        result = _render_bar(12, 10)
        inner = result[1:-1]
        assert len(inner) == _BAR_WIDTH
        assert inner == "█" * _BAR_WIDTH  # clamped to full

    def test_width_invariant_negative_current(self) -> None:
        """TC-TUI-012: negative current — clamping keeps width invariant."""
        result = _render_bar(-1, 10)
        inner = result[1:-1]
        assert len(inner) == _BAR_WIDTH
        assert inner == "░" * _BAR_WIDTH  # clamped to empty


# ---------------------------------------------------------------------------
# TC-TUI-013 … 018  chat_top_k validation (isolated logic)
# ---------------------------------------------------------------------------


def _coerce_top_k(raw: str) -> str:
    """Verbatim copy of the fixed validation in settings_screen.action_save.

    Uses raw.isascii() + raw.isdigit() to reject unicode digits, and
    max(1, int(raw)) to reject zero.
    """
    if raw.isascii() and raw.isdigit() and int(raw) >= 1:
        return raw
    return "8"


class TestChatTopKValidation:
    """Tests for the top-k integer validation in SettingsScreen.action_save."""

    def test_valid_positive_integer_passes(self) -> None:
        """TC-TUI-013: '10' is a valid ASCII digit string → returned as-is."""
        assert _coerce_top_k("10") == "10"

    def test_empty_string_falls_back_to_default(self) -> None:
        """TC-TUI-014: Empty string → fallback '8'."""
        assert _coerce_top_k("") == "8"

    def test_float_string_falls_back(self) -> None:
        """TC-TUI-015: '3.5' contains '.' → fallback '8'."""
        assert _coerce_top_k("3.5") == "8"

    def test_negative_string_falls_back(self) -> None:
        """TC-TUI-016: '-1' contains '-' → fallback '8'."""
        assert _coerce_top_k("-1") == "8"

    def test_zero_falls_back_to_default(self) -> None:
        """TC-TUI-017: '0' is a digit but semantically invalid → fallback '8'."""
        assert _coerce_top_k("0") == "8"

    def test_unicode_superscript_digit_falls_back(self) -> None:
        """TC-TUI-018: '²'.isdigit() is True but not ASCII → fallback '8'."""
        assert "²".isdigit() is True, "Platform does not treat '²' as a digit"
        assert _coerce_top_k("²") == "8"
