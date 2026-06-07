from __future__ import annotations

from typing import ClassVar

import httpx
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, Select, Static

from linkedin_vault.config import LLMProvider, load_settings, save_settings_to_file
from linkedin_vault.utils.url_validation import validate_ollama_url
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

_CSS = """
SetupScreen {
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
    padding: 1 2 0 2;
    color: $text-muted;
    height: 2;
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
"""


class SetupScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "cancel", "Cancel"),
        Binding("r", "refresh_models", "Refresh Ollama models"),
    ]

    DEFAULT_CSS = _CSS

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._ollama_models: list[tuple[str, str]] = []

    def _initial_provider(self) -> LLMProvider:
        return self._settings.llm_provider

    def compose(self) -> ComposeResult:
        settings = self._settings

        yield Static("linkedin-vault — first-time setup", id="title-line")
        yield Static("─" * 80, classes="separator")
        yield Static("")

        # Provider row
        with Static(classes="field-row"):
            yield Label("LLM provider", classes="field-label")
            yield Select(
                options=[
                    ("z.ai (cloud)", "zai"),
                    ("Ollama (local)", "ollama"),
                ],
                value=settings.llm_provider.value,
                id="provider-select",
                classes="field-value",
            )

        # z.ai section
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

        # Ollama section
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

        yield Static("─" * 80, classes="separator")
        yield Static("", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self._sync_provider_visibility()
        provider = self._initial_provider()
        if provider == LLMProvider.OLLAMA:
            self.call_later(self._fetch_ollama_models)

    def _sync_provider_visibility(self) -> None:
        is_zai = self._current_provider() == LLMProvider.ZAI
        self.query_one("#zai-section").display = is_zai
        self.query_one("#ollama-section").display = not is_zai

    def _current_provider(self) -> LLMProvider:
        sel = self.query_one("#provider-select", Select)
        val = sel.value
        if val == "ollama":
            return LLMProvider.OLLAMA
        return LLMProvider.ZAI

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "provider-select":
            self._sync_provider_visibility()
            if self._current_provider() == LLMProvider.OLLAMA and not self._ollama_models:
                self.call_later(self._fetch_ollama_models)

    async def _fetch_ollama_models(self) -> None:
        self._set_status("Fetching Ollama models...")
        ollama_url_input = self.query_one("#ollama-url", Input)
        base_url = ollama_url_input.value.rstrip("/") or "http://localhost:11434"
        is_valid, warning = validate_ollama_url(base_url)
        if not is_valid:
            self._set_status(warning)
            return
        if warning:
            self._set_status(warning)
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
            is_valid, warning = validate_ollama_url(ollama_url)
            if not is_valid:
                self._set_status(warning)
                return
            model_select = self.query_one("#ollama-model-select", Select)
            raw = model_select.value
            model = str(raw) if raw and raw != "(none)" else ""
            to_save["OLLAMA_BASE_URL"] = ollama_url
            to_save["LLM_MODEL"] = model
            if warning:
                self._set_status(warning)

        try:
            save_settings_to_file(to_save)
            self._set_status("Saved.  Loading home screen...")
            self.call_later(self._go_home)
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)
            self._set_status(f"Error saving: {exc}")

    async def _go_home(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.tui.screens.home_screen import HomeScreen

        settings = load_settings()
        db = DatabaseManager(settings.get_db_path())
        await db.initialize_db()
        stats = await db.get_stats()
        self.app.pop_screen()
        await self.app.push_screen(HomeScreen(db=db, initial_stats=stats))

    def action_cancel(self) -> None:
        # On first run, cancel exits rather than pushing a broken home screen
        self.app.exit()

    async def action_refresh_models(self) -> None:
        await self._fetch_ollama_models()

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status-line", Static).update(msg)
        except Exception:
            pass
