"""Compatibility shim: run incus_tui from the source checkout."""

from incus_tui import IncusClientApp

if __name__ == "__main__":
    app = IncusClientApp()
    app.run()
