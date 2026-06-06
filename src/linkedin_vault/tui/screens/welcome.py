from typing import ClassVar

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
            self.notify(
                "Scrape is implemented in Phase 2. Run: linkedin-vault scrape",
                title="Coming Soon",
            )
        elif button_id == "btn-enrich":
            self.notify(
                "Enrichment is implemented in Phase 3. Run: linkedin-vault enrich",
                title="Coming Soon",
            )
        elif button_id == "btn-dashboard":
            self.notify(
                "Dashboard is implemented in Phase 4. Run: linkedin-vault dashboard",
                title="Coming Soon",
            )

    def action_settings(self) -> None:
        from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

        self.app.push_screen(ConfigWizardScreen())

    def action_quit(self) -> None:
        self.app.exit()
