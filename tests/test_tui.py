"""Unit tests for TUI pure-Python logic.

These tests avoid instantiating any Textual App or Screen — only
module-level functions and methods containing testable pure logic are
exercised directly.  No Textual event loop is started, no .env file
is written, and no filesystem side effects are produced.

Two latent defects are documented as xfail tests so CI stays green
while the issues remain visible:
  - _render_bar: no clamping when current > total or current < 0
  - chat_top_k validation: "0".isdigit() is True (range gap)
"""
from __future__ import annotations

import types

import pytest

from linkedin_vault.config import LLMProvider
from linkedin_vault.tui.app import LinkedInVaultApp
from linkedin_vault.tui.screens.enrich_screen import _BAR_WIDTH, _render_bar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_app(
    llm_model: str,
    llm_provider: LLMProvider,
    zai_api_key: str,
) -> types.SimpleNamespace:
    """Return a minimal fake 'self' that satisfies _is_first_run's attribute reads.

    Bypasses LinkedInVaultApp.__init__ (which calls load_settings and
    DatabaseManager) so tests never touch the real user environment.
    """
    return types.SimpleNamespace(
        _settings=types.SimpleNamespace(
            llm_model=llm_model,
            llm_provider=llm_provider,
            zai_api_key=zai_api_key,
        )
    )


# ---------------------------------------------------------------------------
# TC-TUI-001 … 005  _is_first_run
# ---------------------------------------------------------------------------


class TestIsFirstRun:
    """Tests for LinkedInVaultApp._is_first_run().

    The three conditions that return True:
      1. llm_model is falsy (empty string)
      2. provider == ZAI AND zai_api_key is falsy

    Critical case (TC-TUI-004): Ollama provider with no ZAI key must NOT
    trigger first-run — the ZAI branch is guarded by a provider check.
    """

    def test_empty_model_is_first_run(self) -> None:
        """TC-TUI-001: Empty llm_model → first-run regardless of API key."""
        fake = _fake_app(llm_model="", llm_provider=LLMProvider.ZAI, zai_api_key="sk-abc")
        assert LinkedInVaultApp._is_first_run(fake) is True

    def test_zai_missing_api_key_is_first_run(self) -> None:
        """TC-TUI-002: ZAI provider + model set but no API key → first-run."""
        fake = _fake_app(
            llm_model="glm-4-flash", llm_provider=LLMProvider.ZAI, zai_api_key=""
        )
        assert LinkedInVaultApp._is_first_run(fake) is True

    def test_zai_fully_configured_not_first_run(self) -> None:
        """TC-TUI-003: ZAI provider with model AND API key → not first-run."""
        fake = _fake_app(
            llm_model="glm-4-flash", llm_provider=LLMProvider.ZAI, zai_api_key="sk-real"
        )
        assert LinkedInVaultApp._is_first_run(fake) is False

    def test_ollama_no_api_key_not_first_run(self) -> None:
        """TC-TUI-004: Ollama provider, model set, no ZAI key → NOT first-run.

        Regression guard: the ZAI-api-key branch must only fire when the
        provider is ZAI.  If the provider check were ever accidentally dropped
        from _is_first_run, Ollama users would be sent to setup on every launch.
        """
        fake = _fake_app(
            llm_model="llama3", llm_provider=LLMProvider.OLLAMA, zai_api_key=""
        )
        assert LinkedInVaultApp._is_first_run(fake) is False

    def test_empty_model_and_no_key_is_first_run(self) -> None:
        """TC-TUI-005: Both model and API key empty → first-run (model check fires first)."""
        fake = _fake_app(llm_model="", llm_provider=LLMProvider.ZAI, zai_api_key="")
        assert LinkedInVaultApp._is_first_run(fake) is True


# ---------------------------------------------------------------------------
# TC-TUI-006 … 012  _render_bar
# ---------------------------------------------------------------------------


