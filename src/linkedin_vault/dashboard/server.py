"""Uvicorn server helpers for the LinkedIn Vault dashboard.

:func:`make_server` returns a configured :class:`uvicorn.Server` instance.
The caller runs it with ``asyncio.run(server.serve())``, which blocks until
``server.should_exit`` is set to ``True``.  This design lets the TUI signal
a clean shutdown from ``on_unmount`` without hanging Python's atexit thread
join.

:func:`run_dashboard` is a convenience wrapper for the CLI (blocking call).
"""

import asyncio

import uvicorn

from linkedin_vault.config import Settings


def make_server(settings: Settings) -> uvicorn.Server:
    config = uvicorn.Config(
        "linkedin_vault.dashboard.app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level="warning",
    )
    return uvicorn.Server(config)


def run_dashboard(settings: Settings) -> None:
    asyncio.run(make_server(settings).serve())
