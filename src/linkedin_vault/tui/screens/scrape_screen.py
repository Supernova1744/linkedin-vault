from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual import work
from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import RichLog

from linkedin_vault.tui.vault_screen import VaultScreen


class ScrapeScreen(VaultScreen):
    SCREEN_TITLE = "Scrape Posts"
    BOTTOM_HINTS = "  [#CC785C]esc[/#CC785C] Back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    ScrapeScreen #log { height: 1fr; border: none; padding: 0 2; }
    """

    def compose_content(self) -> Iterable[Widget]:
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        self._run_scrape(log)

    @work(thread=True)
    def _run_scrape(self, log: RichLog) -> None:
        import asyncio

        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.scraper.browser import LinkedInSessionExpiredError
        from linkedin_vault.scraper.runner import run_scrape

        def _log(msg: str) -> None:
            self.app.call_from_thread(log.write, msg)

        _log("[dim]Loading settings…[/dim]")

        settings = load_settings()
        db = DatabaseManager(settings.get_db_path())

        asyncio.run(db.initialize_db())
        sync_state = asyncio.run(db.get_sync_state())
        is_complete = sync_state.last_scrape_was_complete

        if is_complete:
            _log("[dim]Mode: fast incremental sync (checking for new posts only)[/dim]")
        else:
            _log("[bold yellow]Full scan mode[/bold yellow] — previous scrape was incomplete.")
            _log(
                "[dim]Scanning the entire feed to recover any missed posts."
                " This may take longer.[/dim]"
            )
            _log("[dim]Do not close the app during this scan.[/dim]")
        _log("")
        _log("[dim]Starting headless browser…[/dim]")
        _log("")

        def on_progress(new_posts: int, _: int) -> None:
            _log(f"  [dim]Saved {new_posts} new post(s)…[/dim]")

        try:
            result = asyncio.run(
                run_scrape(
                    settings=settings,
                    db=db,
                    headless=True,
                    progress_callback=on_progress,
                    status_callback=_log,
                )
            )
            _log("")
            if result.new_posts == 0 and result.skipped_existing == 0:
                _log("[bold yellow]⚠ Scrape finished with 0 posts found.[/bold yellow]")
                _log("")
                _log("Possible causes:")
                _log("  • LinkedIn changed their page structure (selectors need updating)")
                _log("  • Session expired — use the Login option on the welcome screen")
                _log("  • The saved posts page is genuinely empty")
            else:
                _log("[bold green]✓ Scrape complete![/bold green]")
                if result.scrape_mode == "full_scan":
                    if result.new_posts > 0:
                        _log("  Mode: full scan — vault is now complete")
                    else:
                        _log("  Mode: full scan — no missed posts found")
                else:
                    _log("  Mode: fast sync")
            _log(f"  New posts saved:     [bold]{result.new_posts}[/bold]")
            _log(f"  Already in DB:       {result.skipped_existing}")
            _log(f"  Failed extractions:  {result.failed_extractions}")
            _log(f"  Duration:            {result.duration_seconds:.1f}s")
        except LinkedInSessionExpiredError:
            _log("")
            _log("[bold yellow]⚠ LinkedIn session expired.[/bold yellow]")
            _log("")
            _log("Go back and press [bold]l[/bold] to login to LinkedIn, then scrape again.")
        except Exception as exc:
            _log(f"[bold red]Error:[/bold red] {exc}")

    def action_go_back(self) -> None:
        self.app.pop_screen()
