from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Iterable
from typing import Any, ClassVar

from textual import work
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from linkedin_vault.db.models import VaultStats
from linkedin_vault.tui.vault_screen import VaultScreen


def _open_url(url: str) -> None:
    """Open *url* in the default browser, handling WSL2 where webbrowser fails.

    On WSL2 the Linux webbrowser module delegates to ``gio open``, which
    does not know how to handle ``http://`` URLs and prints the error seen
    in the TUI.  Detect WSL2 via ``/proc/version`` and use
    ``cmd.exe /c start`` to open in the Windows default browser instead.
    """
    try:
        with open("/proc/version") as _f:
            if "microsoft" in _f.read().lower():
                subprocess.run(
                    ["cmd.exe", "/c", "start", "", url],
                    capture_output=True,
                    timeout=5,
                )
                return
    except OSError:
        pass
    import webbrowser

    webbrowser.open(url)


class WelcomeScreen(VaultScreen):
    SCREEN_TITLE = ""
    BOTTOM_HINTS = "  [#CC785C]q[/#CC785C] Quit"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("s", "scrape", "Scrape"),
        Binding("e", "enrich", "Enrich"),
        Binding("c", "chat", "Chat"),
        Binding("l", "login", "Login"),
        Binding("d", "dashboard", "Dashboard"),
        Binding("comma", "settings", "Settings"),
    ]

    DEFAULT_CSS = """
    WelcomeScreen #welcome-scroll {
        height: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self, stats: VaultStats) -> None:
        super().__init__()
        self._stats = stats
        self._dashboard_running = False
        self._dashboard_server: Any = None  # uvicorn.Server while the dashboard is up

    def on_unmount(self) -> None:
        # Signal the uvicorn server to stop so its thread exits cleanly.
        # Without this, Python's atexit blocks indefinitely joining the thread.
        if self._dashboard_server is not None:
            self._dashboard_server.should_exit = True

    def compose_content(self) -> Iterable[Widget]:
        from textual.containers import VerticalScroll

        with VerticalScroll(id="welcome-scroll"):
            yield Static("", id="welcome-header", markup=True)
            yield Static("", id="stats-block", markup=True)
            yield Static("", id="actions-list", markup=True)

    def on_mount(self) -> None:
        self.query_one("#welcome-header", Static).update(self._header_markup())
        self.query_one("#stats-block", Static).update(self._stats_markup())
        self._rebuild_actions()

    # ------------------------------------------------------------------
    # Markup helpers
    # ------------------------------------------------------------------

    def _header_markup(self) -> str:
        sep = "─" * 76
        return (
            f"\n  [bold #CC785C]LinkedIn Vault[/bold #CC785C]  v0.1.0\n"
            f"  [dim]Turn your saved posts into a knowledge base[/dim]\n\n"
            f"  [dim]{sep}[/dim]\n"
        )

    def _stats_markup(self) -> str:
        sep = "─" * 76
        last = self._stats.last_scraped_at or "never"
        return (
            f"\n  Total posts      {self._stats.total_posts}\n"
            f"  Enriched         {self._stats.enriched_posts}\n"
            f"  Unread           {self._stats.unread_posts}\n"
            f"  Last scraped     {last}\n\n"
            f"  [dim]{sep}[/dim]\n"
        )

    def _actions_markup(self) -> str:
        dash_hint = ""
        if self._dashboard_running:
            dash_hint = "  [dim](running — press to reopen browser)[/dim]"
        return (
            f"\n  [#CC785C][[s]][/#CC785C] Scrape Posts\n"
            f"  [#CC785C][[e]][/#CC785C] Enrich Posts\n"
            f"  [#CC785C][[c]][/#CC785C] Chat with Vault\n"
            f"  [#CC785C][[l]][/#CC785C] Login to LinkedIn\n"
            f"  [#CC785C][[d]][/#CC785C] Open Dashboard{dash_hint}\n"
            f"  [#CC785C][[,]][/#CC785C] Settings\n"
        )

    def _rebuild_actions(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#actions-list", Static).update(self._actions_markup())

    # ------------------------------------------------------------------
    # Dashboard worker
    # ------------------------------------------------------------------

    @work(thread=True)
    def _open_dashboard(self) -> None:
        import asyncio
        import threading

        from linkedin_vault.config import load_settings
        from linkedin_vault.dashboard.server import make_server

        settings = load_settings()
        url = f"http://{settings.dashboard_host}:{settings.dashboard_port}"

        server = make_server(settings)
        self._dashboard_server = server

        self.app.call_from_thread(
            self.notify,
            f"Dashboard starting at {url}",
            title="Dashboard",
            timeout=6,
        )
        # Open the browser ~1 s after this thread starts so uvicorn has time to bind.
        threading.Timer(1.0, _open_url, args=[url]).start()
        try:
            asyncio.run(server.serve())  # blocks until server.should_exit is set
        except OSError as exc:
            self.app.call_from_thread(
                self.notify,
                f"Dashboard error: {exc}",
                title="Dashboard",
                severity="error",
                timeout=8,
            )
        finally:
            self._dashboard_server = None
            self._dashboard_running = False
            self.app.call_from_thread(self._rebuild_actions)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_scrape(self) -> None:
        from linkedin_vault.tui.screens.scrape_screen import ScrapeScreen

        self.app.push_screen(ScrapeScreen())

    def action_enrich(self) -> None:
        from linkedin_vault.tui.screens.enrich_screen import EnrichScreen

        self.app.push_screen(EnrichScreen())

    def action_chat(self) -> None:
        from linkedin_vault.tui.screens.chat_screen import ChatScreen

        self.app.push_screen(ChatScreen())

    def action_login(self) -> None:
        from linkedin_vault.tui.screens.login_screen import LoginScreen

        self.app.push_screen(LoginScreen())

    def action_dashboard(self) -> None:
        if self._dashboard_running:
            # Server already running — just reopen the browser tab.
            from linkedin_vault.config import load_settings

            settings = load_settings()
            url = f"http://{settings.dashboard_host}:{settings.dashboard_port}"
            _open_url(url)
            self.notify(f"Dashboard already running at {url}", title="Dashboard", timeout=4)
            return
        # Set flag on the event-loop thread (atomically w.r.t. key-press handlers)
        # before spawning the worker to prevent a double-start race.
        self._dashboard_running = True
        self._rebuild_actions()
        self._open_dashboard()

    def action_settings(self) -> None:
        from linkedin_vault.tui.screens.config_wizard import ConfigWizardScreen

        self.app.push_screen(ConfigWizardScreen())

    def action_quit(self) -> None:
        self.app.exit()
