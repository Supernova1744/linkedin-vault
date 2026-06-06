from typing import ClassVar

import httpx
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
)

from linkedin_vault.config import LLMProvider, load_settings, save_settings_to_file
from linkedin_vault.utils.logging import get_logger

logger = get_logger(__name__)

ZAI_MODELS = [
    "glm-4",
    "glm-4-flash",
    "glm-4-air",
    "glm-4-airx",
    "glm-3-turbo",
]


class ConfigWizardScreen(Screen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    DEFAULT_CSS = """
    ConfigWizardScreen {
        align: center middle;
    }

    #wizard-container {
        border: round $accent;
        padding: 2 4;
        width: 70;
        height: auto;
    }

    #title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #provider-section {
        margin-bottom: 1;
    }

    #zai-section, #ollama-section {
        margin-top: 1;
        margin-bottom: 1;
    }

    Label {
        margin-bottom: 1;
    }

    Input {
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    #btn-row {
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    Button {
        margin-right: 1;
    }

    #status-msg {
        text-align: center;
        color: $success;
        margin-top: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._ollama_models: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Static(id="wizard-container"):
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

            with Static(id="btn-row"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Cancel", id="btn-cancel", variant="default")

            yield Static("", id="status-msg")

        yield Footer()

    def on_mount(self) -> None:
        self._sync_provider_visibility()
        if self._settings.llm_provider == LLMProvider.OLLAMA:
            self.app.call_later(self._fetch_ollama_models)

    def _sync_provider_visibility(self) -> None:
        is_zai = self._current_provider() == LLMProvider.ZAI
        self.query_one("#zai-section").display = is_zai
        self.query_one("#ollama-section").display = not is_zai

    def _current_provider(self) -> LLMProvider:
        radio_set = self.query_one("#provider-radio", RadioSet)
        selected = radio_set.pressed_button
        if selected is None:
            return LLMProvider.ZAI
        return LLMProvider.ZAI if selected.id == "radio-zai" else LLMProvider.OLLAMA

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self._sync_provider_visibility()
        if self._current_provider() == LLMProvider.OLLAMA and not self._ollama_models:
            self.app.call_later(self._fetch_ollama_models)

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
        select = self.query_one("#ollama-model-select", Select)

        if models:
            current = self._settings.llm_model
            select.set_options(self._ollama_models)
            if current in models:
                select.value = current
            self.query_one("#status-msg", Static).update("")
        else:
            select.set_options([("(no models found)", "")])
            self.query_one("#status-msg", Static).update(
                "[yellow]Could not reach Ollama — is it running?[/yellow]"
            )

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
            model = str(model_select.value) if model_select.value else ZAI_MODELS[1]
            if not api_key:
                self.query_one("#status-msg", Static).update(
                    "[red]z.ai API key is required.[/red]"
                )
                return
            to_save["ZAI_API_KEY"] = api_key
            to_save["LLM_MODEL"] = model
        else:
            ollama_url = self.query_one("#ollama-url", Input).value.strip()
            model_select = self.query_one("#ollama-model-select", Select)
            model = str(model_select.value) if model_select.value else ""
            to_save["OLLAMA_BASE_URL"] = ollama_url
            to_save["LLM_MODEL"] = model

        try:
            save_settings_to_file(to_save)
            self.query_one("#status-msg", Static).update(
                "[green]Settings saved to ~/.linkedin-vault/.env[/green]"
            )
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)
            self.query_one("#status-msg", Static).update(
                f"[red]Error saving settings: {exc}[/red]"
            )

    def action_back(self) -> None:
        self.app.pop_screen()
