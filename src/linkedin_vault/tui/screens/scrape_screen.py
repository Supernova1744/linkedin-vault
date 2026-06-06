from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static


class ScrapeScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    ScrapeScreen { align: center top; }
    #title { text-align: center; text-style: bold; color: $accent; margin: 1 0; }
    #log { height: 1fr; border: round $accent; margin: 0 2; padding: 0 1; }
    Button { margin: 1 2; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold]Scraping LinkedIn Saved Posts[/bold]", id="title")
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Button("Back", id="btn-back", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._run_scrape()

    @work
    async def _run_scrape(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.scraper.runner import run_scrape

        log = self.query_one(RichLog)
        log.write("[dim]Loading settings…[/dim]")

        settings = load_settings()
        db = DatabaseManager(settings.get_db_path())

        from pathlib import Path
        diag_file = Path.home() / ".linkedin-vault" / "debug_diagnostic.txt"
        log.write("[dim]Opening browser — log in to LinkedIn if prompted.[/dim]")
        log.write(f"[dim]Diagnostic will be written to: {diag_file}[/dim]")
        log.write("")

        def on_progress(new_posts: int, _total: int) -> None:
            log.write(f"  [dim]Saved {new_posts} new post(s)…[/dim]")

        try:
            result = await run_scrape(
                settings=settings,
                db=db,
                headless=False,
                progress_callback=on_progress,
            )
            log.write("")
            if result.new_posts == 0 and result.skipped_existing == 0:
                log.write("[bold yellow]⚠ Scrape finished with 0 posts found.[/bold yellow]")
                log.write("")
                log.write("Possible causes:")
                log.write("  • LinkedIn changed their page structure (selectors need updating)")
                log.write("  • You are not logged in / session expired")
                log.write("  • The saved posts page is genuinely empty")
                from pathlib import Path
                screenshot = Path.home() / ".linkedin-vault" / "debug_screenshot.png"
                if screenshot.exists():
                    log.write("")
                    log.write(f"[dim]Debug screenshot saved:[/dim] {screenshot}")
                    log.write("[dim]Open it to see what the browser saw.[/dim]")
            else:
                log.write("[bold green]✓ Scrape complete![/bold green]")
            log.write(f"  New posts saved:     [bold]{result.new_posts}[/bold]")
            log.write(f"  Already in DB:       {result.skipped_existing}")
            log.write(f"  Failed extractions:  {result.failed_extractions}")
            log.write(f"  Duration:            {result.duration_seconds:.1f}s")
        except Exception as exc:
            log.write(f"[bold red]Error:[/bold red] {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_go_back()

    def action_go_back(self) -> None:
        self.app.pop_screen()
