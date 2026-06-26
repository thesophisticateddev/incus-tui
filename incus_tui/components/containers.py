"""Screen that lists Incus containers and lets you access them."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label

from incus_tui.components.access import AccessScreen
from incus_tui.components.incus import (
    Container,
    IncusError,
    list_containers,
    shell_command,
    ssh_command,
)


class SSHUserScreen(ModalScreen[str | None]):
    """Ask for the username to use for an SSH connection."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    SSHUserScreen {
        align: center middle;
    }
    SSHUserScreen > * {
        width: 50;
    }
    SSHUserScreen Label {
        padding: 1 1 0 1;
    }
    SSHUserScreen Button {
        margin: 1 1;
    }
    """

    def __init__(self, container: str, default_user: str = "root") -> None:
        super().__init__()
        self._container = container
        self._default_user = default_user

    def compose(self) -> ComposeResult:
        yield Label(f"SSH into '{self._container}' as:")
        yield Input(value=self._default_user, placeholder="username")
        yield Button("Connect", variant="primary", id="connect")

    @on(Input.Submitted)
    @on(Button.Pressed, "#connect")
    def _confirm(self) -> None:
        self.dismiss(self.query_one(Input).value.strip() or self._default_user)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ContainerScreen(Screen):
    """A table of containers with shell / SSH access."""

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s,enter", "shell", "Shell (incus)"),
        ("i", "ssh", "SSH"),
        ("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        table = DataTable(cursor_type="row", zebra_stripes=True)
        table.add_columns("Name", "Status", "Type", "IPv4")
        yield table
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Incus containers"
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        try:
            containers = list_containers()
        except IncusError as exc:
            self.notify(str(exc), title="Incus error", severity="error")
            return

        if not containers:
            self.notify("No containers found.", severity="warning")
            return

        for c in containers:
            table.add_row(c.name, c.status, c.type, c.ipv4 or "-", key=c.name)
        table.focus()

    def _selected(self) -> Container | None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return None
        try:
            name = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None
        for c in list_containers():
            if c.name == name:
                return c
        return None

    def action_shell(self) -> None:
        container = self._selected()
        if container is None:
            return
        if not container.is_running:
            self.notify(
                f"'{container.name}' is {container.status.lower()}; start it first.",
                severity="warning",
            )
            return
        self.app.push_screen(AccessScreen(container, shell_command(container.name)))

    def action_ssh(self) -> None:
        container = self._selected()
        if container is None:
            return
        if not container.is_running:
            self.notify(
                f"'{container.name}' is {container.status.lower()}; start it first.",
                severity="warning",
            )
            return
        if not container.ipv4:
            self.notify(
                f"'{container.name}' has no IPv4 address to SSH into.",
                severity="warning",
            )
            return
        host = container.ipv4.split(",")[0].strip()

        def connect(user: str | None) -> None:
            if user is None:
                return
            self.app.push_screen(
                AccessScreen(container, ssh_command(user, host))
            )

        self.app.push_screen(SSHUserScreen(container.name), connect)

    def action_back(self) -> None:
        self.app.pop_screen()
