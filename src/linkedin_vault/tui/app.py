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
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._db = DatabaseManager(self._settings.get_db_path())

    async def on_mount(self) -> None:
        await self._db.initialize_db()
        stats = await self._db.get_stats()
        stats_dict = {
            "total_posts": stats.total_posts,
            "enriched_posts": stats.enriched_posts,
            "unread_posts": stats.unread_posts,
            "last_scraped_at": stats.last_scraped_at,
        }
        from linkedin_vault.tui.screens.welcome import WelcomeScreen

        await self.push_screen(WelcomeScreen(stats=stats_dict))


def run_tui() -> None:
    app = LinkedInVaultApp()
    app.run()
