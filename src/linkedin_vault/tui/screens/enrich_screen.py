from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static


class EnrichScreen(Screen):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    EnrichScreen { align: center top; }
    #title { text-align: center; text-style: bold; color: $success; margin: 1 0; }
    #log { height: 1fr; border: round $success; margin: 0 2; padding: 0 1; }
    Button { margin: 1 2; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold]Enriching Posts with LLM[/bold]", id="title")
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Button("Back", id="btn-back", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._run_enrich()

    @work
    async def _run_enrich(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.enricher.runner import run_enrichment

        log = self.query_one(RichLog)
        log.write("[dim]Loading settings…[/dim]")

        settings = load_settings()
        db = DatabaseManager(settings.get_db_path())

        if not settings.llm_model:
            log.write(
                "[bold red]No LLM model configured.[/bold red] "
                "Press [bold]Escape[/bold] and open [bold]Settings[/bold] to configure one."
            )
            return

        log.write(
            f"[dim]Provider: {settings.llm_provider}  "
            f"Model: {settings.llm_model}[/dim]"
        )
        log.write("")

        def on_progress(current: int, total: int) -> None:
            if total > 0:
                log.write(f"  [dim]Enriched {current}/{total} posts…[/dim]")

        try:
            result = await run_enrichment(
                settings=settings,
                db=db,
                limit=None,
                re_enrich=False,
                progress_callback=on_progress,
            )
            log.write("")
            log.write("[bold green]✓ Enrichment complete![/bold green]")
            log.write(f"  Posts enriched:    [bold]{result.enriched}[/bold]")
            log.write(f"  Already enriched:  {result.skipped_already_enriched}")
            log.write(f"  Failed:            {result.failed}")
            log.write(f"  Duration:          {result.duration_seconds:.1f}s")
        except Exception as exc:
            log.write(f"[bold red]Error:[/bold red] {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_go_back()

    def action_go_back(self) -> None:
        self.app.pop_screen()
