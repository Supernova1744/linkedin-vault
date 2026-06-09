from __future__ import annotations

import contextlib
from collections.abc import Iterable
from typing import ClassVar

import httpx
from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import (
    Button,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
    Switch,
)

from linkedin_vault.config import LLMProvider, load_settings, save_settings_to_file
from linkedin_vault.tui.vault_screen import VaultScreen
from linkedin_vault.utils.logging import get_logger

logger = get_logger(__name__)

ZAI_MODELS = [
    "glm-4",
    "glm-4-flash",
    "glm-4-air",
    "glm-4-airx",
    "glm-3-turbo",
]


class ConfigWizardScreen(VaultScreen):
    SCREEN_TITLE = "Settings"
    BOTTOM_HINTS = "  [#CC785C]esc/q[/#CC785C] Back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    ConfigWizardScreen #wizard-scroll { height: 1fr; padding: 0 4; }

    ConfigWizardScreen #title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
        padding-top: 1;
    }

    ConfigWizardScreen #provider-section { margin-bottom: 1; }
    ConfigWizardScreen #zai-section, ConfigWizardScreen #ollama-section {
        margin-top: 1;
        margin-bottom: 1;
    }

    ConfigWizardScreen #chat-section {
        margin-top: 2;
        border-top: dashed $accent;
        padding-top: 1;
    }

    ConfigWizardScreen #chat-override-section { margin-top: 1; }
    ConfigWizardScreen #chat-same-hint { color: $text-muted; margin-bottom: 1; }

    ConfigWizardScreen Label { margin-bottom: 1; }
    ConfigWizardScreen Input { margin-bottom: 1; }
    ConfigWizardScreen Select { margin-bottom: 1; }
    ConfigWizardScreen Switch { margin-bottom: 1; }

    ConfigWizardScreen #btn-row {
        layout: horizontal;
        margin-top: 1;
        margin-bottom: 2;
    }

    ConfigWizardScreen Button { margin-right: 1; }

    ConfigWizardScreen #status-msg {
        color: $success;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._ollama_models: list[tuple[str, str]] = []
        self._chat_ollama_models: list[tuple[str, str]] = []

    def compose_content(self) -> Iterable[Widget]:
        from textual.containers import VerticalScroll

        with VerticalScroll(id="wizard-scroll"):
            yield Static("Provider & Model Configuration", id="title")

            with Static(id="provider-section"):
                yield Label("LLM Provider:")
                with RadioSet(id="provider-radio"):
                    yield RadioButton(
                        "z.ai (cloud)",
                        id="radio-zai",
                        value=self._settings.llm_provider == LLMProvider.ZAI,
                    )
                    yield RadioButton(
                        "Ollama (local)",
                        id="radio-ollama",
                        value=self._settings.llm_provider == LLMProvider.OLLAMA,
                    )

            with Static(id="zai-section"):
                yield Label("z.ai API Key:")
                yield Input(
                    value=self._settings.zai_api_key,
                    placeholder="your_api_key_here",
                    password=True,
                    id="zai-api-key",
                )
                yield Label("Model:")
                if self._settings.llm_model in ZAI_MODELS:
                    current_model = self._settings.llm_model
                else:
                    current_model = ZAI_MODELS[1]
                yield Select(
                    options=[(m, m) for m in ZAI_MODELS],
                    value=current_model,
                    id="zai-model-select",
                )

            with Static(id="ollama-section"):
                yield Label("Ollama Base URL:")
                yield Input(
                    value=self._settings.ollama_base_url,
                    placeholder="http://localhost:11434",
                    id="ollama-url",
                )
                yield Label("Model (fetched from Ollama):")
                yield Select(
                    options=[],
                    id="ollama-model-select",
                    prompt="Fetching models...",
                )
                yield Button("Refresh Models", id="btn-refresh-ollama", variant="default")

            with Static(id="chat-section"):
                yield Label("─── Chat Settings ───")
                yield Label("Use same provider/model as enrichment:")
                chat_use_same = (
                    self._settings.chat_provider is None and not self._settings.chat_model
                )
                yield Switch(value=chat_use_same, id="chat-use-same")
                yield Static("", id="chat-same-hint")

                with Static(id="chat-override-section"):
                    yield Label("Chat Provider:")
                    chat_provider = self._settings.chat_provider or LLMProvider.ZAI
                    with RadioSet(id="chat-provider-radio"):
                        yield RadioButton(
                            "z.ai (cloud)",
                            id="chat-radio-zai",
                            value=chat_provider == LLMProvider.ZAI,
                        )
                        yield RadioButton(
                            "Ollama (local)",
                            id="chat-radio-ollama",
                            value=chat_provider == LLMProvider.OLLAMA,
                        )

                    with Static(id="chat-zai-section"):
                        yield Label("Chat Model (z.ai):")
                        chat_zai_model = (
                            self._settings.chat_model
                            if self._settings.chat_model in ZAI_MODELS
                            else ZAI_MODELS[1]
                        )
                        yield Select(
                            options=[(m, m) for m in ZAI_MODELS],
                            value=chat_zai_model,
                            id="chat-zai-model-select",
                        )

                    with Static(id="chat-ollama-section"):
                        yield Label("Chat Model (Ollama):")
                        yield Select(
                            options=[],
                            id="chat-ollama-model-select",
                            prompt="Fetching models...",
                        )

                yield Label("Context posts (top-K, 1-20):")
                yield Input(
                    value=str(self._settings.chat_top_k),
                    id="chat-top-k",
                    placeholder="8",
                )

            with Static(id="btn-row"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

            yield Static("", id="status-msg")

    def on_mount(self) -> None:
        self._sync_provider_visibility()
        self._sync_chat_visibility()
        if self._settings.llm_provider == LLMProvider.OLLAMA:
            self.app.call_later(self._fetch_ollama_models)

    def _sync_provider_visibility(self) -> None:
        is_zai = self._current_provider() == LLMProvider.ZAI
        self.query_one("#zai-section").display = is_zai
        self.query_one("#ollama-section").display = not is_zai

    def _sync_chat_visibility(self) -> None:
        use_same = self.query_one("#chat-use-same", Switch).value
        override_section = self.query_one("#chat-override-section")
        override_section.display = not use_same

        hint = self.query_one("#chat-same-hint", Static)
        if use_same:
            provider = self._settings.llm_provider.value
            model = self._settings.llm_model or "(not set)"
            hint.update(f"[dim]Using enrichment provider: {provider} / {model}[/dim]")
        else:
            hint.update("")
            self._sync_chat_provider_visibility()

    def _sync_chat_provider_visibility(self) -> None:
        chat_provider = self._current_chat_provider()
        self.query_one("#chat-zai-section").display = chat_provider == LLMProvider.ZAI
        self.query_one("#chat-ollama-section").display = chat_provider == LLMProvider.OLLAMA
        if chat_provider == LLMProvider.OLLAMA and not self._chat_ollama_models:
            self.app.call_later(self._fetch_chat_ollama_models)

    def _current_provider(self) -> LLMProvider:
        radio_set = self.query_one("#provider-radio", RadioSet)
        selected = radio_set.pressed_button
        if selected is None:
            return LLMProvider.ZAI
        return LLMProvider.ZAI if selected.id == "radio-zai" else LLMProvider.OLLAMA

    def _current_chat_provider(self) -> LLMProvider:
        radio_set = self.query_one("#chat-provider-radio", RadioSet)
        selected = radio_set.pressed_button
        if selected is None:
            return LLMProvider.ZAI
        return LLMProvider.ZAI if selected.id == "chat-radio-zai" else LLMProvider.OLLAMA

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "chat-use-same":
            self._sync_chat_visibility()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "provider-radio":
            self._sync_provider_visibility()
            if self._current_provider() == LLMProvider.OLLAMA and not self._ollama_models:
                self.app.call_later(self._fetch_ollama_models)
        elif event.radio_set.id == "chat-provider-radio":
            self._sync_chat_provider_visibility()

    async def _fetch_ollama_models(self) -> None:
        ollama_url_input = self.query_one("#ollama-url", Input)
        base_url = ollama_url_input.value.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models: list[str] = [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Could not fetch Ollama models: %s", exc)
            models = []

        self._ollama_models = [(m, m) for m in models]
        if not self.is_attached:
            return

        captured_models = list(models)

        def _apply() -> None:
            if not self.is_attached:
                return
            try:
                select = self.query_one("#ollama-model-select", Select)
            except Exception:
                return
            if captured_models:
                current = self._settings.llm_model
                select.set_options([(m, m) for m in captured_models])
                if current in captured_models:
                    select.value = current
                with contextlib.suppress(Exception):
                    self.query_one("#status-msg", Static).update("")
            else:
                select.set_options([("(no models found)", "")])
                with contextlib.suppress(Exception):
                    self.query_one("#status-msg", Static).update(
                        "[yellow]Could not reach Ollama — is it running?[/yellow]"
                    )

        self.call_after_refresh(_apply)

    async def _fetch_chat_ollama_models(self) -> None:
        ollama_url_input = self.query_one("#ollama-url", Input)
        base_url = ollama_url_input.value.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models: list[str] = [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Could not fetch Ollama models for chat: %s", exc)
            models = []

        self._chat_ollama_models = [(m, m) for m in models]
        if not self.is_attached:
            return

        captured_models = list(models)

        def _apply() -> None:
            if not self.is_attached:
                return
            try:
                select = self.query_one("#chat-ollama-model-select", Select)
            except Exception:
                return
            if captured_models:
                current = self._settings.chat_model
                select.set_options([(m, m) for m in captured_models])
                if current in captured_models:
                    select.value = current
            else:
                select.set_options([("(no models found)", "")])

        self.call_after_refresh(_apply)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-cancel":
            self.action_back()
        elif button_id == "btn-refresh-ollama":
            self.query_one("#status-msg", Static).update("Fetching models...")
            await self._fetch_ollama_models()
        elif button_id == "btn-save":
            await self._save()

    async def _save(self) -> None:
        provider = self._current_provider()
        to_save: dict[str, str] = {"LLM_PROVIDER": provider.value}

        if provider == LLMProvider.ZAI:
            api_key = self.query_one("#zai-api-key", Input).value.strip()
            model_select = self.query_one("#zai-model-select", Select)
            model = (
                str(model_select.value) if model_select.value is not Select.BLANK else ZAI_MODELS[1]
            )
            if not api_key:
                self.query_one("#status-msg", Static).update("[red]z.ai API key is required.[/red]")
                return
            to_save["ZAI_API_KEY"] = api_key
            to_save["LLM_MODEL"] = model
        else:
            ollama_url = self.query_one("#ollama-url", Input).value.strip()
            model_select = self.query_one("#ollama-model-select", Select)
            model = str(model_select.value) if model_select.value is not Select.BLANK else ""
            to_save["OLLAMA_BASE_URL"] = ollama_url
            to_save["LLM_MODEL"] = model

        top_k_raw = self.query_one("#chat-top-k", Input).value.strip()
        try:
            top_k = int(top_k_raw)
            if not (1 <= top_k <= 20):
                raise ValueError
        except ValueError:
            self.query_one("#status-msg", Static).update(
                "[red]Chat top-K must be an integer between 1 and 20.[/red]"
            )
            return
        to_save["CHAT_TOP_K"] = str(top_k)

        use_same = self.query_one("#chat-use-same", Switch).value
        if use_same:
            to_save["CHAT_PROVIDER"] = ""
            to_save["CHAT_MODEL"] = ""
        else:
            chat_provider = self._current_chat_provider()
            to_save["CHAT_PROVIDER"] = chat_provider.value
            if chat_provider == LLMProvider.ZAI:
                chat_model_select = self.query_one("#chat-zai-model-select", Select)
                to_save["CHAT_MODEL"] = (
                    str(chat_model_select.value)
                    if chat_model_select.value is not Select.BLANK
                    else ZAI_MODELS[1]
                )
            else:
                chat_model_select = self.query_one("#chat-ollama-model-select", Select)
                to_save["CHAT_MODEL"] = (
                    str(chat_model_select.value)
                    if chat_model_select.value is not Select.BLANK
                    else ""
                )

        try:
            save_settings_to_file(to_save)
            self.query_one("#status-msg", Static).update(
                "[green]Settings saved to ~/.linkedin-vault/.env[/green]"
            )
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)
            self.query_one("#status-msg", Static).update(f"[red]Error saving settings: {exc}[/red]")

    def action_back(self) -> None:
        self.app.pop_screen()
