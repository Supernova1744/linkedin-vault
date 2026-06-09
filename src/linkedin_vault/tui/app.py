"""Textual application entry point for LinkedIn Vault.

:class:`LinkedInVaultApp` initialises the database, loads vault statistics,
and pushes the :class:`~linkedin_vault.tui.screens.welcome.WelcomeScreen` as
the first screen.  All screen navigation happens via Textual's built-in
``push_screen`` / ``pop_screen`` stack.

Call :func:`run_tui` from the CLI to launch the app.
"""

from typing import ClassVar

from textual.app import App
from textual.binding import Binding, BindingType

from linkedin_vault.config import load_settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.utils.logging import get_logger

logger = get_logger(__name__)


class LinkedInVaultApp(App):
    TITLE = "LinkedIn Vault"
    SUB_TITLE = "Your saved posts, organized"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    Screen {
        background: $background;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._db = DatabaseManager(self._settings.get_db_path())

    async def on_mount(self) -> None:
        await self._db.initialize_db()
        stats = await self._db.get_stats()
        from linkedin_vault.tui.screens.welcome import WelcomeScreen

        await self.push_screen(WelcomeScreen(stats=stats))


def run_tui() -> None:
    app = LinkedInVaultApp()
    app.run()
