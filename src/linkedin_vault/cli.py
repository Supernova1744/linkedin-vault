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
        def _on_progress(new_posts: int, _total: int) -> None:
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
    re_enrich: bool = typer.Option(
        False, "--re-enrich", help="Re-enrich already-enriched posts"
    ),
) -> None:
    """Enrich scraped posts with LLM analysis."""
    from linkedin_vault.enricher.runner import EnrichmentRunResult, run_enrichment

    settings = load_settings()
    configure_logging(settings.log_level)
    db = DatabaseManager(settings.get_db_path())

    if not settings.llm_model:
        console.print(
            "[bold red]Error:[/bold red] No LLM model configured. "
            "Run [bold]linkedin-vault tui[/bold] to configure one."
        )
        raise typer.Exit(1)

    console.print("[bold blue]LinkedIn Vault — Enrich[/bold blue]")
    console.print(
        f"[dim]Provider: {settings.llm_provider}  Model: {settings.llm_model}[/dim]"
    )

    async def _run() -> EnrichmentRunResult:
        def _on_progress(current: int, total: int) -> None:
            if total > 0 and (current % 5 == 0 or current == total):
                console.print(f"  [dim]Processed {current}/{total} posts…[/dim]")

        return await run_enrichment(
            settings=settings,
            db=db,
            limit=limit,
            re_enrich=re_enrich,
            progress_callback=_on_progress,
        )

    with console.status("[bold green]Enriching posts…[/bold green]", spinner="dots"):
        result = asyncio.run(_run())

    table = Table(title="Enrichment Complete", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Posts enriched", str(result.enriched))
    table.add_row("Already enriched (skipped)", str(result.skipped_already_enriched))
    table.add_row("Failed", str(result.failed))
    table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    console.print(table)


@app.command()
def models() -> None:
    """List available LLM models for the configured provider."""
    from linkedin_vault.enricher.base import LLMProviderError
    from linkedin_vault.enricher.factory import get_provider

    settings = load_settings()
    configure_logging(settings.log_level)

    async def _run() -> list[str]:
        provider = get_provider(settings)
        return await provider.list_models()

    try:
        model_list = asyncio.run(_run())
    except LLMProviderError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        f"[bold blue]Available models ({settings.llm_provider}):[/bold blue]"
    )
    for m in model_list:
        marker = " [bold yellow]*[/bold yellow]" if m == settings.llm_model else ""
        console.print(f"  {m}{marker}")


@app.command()
def dashboard() -> None:
    """Launch the web dashboard."""
    from linkedin_vault.dashboard.server import run_dashboard

    settings = load_settings()
    configure_logging(settings.log_level)
    url = f"http://{settings.dashboard_host}:{settings.dashboard_port}"
    console.print("[bold blue]LinkedIn Vault Dashboard[/bold blue]")
    console.print(f"[dim]Opening at {url}[/dim]")
    import webbrowser

    webbrowser.open(url)
    run_dashboard(settings)


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
