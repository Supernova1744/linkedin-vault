from __future__ import annotations

from typing import ClassVar

import httpx
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, Select, Static

from linkedin_vault.config import LLMProvider, load_settings, save_settings_to_file
from linkedin_vault.utils.logging import get_logger

logger = get_logger(__name__)

ZAI_MODELS = [
    "glm-4",
    "glm-4-flash",
    "glm-4-air",
    "glm-4-airx",
    "glm-4-long",
    "glm-3-turbo",
]

CHAT_PROVIDER_OPTIONS: list[tuple[str, str]] = [
    ("inherit (use enrichment setting)", ""),
    ("z.ai", "zai"),
    ("Ollama", "ollama"),
]

_CSS = """
SettingsScreen {
    background: $surface;
}

#title-line {
    color: $text-muted;
    padding: 0 2;
    height: 1;
}

.separator {
    color: $text-muted;
    height: 1;
}

.section-header {
    padding: 0 2;
    color: $text-muted;
    height: 1;
    margin-top: 1;
    margin-bottom: 1;
}

.field-row {
    layout: horizontal;
    height: auto;
    padding: 0 2;
    margin-bottom: 1;
}

.field-label {
    width: 22;
    color: $text-muted;
    padding-top: 1;
}

.field-value {
    width: 1fr;
}

#status-line {
    padding: 0 2;
    color: $text-muted;
    margin-top: 1;
    height: 1;
}

#zai-section {
    height: auto;
}

#ollama-section {
    height: auto;
}

#chat-section {
    height: auto;
}
"""


class SettingsScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "back", "Back"),
        Binding("r", "refresh_models", "Refresh Ollama"),
    ]

    DEFAULT_CSS = _CSS

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._ollama_models: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        settings = self._settings

        yield Static("settings", id="title-line")
        yield Static("─" * 80, classes="separator")
        yield Static("─── enrichment ─────────────────────────────────────────────────────", classes="section-header")

        # Provider
        with Static(classes="field-row"):
            yield Label("provider", classes="field-label")
            yield Select(
                options=[
                    ("z.ai (cloud)", "zai"),
                    ("Ollama (local)", "ollama"),
                ],
                value=settings.llm_provider.value,
                id="provider-select",
                classes="field-value",
            )

        # z.ai enrichment section
        with Static(id="zai-section"):
            with Static(classes="field-row"):
                yield Label("z.ai API key", classes="field-label")
                yield Input(
                    value=settings.zai_api_key,
                    placeholder="your_api_key_here",
                    password=True,
                    id="zai-api-key",
                    classes="field-value",
                )
            with Static(classes="field-row"):
                current_zai_model = (
                    settings.llm_model if settings.llm_model in ZAI_MODELS else ZAI_MODELS[1]
                )
                yield Label("z.ai model", classes="field-label")
                yield Select(
                    options=[(m, m) for m in ZAI_MODELS],
                    value=current_zai_model,
                    id="zai-model-select",
                    classes="field-value",
                )

        # Ollama enrichment section
        with Static(id="ollama-section"):
            with Static(classes="field-row"):
                yield Label("Ollama URL", classes="field-label")
                yield Input(
                    value=settings.ollama_base_url,
                    placeholder="http://localhost:11434",
                    id="ollama-url",
                    classes="field-value",
                )
            with Static(classes="field-row"):
                yield Label("Ollama model", classes="field-label")
                yield Select(
                    options=[],
                    id="ollama-model-select",
                    prompt="press r to fetch models",
                    classes="field-value",
                )

        yield Static("─── chat (optional overrides) ──────────────────────────────────────", classes="section-header")

        with Static(id="chat-section"):
            # Chat provider
            chat_provider_val = settings.chat_provider.value if settings.chat_provider else ""
            with Static(classes="field-row"):
                yield Label("chat provider", classes="field-label")
                yield Select(
                    options=CHAT_PROVIDER_OPTIONS,
                    value=chat_provider_val,
                    id="chat-provider-select",
                    classes="field-value",
                )
            # Chat model
            with Static(classes="field-row"):
                yield Label("chat model", classes="field-label")
                yield Input(
                    value=settings.chat_model,
                    placeholder=f"inherit ({settings.llm_model or 'not set'})",
                    id="chat-model",
                    classes="field-value",
                )
            # Chat top-k
            with Static(classes="field-row"):
                yield Label("chat top-k", classes="field-label")
                yield Input(
                    value=str(settings.chat_top_k),
                    placeholder="8",
                    id="chat-top-k",
                    classes="field-value",
                )

        yield Static("─" * 80, classes="separator")
        yield Static("", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_provider_visibility()
        if self._settings.llm_provider == LLMProvider.OLLAMA:
            self.call_later(self._fetch_ollama_models)

    def _sync_provider_visibility(self) -> None:
        is_zai = self._current_provider() == LLMProvider.ZAI
        self.query_one("#zai-section").display = is_zai
        self.query_one("#ollama-section").display = not is_zai

    def _current_provider(self) -> LLMProvider:
        sel = self.query_one("#provider-select", Select)
        return LLMProvider.OLLAMA if sel.value == "ollama" else LLMProvider.ZAI

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider-select":
            self._sync_provider_visibility()
            if self._current_provider() == LLMProvider.OLLAMA and not self._ollama_models:
                self.call_later(self._fetch_ollama_models)

    async def _fetch_ollama_models(self) -> None:
        self._set_status("Fetching Ollama models...")
        ollama_url_input = self.query_one("#ollama-url", Input)
        base_url = ollama_url_input.value.rstrip("/") or "http://localhost:11434"
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
        select = self.query_one("#ollama-model-select", Select)

        if models:
            current = self._settings.llm_model
            select.set_options(self._ollama_models)
            if current in models:
                select.value = current
            self._set_status("")
        else:
            select.set_options([("(no models found)", "(none)")])
            self._set_status("Could not reach Ollama — is it running?  (press r to retry)")

    async def action_save(self) -> None:
        provider = self._current_provider()
        to_save: dict[str, str] = {"LLM_PROVIDER": provider.value}

        if provider == LLMProvider.ZAI:
            api_key = self.query_one("#zai-api-key", Input).value.strip()
            model_select = self.query_one("#zai-model-select", Select)
            model = str(model_select.value) if model_select.value else ZAI_MODELS[1]
            if not api_key:
                self._set_status("z.ai API key is required.")
                return
            to_save["ZAI_API_KEY"] = api_key
            to_save["LLM_MODEL"] = model
        else:
            ollama_url = self.query_one("#ollama-url", Input).value.strip()
            model_select = self.query_one("#ollama-model-select", Select)
            raw = model_select.value
            model = str(raw) if raw and raw != "(none)" else ""
            to_save["OLLAMA_BASE_URL"] = ollama_url
            to_save["LLM_MODEL"] = model

        # Chat overrides
        chat_provider_sel = self.query_one("#chat-provider-select", Select)
        chat_provider_raw = chat_provider_sel.value
        to_save["CHAT_PROVIDER"] = str(chat_provider_raw) if chat_provider_raw else ""

        chat_model = self.query_one("#chat-model", Input).value.strip()
        to_save["CHAT_MODEL"] = chat_model  # empty means inherit

        chat_top_k_str = self.query_one("#chat-top-k", Input).value.strip()
        if chat_top_k_str.isdigit():
            to_save["CHAT_TOP_K"] = chat_top_k_str
        else:
            to_save["CHAT_TOP_K"] = "8"

        try:
            save_settings_to_file(to_save)
            self._set_status("Settings saved.")
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)
            self._set_status(f"Error saving: {exc}")

    def action_back(self) -> None:
        self.app.pop_screen()

    async def action_refresh_models(self) -> None:
        await self._fetch_ollama_models()

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status-line", Static).update(msg)
        except Exception:
            pass
