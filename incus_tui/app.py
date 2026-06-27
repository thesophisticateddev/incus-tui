"""The IncusClientApp Textual application."""

from __future__ import annotations

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, OptionList

from incus_tui.components.admin import AdminScreen
from incus_tui.components.containers import ContainerScreen
from incus_tui.components.create import CreateContainerScreen
from incus_tui.components.welcome import MarkdownHeader, Welcome


class IncusClientApp(App):
    """A Textual app to manage Incus containers."""

    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield MarkdownHeader()
        yield Welcome()
        yield Footer()

    @on(OptionList.OptionSelected)
    def handle_menu(self, event: OptionList.OptionSelected) -> None:
        if event.option.prompt == "List containers":
            self.push_screen(ContainerScreen())
        elif event.option.prompt == "Create a new container":
            self.push_screen(CreateContainerScreen())
        elif event.option.prompt == "Manage daemon":
            self.push_screen(AdminScreen())
        else:
            self.notify("Not implemented yet.", severity="warning")

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )
