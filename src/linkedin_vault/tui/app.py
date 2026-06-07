from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from linkedin_vault.config import LLMProvider, load_settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.utils.logging import get_logger

logger = get_logger(__name__)


class LinkedInVaultApp(App):
    TITLE = "linkedin-vault"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    Screen { background: $surface; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._db = DatabaseManager(self._settings.get_db_path())

    async def on_mount(self) -> None:
        await self._db.initialize_db()
        if self._is_first_run():
            from linkedin_vault.tui.screens.setup_screen import SetupScreen

            await self.push_screen(SetupScreen())
        else:
            stats = await self._db.get_stats()
            from linkedin_vault.tui.screens.home_screen import HomeScreen

            await self.push_screen(HomeScreen(db=self._db, initial_stats=stats))

    def _is_first_run(self) -> bool:
        s = self._settings
        if not s.llm_model:
            return True
        if s.llm_provider == LLMProvider.ZAI and not s.zai_api_key:
            return True
        return False


def run_tui() -> None:
    app = LinkedInVaultApp()
    app.run()
