from __future__ import annotations

import time
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_CSS = """
ScrapeScreen {
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

#run-indicator {
    padding: 0 2;
    color: $text-muted;
    height: 1;
}

#log {
    height: 1fr;
    padding: 0 2;
    background: $surface;
}
"""


class ScrapeScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = _CSS

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self._spinner_idx = 0
        self._start_time = 0.0
        self._spinner_timer = None  # type: ignore[assignment]

    def compose(self) -> ComposeResult:
        yield Static("scrape posts", id="title-line")
        yield Static("─" * 80, classes="separator")
        yield Static("  ⠋ running…", id="run-indicator")
        yield Static("─" * 80, classes="separator")
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Footer()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Return None (not False) so the binding is HIDDEN (not dimmed) during run
        if action == "go_back" and self._running:
            return None
        return True

    def on_mount(self) -> None:
        self._start_time = time.monotonic()
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
        self._run_scrape()

    def _tick_spinner(self) -> None:
        if not self._running:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_idx]
        try:
            self.query_one("#run-indicator", Static).update(f"  {frame} running…")
        except Exception:
            pass

    @work
    async def _run_scrape(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.scraper.runner import run_scrape

        log = self.query_one(RichLog)
        log.write("[dim]loading settings…[/dim]")

        try:
            settings = load_settings()
            db = DatabaseManager(settings.get_db_path())

            from pathlib import Path
            diag_file = Path.home() / ".linkedin-vault" / "debug_diagnostic.txt"
            log.write("[dim]opening browser — log in to LinkedIn if prompted.[/dim]")
            log.write(f"[dim]diagnostic: {diag_file}[/dim]")
            log.write("")

            def on_progress(new_posts: int, _total: int) -> None:
                log.write(f"  [dim]saved {new_posts} new post(s)…[/dim]")

            result = await run_scrape(
                settings=settings,
                db=db,
                headless=False,
                progress_callback=on_progress,
            )
            log.write("")
            elapsed = time.monotonic() - self._start_time
            if result.new_posts == 0 and result.skipped_existing == 0:
                log.write("[bold]⚠ scrape finished with 0 posts found.[/bold]")
                log.write("")
                log.write("possible causes:")
                log.write("  · linkedin changed their page structure (selectors need updating)")
                log.write("  · you are not logged in / session expired")
                log.write("  · the saved posts page is genuinely empty")
                from pathlib import Path
                screenshot = Path.home() / ".linkedin-vault" / "debug_screenshot.png"
                if screenshot.exists():
                    log.write("")
                    log.write(f"[dim]debug screenshot: {screenshot}[/dim]")
                self.query_one("#run-indicator", Static).update(
                    f"  done  ·  {result.new_posts} new  ·  {result.skipped_existing} skipped"
                    f"  ·  {result.failed_extractions} failed  ·  {elapsed:.1f}s"
                )
            else:
                log.write("[bold]✓ scrape complete![/bold]")
                log.write(f"  new posts saved:     [bold]{result.new_posts}[/bold]")
                log.write(f"  already in DB:       {result.skipped_existing}")
                log.write(f"  failed extractions:  {result.failed_extractions}")
                log.write(f"  duration:            {elapsed:.1f}s")
                self.query_one("#run-indicator", Static).update(
                    f"  done  ·  {result.new_posts} new  ·  {result.skipped_existing} skipped"
                    f"  ·  {result.failed_extractions} failed  ·  {elapsed:.1f}s"
                )
        except Exception as exc:
            elapsed = time.monotonic() - self._start_time
            log.write(f"[bold red]error:[/bold red] {exc}")
            self.query_one("#run-indicator", Static).update(
                f"  error  ·  {elapsed:.1f}s"
            )
        finally:
            self._running = False
            self._spinner_timer.stop()
            self.refresh_bindings()  # triggers Footer to re-render with esc visible

    def action_go_back(self) -> None:
        self.app.pop_screen()
