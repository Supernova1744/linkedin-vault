from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class WelcomeScreen(Screen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("s", "settings", "Settings"),
    ]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
    }

    #banner {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    #stats-panel {
        border: round $accent;
        padding: 1 3;
        margin-bottom: 2;
        width: 50;
    }

    #stats-panel Label {
        text-align: left;
    }

    #actions {
        layout: vertical;
        align: center middle;
        width: 30;
    }

    Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, stats: dict[str, int | str | None]) -> None:
        super().__init__()
        self._stats = stats

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold]LinkedIn Vault[/bold]  v0.1.0", id="banner")
        yield Static("Turn your saved posts into a knowledge base", id="subtitle")

        total = self._stats.get("total_posts", 0)
        enriched = self._stats.get("enriched_posts", 0)
        unread = self._stats.get("unread_posts", 0)
        last_scraped = self._stats.get("last_scraped_at") or "never"

        stats_panel = Static(
            f"  Total posts:    {total}\n"
            f"  Enriched:       {enriched}\n"
            f"  Unread:         {unread}\n"
            f"  Last scraped:   {last_scraped}",
            id="stats-panel",
        )
        yield stats_panel

        with Static(id="actions"):
            yield Button("Scrape Posts", id="btn-scrape", variant="primary")
            yield Button("Enrich Posts", id="btn-enrich", variant="success")
            yield Button("Open Dashboard", id="btn-dashboard", variant="default")
            yield Button("Settings", id="btn-settings", variant="default")
            yield Button("Quit", id="btn-quit", variant="error")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-quit":
            self.app.exit()
        elif button_id == "btn-settings":
            self.action_settings()
        elif button_id == "btn-scrape":
            from linkedin_vault.tui.screens.scrape_screen import ScrapeScreen

            self.app.push_screen(ScrapeScreen())
        elif button_id == "btn-enrich":
            from linkedin_vault.tui.screens.enrich_screen import EnrichScreen

            self.app.push_screen(EnrichScreen())
        elif button_id == "btn-dashboard":
            self._open_dashboard()

    @work(thread=True)
    def _open_dashboard(self) -> None:
        import webbrowser

        from linkedin_vault.config import load_settings
        from linkedin_vault.dashboard.server import run_dashboard

        settings = load_settings()
        url = f"http://{settings.dashboard_host}:{settings.dashboard_port}"
        self.app.call_from_thread(
            self.notify,
            f"Dashboard running at {url}  (press Ctrl+C in terminal to stop)",
            title="Dashboard",
            timeout=8,
        )
        webbrowser.open(url)
        run_dashboard(settings)  # blocks until server exits

    def action_settings(self) -> None:
        from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

        self.app.push_screen(ConfigWizardScreen())

    def action_quit(self) -> None:
        self.app.exit()