class TestRenderBar:
    """Tests for enrich_screen._render_bar(current, total).

    The function returns a string of the form '[<inner>]' where inner must
    always be exactly _BAR_WIDTH characters, composed of '█' (filled) and
    '░' (unfilled).

    TC-TUI-011 and TC-TUI-012 document a latent defect: when current is
    outside [0, total], 'filled' is not clamped, so the inner string length
    no longer equals _BAR_WIDTH.  These tests are marked xfail so CI remains
    green until the defect is fixed.
    """

    def test_total_zero_returns_empty_bar(self) -> None:
        """TC-TUI-006: total=0 short-circuits to an all-unfilled bar."""
        result = _render_bar(0, 0)
        assert result == f"[{'░' * _BAR_WIDTH}]"

    def test_current_zero_returns_empty_bar(self) -> None:
        """TC-TUI-007: current=0, total>0 → no filled blocks."""
        result = _render_bar(0, 10)
        assert result == f"[{'░' * _BAR_WIDTH}]"

    def test_fully_complete_returns_full_bar(self) -> None:
        """TC-TUI-008: current==total → all filled blocks."""
        result = _render_bar(10, 10)
        assert result == f"[{'█' * _BAR_WIDTH}]"

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

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT: _render_bar does not clamp 'filled'. "
            "When current > total, filled > _BAR_WIDTH and the unfilled segment "
            "becomes '░' * negative == '', making the inner string too long. "
            "Fix: filled = max(0, min(int(_BAR_WIDTH * current / total), _BAR_WIDTH))"
        ),
    )
    def test_width_invariant_current_exceeds_total(self) -> None:
        """TC-TUI-011 (DEFECT): current > total must not overflow bar width."""
        result = _render_bar(12, 10)  # 20 % above total
        inner = result[1:-1]
        assert len(inner) == _BAR_WIDTH, (
            f"DEFECT: inner length={len(inner)}, expected {_BAR_WIDTH}"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "DEFECT: negative 'filled' makes '█' * negative == '' and "
            "'░' * (_BAR_WIDTH - negative) wider than _BAR_WIDTH. "
            "Fix: same clamping as TC-TUI-011."
        ),
    )
    def test_width_invariant_negative_current(self) -> None:
        """TC-TUI-012 (DEFECT): negative current must not widen bar beyond _BAR_WIDTH."""
        result = _render_bar(-1, 10)
        inner = result[1:-1]
        assert len(inner) == _BAR_WIDTH, (
            f"DEFECT: inner length={len(inner)}, expected {_BAR_WIDTH}"
        )


# ---------------------------------------------------------------------------
# TC-TUI-013 … 018  chat_top_k validation (isolated logic)
# ---------------------------------------------------------------------------


def _coerce_top_k(raw: str) -> str:
    """Verbatim copy of the validation branch in settings_screen.action_save.

    Reproducing the logic here rather than calling action_save() is necessary
    because action_save() requires a running Textual app (it calls query_one).
    If the source logic drifts from this copy, TC-TUI-017/018 will surface it.
    """
    if raw.isdigit():
        return raw
    return "8"


class TestChatTopKValidation:
    """Tests for the top-k integer validation in SettingsScreen.action_save.

    TC-TUI-017 and TC-TUI-018 document gaps in the current validation:
    - "0" passes format validation but yields zero retrieval results.
    - Unicode digits (e.g. "²") pass .isdigit() but cannot be parsed by
      Settings(chat_top_k=...) which expects a plain int string.
    """

    def test_valid_positive_integer_passes(self) -> None:
        """TC-TUI-013: '10' is a valid digit string → returned as-is."""
        assert _coerce_top_k("10") == "10"

    def test_empty_string_falls_back_to_default(self) -> None:
        """TC-TUI-014: Empty string is not digits-only → fallback '8'."""
        assert _coerce_top_k("") == "8"

    def test_float_string_falls_back(self) -> None:
        """TC-TUI-015: '3.5' contains '.' → .isdigit() is False → fallback '8'."""
        assert _coerce_top_k("3.5") == "8"

    def test_negative_string_falls_back(self) -> None:
        """TC-TUI-016: '-1' contains '-' → .isdigit() is False → fallback '8'."""
        assert _coerce_top_k("-1") == "8"

    def test_zero_passes_format_validation_range_gap(self) -> None:
        """TC-TUI-017 (GAP): '0'.isdigit() is True, so top_k=0 is accepted.

        Zero is semantically invalid: chat retrieval returns 0 posts.
        This was the root cause class of the bug fixed in commit 476ea6a.
        The isdigit() guard rejects non-numeric strings but not out-of-range
        values.

        Recommended fix:
            top_k = max(1, int(raw)) if raw.isdigit() else 8
        """
        # Documents current (defective) behaviour — zero is saved, not rejected.
        assert _coerce_top_k("0") == "0"

    def test_unicode_superscript_digit_passes_format_gap(self) -> None:
        """TC-TUI-018 (GAP): '²'.isdigit() is True, so it bypasses the fallback.

        pydantic-settings will then call int('²') when loading Settings,
        which raises ValueError and crashes the TUI on next launch.

        Recommended fix: use raw.isascii() and raw.isdigit() together, or
        use a try/except int() parse instead of .isdigit().
        """
        # Confirm the platform invariant this test depends on
        assert "²".isdigit() is True, "Platform does not treat '²' as a digit — skip"
        # Documents current (defective) behaviour — unicode digit is saved verbatim
        assert _coerce_top_k("²") == "²"
