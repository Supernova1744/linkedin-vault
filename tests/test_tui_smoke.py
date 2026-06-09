"""TUI mount smoke tests for ChatScreen and ConfigWizardScreen.

These tests use Textual's run_test() pilot to verify that compose() + on_mount()
execute cleanly and that the event wiring (switch toggling, radio switching) works
as expected — the failure surface that import-only checks miss.

No real filesystem writes or network calls are made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from linkedin_vault.config import LLMProvider, Settings

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
        # Point DB at tmp_path so get_db_path() never creates ~/.linkedin-vault
        "db_path": tmp_path / "vault.db",
        "data_dir": tmp_path,
    }
    defaults.update(kwargs)
    return Settings.model_construct(**defaults)


# ---------------------------------------------------------------------------
# ChatScreen mount tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_screen_mounts_with_model(tmp_path: Path) -> None:
    """ChatScreen: when a model is configured, input is enabled and log shows ready msg."""
    from textual.app import App
    from textual.widgets import Input, RichLog

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    settings = _settings(tmp_path, llm_model="glm-4-flash")

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with patch("linkedin_vault.config.load_settings", return_value=settings):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen), (
                f"Expected ChatScreen, got {type(screen).__name__}"
            )

            chat_input = screen.query_one("#chat-input", Input)
            assert not chat_input.disabled, "Input should be enabled when model is configured"

            log = screen.query_one("#chat-log", RichLog)
            assert log is not None


@pytest.mark.asyncio
async def test_chat_screen_mounts_without_model(tmp_path: Path) -> None:
    """ChatScreen: when no model is configured, error banner is visible and input disabled."""
    from textual.app import App
    from textual.widgets import Input, Static

    from linkedin_vault.tui.screens.chat_screen import ChatScreen

    # No model configured — get_chat_model() returns ""
    settings = _settings(tmp_path, llm_model="", chat_model="")

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ChatScreen())

    with patch("linkedin_vault.config.load_settings", return_value=settings):
        async with _TestApp().run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ChatScreen)

            chat_input = screen.query_one("#chat-input", Input)
            assert chat_input.disabled, "Input should be disabled when no model is configured"

            banner = screen.query_one("#no-model-banner", Static)
            assert "visible" in banner.classes, "Error banner should have class 'visible'"


# ---------------------------------------------------------------------------
# ConfigWizardScreen mount tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_wizard_mounts_cleanly(tmp_path: Path) -> None:
    """ConfigWizardScreen: mounts without error; key widget IDs exist."""
    from textual.app import App
    from textual.widgets import Switch

    from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

    settings = _settings(tmp_path)

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ConfigWizardScreen())

    with patch("linkedin_vault.tui.screens.config_wizard.load_settings", return_value=settings):
        async with _TestApp().run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            assert isinstance(screen, ConfigWizardScreen)

            # Core chat section widgets must all resolve
            screen.query_one("#chat-section")
            screen.query_one("#chat-use-same", Switch)
            screen.query_one("#chat-same-hint")
            screen.query_one("#chat-override-section")
            screen.query_one("#chat-top-k")


@pytest.mark.asyncio
async def test_config_wizard_chat_same_switch_toggles_override_section(tmp_path: Path) -> None:
    """Toggling 'use same provider' switch hides/shows the override section."""
    from textual.app import App
    from textual.widgets import Switch

    from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

    # Default: chat_provider=None, chat_model="" → switch starts ON (use-same)
    settings = _settings(tmp_path, chat_provider=None, chat_model="")

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ConfigWizardScreen())

    with patch("linkedin_vault.tui.screens.config_wizard.load_settings", return_value=settings):
        async with _TestApp().run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            override = screen.query_one("#chat-override-section")
            switch = screen.query_one("#chat-use-same", Switch)

            # Switch ON → override section hidden
            assert switch.value is True
            assert override.display is False, (
                "Override section should be hidden when 'use same' is ON"
            )

            # Toggle switch OFF → override section becomes visible
            switch.value = False
            await pilot.pause(0.1)

            assert override.display is True, (
                "Override section should be visible when 'use same' is OFF"
            )


@pytest.mark.asyncio
async def test_config_wizard_chat_radio_switches_provider_subsection(tmp_path: Path) -> None:
    """Switching chat provider radio shows correct sub-section (z.ai vs Ollama)."""
    from textual.app import App
    from textual.widgets import RadioButton, RadioSet, Switch

    from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

    # Start with override enabled (switch OFF) and ZAI chat provider
    settings = _settings(tmp_path, chat_provider=LLMProvider.ZAI, chat_model="glm-4-flash")

    class _TestApp(App):
        async def on_mount(self) -> None:
            await self.push_screen(ConfigWizardScreen())

    with patch("linkedin_vault.tui.screens.config_wizard.load_settings", return_value=settings):
        async with _TestApp().run_test(size=(100, 60)) as pilot:
            await pilot.pause(0.1)

            screen = pilot.app.screen
            switch = screen.query_one("#chat-use-same", Switch)

            # Force switch OFF so override section is visible
            switch.value = False
            await pilot.pause(0.1)

            zai_section = screen.query_one("#chat-zai-section")
            ollama_section = screen.query_one("#chat-ollama-section")

            # With ZAI selected: z.ai section visible, ollama section hidden
            assert zai_section.display is True
            assert ollama_section.display is False

            # Switch chat provider to Ollama
            screen.query_one("#chat-provider-radio", RadioSet)  # ensure widget exists
            ollama_radio = screen.query_one("#chat-radio-ollama", RadioButton)
            ollama_radio.value = True
            await pilot.pause(0.1)

            # After selecting Ollama: ollama section visible, zai section hidden
            assert ollama_section.display is True
            assert zai_section.display is False
