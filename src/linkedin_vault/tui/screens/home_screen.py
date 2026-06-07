from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, ListItem, ListView, Static

from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.db.models import VaultStats

_VERSION = "v0.1.0"

# Maps ListItem id → action name
_MENU_ITEMS: list[tuple[str, str]] = [
    ("menu-scrape", "Scrape Posts"),
    ("menu-enrich", "Enrich Posts"),
    ("menu-dashboard", "Open Dashboard"),
    ("menu-settings", "Settings"),
]

_SHARED_CSS = """
.separator {
    color: $text-muted;
    height: 1;
    padding: 0 0;
}

#title-line {
    padding: 0 2;
    color: $text-muted;
    height: 1;
    margin-bottom: 0;
}

#stats-line {
    padding: 0 2;
    color: $text-muted;
    height: 1;
}

#status-line {
    padding: 0 2;
    color: $text-muted;
    height: 1;
}

ListView {
    background: $surface;
    border: none;
    padding: 1 2;
    height: auto;
}

ListView > ListItem {
    background: $surface;
    padding: 0 1;
    height: 1;
}

ListView > ListItem.--highlight {
    background: $accent 20%;
}

ListView:focus > ListItem.--highlight {
    background: $accent 30%;
}
"""


class HomeScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("s", "settings", "Settings"),
        Binding("d", "dashboard", "Dashboard"),
        Binding("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = _SHARED_CSS

    def __init__(self, db: DatabaseManager, initial_stats: VaultStats) -> None:
        super().__init__()
        self._db = db
        self._initial_stats = initial_stats

    def compose(self) -> ComposeResult:
        stats = self._initial_stats
        pending = stats.total_posts - stats.enriched_posts
        last = stats.last_scraped_at or "never"

        yield Static(
            f"linkedin-vault  {_VERSION}",
            id="title-line",
        )
        yield Static("─" * 80, classes="separator")
        yield Static(
            f"posts: {stats.total_posts}  "
            f"enriched: {stats.enriched_posts}  "
            f"pending: {pending}  "
            f"last scraped: {last}",
            id="stats-line",
        )
        yield Static("─" * 80, classes="separator")
        yield Static("", id="spacer-top")
        menu = ListView(
            *[ListItem(Static(label), id=item_id) for item_id, label in _MENU_ITEMS],
            id="main-menu",
        )
        yield menu
        yield Static("─" * 80, classes="separator")
        yield Static("", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        # Focus the menu so arrows work immediately
        self.query_one("#main-menu", ListView).focus()

    def on_screen_resume(self) -> None:
        # Refresh stats every time we return from a sub-screen
        self.call_later(self._refresh_stats)

    # --- j/k delegation (advisor trap 1) ---

    def action_cursor_down(self) -> None:
        self.query_one("#main-menu", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#main-menu", ListView).action_cursor_up()

    # --- Stats refresh ---

    async def _refresh_stats(self) -> None:
        try:
            stats = await self._db.get_stats()
            pending = stats.total_posts - stats.enriched_posts
            last = stats.last_scraped_at or "never"
            self.query_one("#stats-line", Static).update(
                f"posts: {stats.total_posts}  "
                f"enriched: {stats.enriched_posts}  "
                f"pending: {pending}  "
                f"last scraped: {last}"
            )
        except Exception:
            pass

    # --- ListView selection ---

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id
        if item_id == "menu-scrape":
            self._go_scrape()
        elif item_id == "menu-enrich":
            self._go_enrich()
        elif item_id == "menu-dashboard":
            self.action_dashboard()
        elif item_id == "menu-settings":
            self.action_settings()

    def _go_scrape(self) -> None:
        from linkedin_vault.tui.screens.scrape_screen import ScrapeScreen

        self.app.push_screen(ScrapeScreen())

    def _go_enrich(self) -> None:
        from linkedin_vault.tui.screens.enrich_screen import EnrichScreen

        self.app.push_screen(EnrichScreen())

    def action_settings(self) -> None:
        from linkedin_vault.tui.screens.settings_screen import SettingsScreen

        self.app.push_screen(SettingsScreen())

    def action_dashboard(self) -> None:
        self._open_dashboard()

    @work(thread=True)
    def _open_dashboard(self) -> None:
        import webbrowser

        from linkedin_vault.config import load_settings
        from linkedin_vault.dashboard.server import run_dashboard

        settings = load_settings()
        url = f"http://{settings.dashboard_host}:{settings.dashboard_port}"
        self.app.call_from_thread(
            self._set_status,
            f"Dashboard running at {url}  (Ctrl+C in terminal to stop)",
        )
        webbrowser.open(url)
        run_dashboard(settings)  # blocks until server exits
        self.app.call_from_thread(self._set_status, "")

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#status-line", Static).update(msg)
        except Exception:
            pass

    def action_quit(self) -> None:
        self.app.exit()
