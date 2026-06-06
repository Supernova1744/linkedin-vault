import asyncio

import typer
from rich.console import Console
from rich.table import Table

from linkedin_vault.config import load_settings
from linkedin_vault.db.database import DatabaseManager
from linkedin_vault.utils.logging import configure_logging

app = typer.Typer(
    name="linkedin-vault",
    help="LinkedIn Vault — turn your saved posts into a knowledge base",
    no_args_is_help=True,
)
console = Console()


def _get_db() -> DatabaseManager:
    settings = load_settings()
    configure_logging(settings.log_level)
    return DatabaseManager(settings.get_db_path())


@app.command()
def tui() -> None:
    """Launch the interactive TUI wizard."""
    from linkedin_vault.tui.app import run_tui

    run_tui()


@app.command()
def scrape(
    headless: bool = typer.Option(False, "--headless", help="Run browser in headless mode"),
) -> None:
    """Scrape LinkedIn saved posts and store them in the local database."""
    from linkedin_vault.scraper.runner import ScrapeResult, run_scrape

    settings = load_settings()
    configure_logging(settings.log_level)
    db = DatabaseManager(settings.get_db_path())

    console.print("[bold blue]LinkedIn Vault — Scrape[/bold blue]")
    if not headless:
        console.print(
            "[dim]A browser window will open. Log in to LinkedIn if prompted.[/dim]"
        )

    async def _run() -> ScrapeResult:
        def _on_progress(new_posts: int, _total_processed: int) -> None:
            if new_posts == 1 or new_posts % 25 == 0:
                console.print(f"  [dim]Saved {new_posts} new post(s) so far…[/dim]")

        return await run_scrape(
            settings=settings,
            db=db,
            headless=headless,
            progress_callback=_on_progress,
        )

    with console.status("[bold green]Scraping saved posts…[/bold green]", spinner="dots"):
        result = asyncio.run(_run())

    table = Table(title="Scrape Complete", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("New posts saved", str(result.new_posts))
    table.add_row("Already in DB (skipped)", str(result.skipped_existing))
    table.add_row("Failed extractions", str(result.failed_extractions))
    table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    console.print(table)


@app.command()
def enrich(
    limit: int | None = typer.Option(None, "--limit", "-n", help="Max posts to enrich"),
) -> None:
    """Enrich scraped posts with LLM analysis (Phase 3)."""
    raise NotImplementedError(f"Enrichment (limit={limit}) is implemented in Phase 3.")


@app.command()
def dashboard() -> None:
    """Open the web dashboard (Phase 4)."""
    raise NotImplementedError("Dashboard is implemented in Phase 4.")


@app.command()
def stats() -> None:
    """Show database statistics."""
    db = _get_db()

    async def _run() -> None:
        await db.initialize_db()
        vault_stats = await db.get_stats()
        sync = await db.get_sync_state()

        table = Table(title="LinkedIn Vault Statistics", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Total posts in DB", str(vault_stats.total_posts))
        table.add_row("Enriched posts", str(vault_stats.enriched_posts))
        table.add_row("Unread posts", str(vault_stats.unread_posts))
        table.add_row("Total ever scraped", str(vault_stats.total_posts_scraped))
        table.add_row("Last scraped", vault_stats.last_scraped_at or "never")
        if sync.last_sync_duration_seconds is not None:
            table.add_row("Last sync duration", f"{sync.last_sync_duration_seconds:.1f}s")

        console.print(table)

    asyncio.run(_run())


if __name__ == "__main__":
    app()
