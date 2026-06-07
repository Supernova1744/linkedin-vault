from __future__ import annotations

import time
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, RichLog, Static

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_BAR_WIDTH = 46


def _render_bar(current: int, total: int) -> str:
    if total <= 0:
        return f"[{'░' * _BAR_WIDTH}]"
    filled = int(_BAR_WIDTH * current / total)
    return f"[{'█' * filled}{'░' * (_BAR_WIDTH - filled)}]"


_CSS = """
EnrichScreen {
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


class EnrichScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = _CSS

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self._spinner_idx = 0
        self._current = 0
        self._total = 0
        self._start_time = 0.0
        self._spinner_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static("enrich posts", id="title-line")
        yield Static("─" * 80, classes="separator")
        yield Static(f"  ⠋ running…  {_render_bar(0, 0)}  0/0", id="run-indicator")
        yield Static("─" * 80, classes="separator")
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Footer()

    def check_action(self, action: str, parameters: tuple) -> bool | None:  # noqa: ARG002
        if action == "go_back" and self._running:
            return None
        return True

    def on_mount(self) -> None:
        self._start_time = time.monotonic()
        self._spinner_timer = self.set_interval(0.1, self._tick_spinner)
        self._run_enrich()

    def _tick_spinner(self) -> None:
        if not self._running:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_idx]
        bar = _render_bar(self._current, self._total)
        count = f"{self._current}/{self._total}" if self._total > 0 else "…"
        try:
            self.query_one("#run-indicator", Static).update(
                f"  {frame} running…  {bar}  {count}"
            )
        except Exception:
            pass

    @work
    async def _run_enrich(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.enricher.runner import run_enrichment

        log = self.query_one(RichLog)
        log.write("[dim]loading settings…[/dim]")

        try:
            settings = load_settings()
            db = DatabaseManager(settings.get_db_path())

            if not settings.llm_model:
                log.write(
                    "[dim]no LLM model configured.[/dim]\n"
                    "press [bold]esc[/bold] and open [bold]settings[/bold] to configure one."
                )
                self.query_one("#run-indicator", Static).update(
                    "  done  ·  not started  ·  0.0s"
                )
                return

            log.write(
                f"[dim]provider: {settings.llm_provider}  "
                f"model: {settings.llm_model}[/dim]"
            )
            log.write("")

            def on_progress(current: int, total: int) -> None:
                self._current = current
                self._total = total
                log.write(f"  [dim]enriched {current}/{total} posts…[/dim]")

            result = await run_enrichment(
                settings=settings,
                db=db,
                limit=None,
                re_enrich=False,
                progress_callback=on_progress,
            )
            elapsed = time.monotonic() - self._start_time
            log.write("")
            log.write("[bold]✓ enrichment complete![/bold]")
            log.write(f"  posts enriched:    [bold]{result.enriched}[/bold]")
            log.write(f"  already enriched:  {result.skipped_already_enriched}")
            log.write(f"  failed:            {result.failed}")
            log.write(f"  duration:          {elapsed:.1f}s")
            full_bar = "█" * _BAR_WIDTH
            self.query_one("#run-indicator", Static).update(
                f"  done  [{full_bar}]  {result.enriched}/{result.enriched}  {elapsed:.1f}s"
            )
        except Exception as exc:
            elapsed = time.monotonic() - self._start_time
            log.write(f"[bold red]error:[/bold red] {exc}")
            self.query_one("#run-indicator", Static).update(
                f"  error  ·  {elapsed:.1f}s"
            )
        finally:
            self._running = False
            if self._spinner_timer is not None:
                self._spinner_timer.stop()
            self.refresh_bindings()  # makes esc appear in Footer

    def action_go_back(self) -> None:
        self.app.pop_screen()
