"""Welcome screen components."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.widgets import OptionList, Static

try:
    from pyfiglet import figlet_format

    _TITLE_ART = figlet_format("INCUS Manager", font="standard").rstrip("\n")
except Exception:  # pragma: no cover - pyfiglet missing
    _TITLE_ART = "INCUS Manager"

_DESCRIPTION = (
    "A terminal UI to list, access and manage your Incus containers — "
    "open an embedded shell and browse host and container files side by side."
)


class MarkdownHeader(Vertical):
    """Large, left-aligned application banner with a short description."""

    DEFAULT_CSS = """
    MarkdownHeader {
        height: auto;
        padding: 1 2 0 2;
        align-horizontal: left;
    }
    MarkdownHeader #app-title {
        width: auto;
        color: $accent;
        text-style: bold;
        text-align: left;
    }
    MarkdownHeader #app-subtitle {
        width: auto;
        padding-top: 1;
        color: $text-muted;
        text-align: left;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_TITLE_ART, id="app-title")
        yield Static(_DESCRIPTION, id="app-subtitle")


class Welcome(HorizontalGroup):
    CSS_PATH = "option_list.tcss"

    def compose(self) -> ComposeResult:
        yield OptionList(
            "Create a new container",
            "List containers",
            "Delete a container",
            "Update a container",
            "View container details",
        )
