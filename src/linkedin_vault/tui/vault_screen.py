"""Base screen and chrome widgets for LinkedIn Vault TUI screens.

Every screen in the TUI inherits from :class:`VaultScreen` to get a
consistent one-line top bar (app name + screen title) and a one-line bottom
bar (key-binding hints).  Subclasses only need to implement
:meth:`VaultScreen.compose_content` and set the ``SCREEN_TITLE`` and
``BOTTOM_HINTS`` class attributes.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static


class VaultTopBar(Static):
    DEFAULT_CSS = """
    VaultTopBar {
        dock: top;
        height: 1;
        background: $background;
        color: $text;
        padding: 0 1;
    }
    """


class VaultBottomBar(Static):
    DEFAULT_CSS = """
    VaultBottomBar {
        dock: bottom;
        height: 1;
        background: $background;
        color: $text-muted;
        padding: 0 1;
    }
    """


class VaultScreen(Screen):
    """Base screen for all LinkedIn Vault screens — provides docked top/bottom bars."""

    SCREEN_TITLE: ClassVar[str] = ""
    BOTTOM_HINTS: ClassVar[str] = ""

    def compose(self) -> ComposeResult:
        yield VaultTopBar(self._top_text(), markup=True)
        yield from self.compose_content()
        yield VaultBottomBar(self.BOTTOM_HINTS, markup=True)

    def compose_content(self) -> Iterable[Widget]:
        return []

    def _top_text(self) -> str:
        bullet = "[#CC785C]●[/#CC785C]"
        if self.SCREEN_TITLE:
            return f"{bullet} LinkedIn Vault  ·  {self.SCREEN_TITLE}"
        return f"{bullet} LinkedIn Vault"
