from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual import work
from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import RichLog

from linkedin_vault.tui.vault_screen import VaultScreen


class EnrichScreen(VaultScreen):
    SCREEN_TITLE = "Enrich Posts"
    BOTTOM_HINTS = "  [#CC785C]esc[/#CC785C] Back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    EnrichScreen #log { height: 1fr; border: none; padding: 0 2; }
    """

    def compose_content(self) -> Iterable[Widget]:
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        self._run_enrich()

    @work
    async def _run_enrich(self) -> None:
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager
        from linkedin_vault.enricher.runner import run_enrichment

        log = self.query_one(RichLog)
        log.write("[dim]Loading settings…[/dim]")

        try:
            settings = load_settings()
            db = DatabaseManager(settings.get_db_path())
        except Exception as exc:
            log.write(f"[bold red]Failed to load settings:[/bold red] {exc}")
            return

        if not settings.llm_model:
            log.write(
                "[bold red]No LLM model configured.[/bold red] "
                "Press [bold]Escape[/bold] and open [bold]Settings[/bold] to configure one."
            )
            return

        log.write(f"[dim]Provider: {settings.llm_provider}  Model: {settings.llm_model}[/dim]")
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

    def action_go_back(self) -> None:
        self.app.pop_screen()
