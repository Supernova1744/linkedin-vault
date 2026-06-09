from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual import work
from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import RichLog

from linkedin_vault.tui.vault_screen import VaultScreen


class LoginScreen(VaultScreen):
    SCREEN_TITLE = "Login to LinkedIn"
    BOTTOM_HINTS = "  [#CC785C]esc[/#CC785C] Back"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    LoginScreen #log { height: 1fr; border: none; padding: 0 2; }
    """

    def compose_content(self) -> Iterable[Widget]:
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        self._run_login(log)

    @work(thread=True)
    def _run_login(self, log: RichLog) -> None:
        import asyncio

        from linkedin_vault.config import load_settings
        from linkedin_vault.scraper.browser import do_login

        def _log(msg: str) -> None:
            self.app.call_from_thread(log.write, msg)

        _log("[dim]Loading settings…[/dim]")

        try:
            settings = load_settings()
            session_path = settings.data_dir / "session.json"

            _log("[dim]A browser window will open — please log in to LinkedIn.[/dim]")
            _log("[dim]The window closes automatically once login is detected.[/dim]")
            _log("")

            def on_status(msg: str) -> None:
                _log(f"  [dim]{msg}[/dim]")

            asyncio.run(do_login(session_path=session_path, status_callback=on_status))

            _log("")
            _log("[bold green]✓ Logged in![/bold green] Session saved.")
            _log("")
            _log("You can now go back and scrape your posts.")
        except TimeoutError:
            _log("")
            _log("[bold yellow]⚠ Login timed out (5 minutes).[/bold yellow]")
            _log("Please press Back and try again.")
        except Exception as exc:
            _log(f"[bold red]Error:[/bold red] {exc}")

    def action_go_back(self) -> None:
        self.app.pop_screen()
