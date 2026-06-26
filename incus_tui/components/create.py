"""Interactive form to create (launch) a new Incus container."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    Switch,
)

from incus_tui.components.incus import (
    launch_command,
    normalize_image,
    validate_instance_name,
    validate_memory,
)
from incus_tui.components.terminal import TerminalWidget

DISTROS: list[tuple[str, str]] = [
    ("Ubuntu 24.04 LTS", "images:ubuntu/24.04"),
    ("Ubuntu 22.04 LTS", "images:ubuntu/22.04"),
    ("Debian 12 (Bookworm)", "images:debian/12"),
    ("Debian 11 (Bullseye)", "images:debian/11"),
    ("Alpine 3.22", "images:alpine/3.22"),
    ("Alpine Edge", "images:alpine/edge"),
    ("Arch Linux", "images:archlinux"),
    ("Fedora 43", "images:fedora/43"),
    ("Rocky Linux 9", "images:rockylinux/9"),
    ("AlmaLinux 9", "images:almalinux/9"),
    ("CentOS 9-Stream", "images:centos/9-Stream"),
    ("openSUSE Tumbleweed", "images:opensuse/tumbleweed"),
]


class CommandRunnerScreen(ModalScreen[bool]):
    """Runs a command in an embedded terminal and reports the result."""

    BINDINGS = [Binding("f10", "close", "Close", priority=True)]

    DEFAULT_CSS = """
    CommandRunnerScreen #runner-title {
        background: $accent; color: $text; text-style: bold; padding: 0 1;
    }
    CommandRunnerScreen TerminalWidget { height: 1fr; }
    CommandRunnerScreen #runner-status { padding: 0 1; height: auto; }
    """

    def __init__(self, command: list[str], title: str) -> None:
        super().__init__()
        self._command = command
        self._title = title
        self._success = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._title, id="runner-title")
        yield TerminalWidget(self._command)
        yield Static("Running… press F10 to cancel.", id="runner-status")
        yield Footer()

    @on(TerminalWidget.Exited)
    def _finished(self, event: TerminalWidget.Exited) -> None:
        self._success = event.returncode == 0
        status = self.query_one("#runner-status", Static)
        if self._success:
            status.update("[b green]✓ Done. Press F10 to continue.[/]")
        else:
            status.update(
                f"[b red]✗ Failed (exit {event.returncode}). Press F10 to close.[/]"
            )

    def action_close(self) -> None:
        self.dismiss(self._success)


class CreateContainerScreen(Screen):
    """A form for configuring and launching a new container."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    CreateContainerScreen #form {
        width: 72; max-width: 100%; height: auto; padding: 1 2;
        margin: 1 2; border: round $accent;
    }
    CreateContainerScreen Label { padding-top: 1; color: $text-muted; }
    CreateContainerScreen Input, CreateContainerScreen Select { width: 100%; }
    CreateContainerScreen #vm-row { height: auto; padding-top: 1; }
    CreateContainerScreen #vm-row Label { padding: 0 1 0 0; }
    CreateContainerScreen #buttons { height: auto; padding-top: 1; align-horizontal: right; }
    CreateContainerScreen #buttons Button { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            yield Static("Create a new container", classes="form-heading")

            yield Label("Name *")
            yield Input(placeholder="e.g. web-server", id="name")

            yield Label("Distribution")
            yield Select(DISTROS, value=DISTROS[0][1], allow_blank=False, id="distro")

            yield Label("Custom image (overrides the distribution above)")
            yield Input(placeholder="e.g. images:debian/13 or local:my-image", id="custom")

            yield Label("CPU cores (optional)")
            yield Input(placeholder="e.g. 2", type="integer", id="cpu")

            yield Label("Memory (optional)")
            yield Input(placeholder="e.g. 2GiB", id="memory")

            with Horizontal(id="vm-row"):
                yield Label("Virtual machine instead of container")
                yield Switch(value=False, id="vm")

            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", variant="primary", id="create")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Create container"
        self.query_one("#name", Input).focus()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.app.pop_screen()

    @on(Input.Submitted)
    @on(Button.Pressed, "#create")
    def _create(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        error = validate_instance_name(name)
        if error:
            self._fail(error, "#name")
            return

        custom = self.query_one("#custom", Input).value.strip()
        image = normalize_image(custom) if custom else self.query_one("#distro", Select).value

        cpu = self.query_one("#cpu", Input).value.strip() or None
        if cpu and not cpu.isdigit():
            self._fail("CPU must be a whole number of cores.", "#cpu")
            return

        memory = self.query_one("#memory", Input).value.strip() or None
        if memory:
            mem_error = validate_memory(memory)
            if mem_error:
                self._fail(mem_error, "#memory")
                return

        vm = self.query_one("#vm", Switch).value
        command = launch_command(image, name, cpu=cpu, memory=memory, vm=vm)

        def after(success: bool | None) -> None:
            if success:
                self.app.notify(f"Container '{name}' created.", severity="information")
                from incus_tui.components.containers import ContainerScreen

                self.app.switch_screen(ContainerScreen())

        self.app.push_screen(
            CommandRunnerScreen(command, f"Creating '{name}'…"), after
        )

    def _fail(self, message: str, focus: str) -> None:
        self.app.notify(message, title="Invalid configuration", severity="error")
        self.query_one(focus, Input).focus()
