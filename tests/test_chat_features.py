"""TUI feature tests for ChatScreen.

Covers three features introduced in the chat screen rewrite:
  A. Persistent chat memory (DB history loaded on mount)
  B. Copy-last-answer via ctrl+y
  C. Input history navigation (Up/Down keys, hint widget, dedup)

All tests use Textual's run_test() pilot and patch DB / config to avoid
real filesystem or network calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin_vault.config import LLMProvider, Settings
from linkedin_vault.db.database import DatabaseManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(tmp_path: Path, **kwargs: Any) -> Settings:
    """Build a Settings via model_construct — avoids reading .env files."""
    defaults: dict[str, Any] = {
        "llm_provider": LLMProvider.ZAI,
        "llm_model": "glm-4-flash",
        "zai_api_key": "sk-test-key",
        "zai_base_url": "https://api.z.ai/v1",
        "ollama_base_url": "http://localhost:11434",
        "chat_top_k": 8,
        "chat_model": "",
        "chat_provider": None,
        # Point DB at tmp_path so get_db_path() never touches ~/.linkedin-vault
        "db_path": tmp_path / "vault.db",
        "data_dir": tmp_path,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


# ---------------------------------------------------------------------------
# Feature B: Copy last answer (ctrl+y)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_copy_answer_when_no_answer(tmp_path: Path) -> None:
    """ctrl+y with no prior answer fires a warning notify; clipboard is not touched."""
    from textual.app import App

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(DatabaseManager, "get_chat_history", new_callable=AsyncMock, return_value=[]),
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)

            # Verify initial state — no answer stored yet
            assert screen._last_answer == ""

            # Replace notify + clipboard with spies
            mock_notify = MagicMock()
            screen.notify = mock_notify
            pilot.app.copy_to_clipboard = MagicMock()

            await pilot.press("ctrl+y")
            await pilot.pause(0.1)

            # Warning branch must have fired
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args
            assert call_kwargs.args[0] == "Nothing to copy yet."
            assert call_kwargs.kwargs.get("severity") == "warning"

            # Clipboard must NOT have been touched
            pilot.app.copy_to_clipboard.assert_not_called()


# ---------------------------------------------------------------------------
# Feature C: Input history navigation — hint visibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_hint_hidden_initially(tmp_path: Path) -> None:
    """#history-hint has display=False immediately after mounting ChatScreen."""
    from textual.app import App
    from textual.widgets import Static

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(DatabaseManager, "get_chat_history", new_callable=AsyncMock, return_value=[]),
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            hint = screen.query_one("#history-hint", Static)
            assert hint.display is False, "#history-hint should be hidden on mount"


@pytest.mark.asyncio
async def test_navigate_history_updates_hint(tmp_path: Path) -> None:
    """navigate_history('up') with items in _input_history adds .active to #history-hint."""
    from textual.app import App
    from textual.widgets import Static

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(DatabaseManager, "get_chat_history", new_callable=AsyncMock, return_value=[]),
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)

            # Seed the in-session history directly
            screen._input_history = ["first question", "second question"]

            # Navigate up (towards older entries)
            screen.navigate_history("up")
            await pilot.pause(0.05)

            hint = screen.query_one("#history-hint", Static)
            assert "active" in hint.classes, (
                "#history-hint should gain class 'active' when browsing history"
            )
            assert hint.display is True, "#history-hint should become visible when browsing history"


@pytest.mark.asyncio
async def test_navigate_history_down_restores_stash(tmp_path: Path) -> None:
    """Navigating down past the newest entry restores the stashed draft and hides hint."""
    from textual.app import App
    from textual.widgets import Static

    from linkedin_vault.tui.screens.chat_screen import ChatScreen, HistoryInput

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(DatabaseManager, "get_chat_history", new_callable=AsyncMock, return_value=[]),
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)

            # Simulate state after one Up press: one history entry, stash set,
            # index pointing at the single entry.
            screen._input_history = ["previous question"]
            screen._history_stash = "my draft text"
            screen._history_index = 0

            # Mark the hint as active (as it would be after an Up press)
            hint = screen.query_one("#history-hint", Static)
            hint.add_class("active")
            await pilot.pause(0.05)

            # Navigate down past the newest — should restore stash and hide hint
            screen.navigate_history("down")
            await pilot.pause(0.05)

            chat_input = screen.query_one("#chat-input", HistoryInput)
            assert chat_input.value == "my draft text", (
                "Input should be restored to stashed draft after navigating past end"
            )
            assert screen._history_index == -1, (
                "_history_index should reset to -1 after restoring stash"
            )
            assert "active" not in hint.classes, (
                "#history-hint should lose class 'active' after stash restoration"
            )


# ---------------------------------------------------------------------------
# Feature C: Input history navigation — dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_input_history_dedup(tmp_path: Path) -> None:
    """Submitting the same question twice in a row stores only one entry in _input_history."""
    from textual.app import App
    from textual.widgets import Input

    from linkedin_vault.tui.screens.chat_screen import ChatScreen, HistoryInput

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(DatabaseManager, "get_chat_history", new_callable=AsyncMock, return_value=[]),
        patch.object(ChatScreen, "_send_message"),
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)
            assert screen._input_history == []

            chat_input = screen.query_one("#chat-input", HistoryInput)

            # Drive on_input_submitted directly to avoid pilot focus ambiguity
            event1 = Input.Submitted(chat_input, "same question")
            screen.on_input_submitted(event1)

            event2 = Input.Submitted(chat_input, "same question")
            screen.on_input_submitted(event2)

            await pilot.pause(0.1)

            assert len(screen._input_history) == 1, (
                "Consecutive identical submissions must be deduplicated"
            )
            assert screen._input_history[0] == "same question"


# ---------------------------------------------------------------------------
# Feature A: Chat history loaded on mount
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_history_loaded_on_mount(tmp_path: Path) -> None:
    """When get_chat_history returns turns they are written to the RichLog on mount."""
    from textual.app import App
    from textual.widgets import RichLog

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    settings = _settings(tmp_path)

    sample_history = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a programming language."},
    ]

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with (
        patch("linkedin_vault.config.load_settings", return_value=settings),
        patch.object(DatabaseManager, "initialize_db", new_callable=AsyncMock),
        patch.object(
            DatabaseManager,
            "get_chat_history",
            new_callable=AsyncMock,
            return_value=sample_history,
        ),
        # Intercept RichLog.write at class level to capture written strings.
        # Dropping wraps= because the unbound method would be called without
        # `self`, causing a TypeError.  We only need to record args here.
        patch.object(RichLog, "write") as mock_write,
    ):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)

            # Each call arrives as mock_write(content) — args[0] is content
            written = [str(call.args[0]) for call in mock_write.call_args_list if call.args]
            joined = " ".join(written)

            assert "loaded from history" in joined, (
                "The 'loaded from history' separator must be written to the log "
                f"when prior turns exist. Actual writes: {written!r}"
            )
            # Both history turns must also appear
            assert "What is Python?" in joined
            assert "Python is a programming language." in joined
