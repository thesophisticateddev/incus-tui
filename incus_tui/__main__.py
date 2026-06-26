"""CLI entry point for incus-tui."""

from __future__ import annotations

import argparse
import shutil
import sys

from incus_tui.__about__ import __version__


def _check_incus() -> bool:
    """Return True if incus is found on PATH."""
    return shutil.which("incus") is not None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="incus-tui",
        description="A terminal UI to manage Incus containers.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"incus-tui {__version__}",
    )
    args = parser.parse_args()

    if not _check_incus():
        sys.stderr.write(
            "warning: `incus` not found on PATH. "
            "Some features will not work without it.\n"
        )
        sys.stderr.flush()

    from incus_tui import IncusClientApp

    app = IncusClientApp()
    app.run()


if __name__ == "__main__":
    main()
