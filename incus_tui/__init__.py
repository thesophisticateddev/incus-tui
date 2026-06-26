"""incus-tui, a terminal UI for managing Incus containers."""

from __future__ import annotations

from incus_tui.__about__ import __version__
from incus_tui.app import IncusClientApp

__all__ = ["IncusClientApp", "__version__"]
