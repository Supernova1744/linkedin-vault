"""Logging configuration helpers for LinkedIn Vault.

Call :func:`configure_logging` once at startup to set up Rich-formatted
logging with the requested log level.  Subsequent calls are no-ops (guarded
by the ``_configured`` flag) so it is safe to call from multiple entry points.

Use :func:`get_logger` everywhere else to obtain a standard :class:`logging.Logger`.
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)
_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = RichHandler(
        console=_console,
        show_time=True,
        show_path=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        markup=True,
    )
    handler.setLevel(numeric_level)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("asyncio", "aiosqlite", "httpx", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    if not _configured:
        configure_logging()
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
