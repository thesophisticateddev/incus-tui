"""Screens for managing the incus daemon itself."""

from __future__ import annotations

import json
import os
import subprocess

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
)

from incus_tui.components.incus import (
    IncusError,
    IncusUnavailable,
    TrustedClient,
    admin_init_auto_command,
    admin_init_dump_command,
    admin_init_interactive_command,
    admin_init_minimal_command,
    admin_shutdown_command,
    admin_waitready_command,
    client_version,
    daemon_status,
    server_config_edit_command,
    server_config_get_command,
    server_config_set_command,
    server_config_show_command,
    server_info_command,
    server_info_raw_command,
    service_disable_command,
    service_enable_command,
    service_restart_command,
    service_start_command,
    service_status_command,
    service_stop_command,
    trust_add_command,
    trust_add_token_command,
    trust_list_command,
    trust_list_tokens_command,
    trust_remove_command,
    trust_revoke_token_command,
)
from incus_tui.components.terminal import TerminalWidget


class StatusBanner(Static):
    """A compact banner showing daemon reachability and version skew."""

    DEFAULT_CSS = """
    StatusBanner {
        height: auto;
        padding: 0 2;
    }
    StatusBanner.reachable {
        color: $text;
    }
    StatusBanner.unreachable {
        color: $error;
    }
    StatusBanner.warning {
        color: $warning;
    }
    """

    def __init__(self, status: dict[str, Any]) -> None:
        super().__init__()
        self._status = status

    def compose(self) -> ComposeResult:
        if not self._status.get("reachable"):
            yield Label(
                f"[error]✗ Daemon unreachable[/]  {self._status.get('message', '')}",
                id="status-line",
            )
            return
        parts = [
            f"[green]✓ Daemon reachable[/]",
            f"server={self._status.get('server_version', '?')}",
            f"client={self._status.get('client_version', '?')}",
        ]
        if self._status.get("clustered"):
            parts.append("[yellow]clustered[/]")
        if self._status.get("version_skew"):
            parts.append("[warning]⚠ version mismatch[/]")
        yield Label("  ".join(parts), id="status-line")


class AdminScreen(Screen):
    """Hub screen listing daemon management sub-actions."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._daemon_info: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="admin-hub"):
            yield Static("Daemon Management", classes="form-heading")
            yield StatusBanner(self._daemon_info)
            yield Vertical(id="menu-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Manage daemon"
        self._probe_daemon()
        self._build_menu()

    def _probe_daemon(self) -> None:
        try:
            status = daemon_status()
            self._daemon_info = {
                "reachable": status.reachable,
                "server_version": status.server_version,
                "client_version": status.client_version,
                "clustered": status.clustered,
                "version_skew": status.version_skew,
                "message": status.message,
            }
        except IncusUnavailable as exc:
            self._daemon_info = {"reachable": False, "message": str(exc)}
        except Exception as exc:
            self._daemon_info = {"reachable": False, "message": str(exc)}

        banner = self.query_one("#admin-hub StatusBanner", StatusBanner)
        banner.remove()
        self.query_one("#admin-hub").mount(StatusBanner(self._daemon_info), before=self.query_one("#menu-pane"))

    def _build_menu(self) -> None:
        menu = self.query_one("#menu-pane", Vertical)
        menu.remove_children()

        options = [
            ("Refresh status", self._on_refresh),
            ("View server info", self._on_server_info),
            ("Server configuration", self._on_server_config),
            ("Trust management", self._on_trust),
            ("Daemon init / setup", self._on_admin_init),
            ("Daemon lifecycle", self._on_service_lifecycle),
            ("Shutdown daemon", self._on_admin_shutdown),
        ]
        for label, handler in options:
            btn = Button(label, variant="primary", id=f"btn-{label}")
            btn.on_click = handler
            menu.mount(btn)

    def _on_refresh(self, event: Button.Pressed) -> None:
        self._probe_daemon()
        self._build_menu()

    def _on_server_info(self, event: Button.Pressed) -> None:
        self.app.push_screen(ServerInfoScreen())

    def _on_server_config(self, event: Button.Pressed) -> None:
        self.app.push_screen(ServerConfigScreen())

    def _on_trust(self, event: Button.Pressed) -> None:
        self.app.push_screen(TrustManagementScreen())

    def _on_admin_init(self, event: Button.Pressed) -> None:
        self.app.push_screen(AdminInitScreen())

    def _on_service_lifecycle(self, event: Button.Pressed) -> None:
        self.app.push_screen(ServiceLifecycleScreen())

    def _on_admin_shutdown(self, event: Button.Pressed) -> None:
        self.app.push_screen(ShutdownConfirmScreen())

    def action_back(self) -> None:
        self.app.pop_screen()


class ServerInfoScreen(Screen):
    """Display server info from ``incus info``."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="info-scroll"):
            yield Static("Server Information", classes="form-heading")
            yield Static("Loading…", id="info-content")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Server info"
        self.run_worker(self._fetch_info())

    async def _fetch_info(self) -> None:
        try:
            result = subprocess.run(
                server_info_raw_command(),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.query_one("#info-content", Static).update(
                    f"[error]Failed:[/] {result.stderr.strip()}"
                )
                return
            lines = result.stdout.splitlines()
            text = "\n".join(
                f"[dim]{i + 1:4d}[/]  {line}" for i, line in enumerate(lines)
            )
            self.query_one("#info-content", Static).update(text)
        except Exception as exc:
            self.query_one("#info-content", Static).update(f"[error]{exc}[/]")

    def action_back(self) -> None:
        self.app.pop_screen()


class ServerConfigScreen(Screen):
    """View and edit server configuration keys."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="config-scroll"):
            yield Static("Server Configuration", classes="form-heading")
            yield Static("Loading config…", id="config-content")
            with Horizontal(id="key-edit-row"):
                yield Input(placeholder="key (e.g. core.https_address)", id="config-key")
                yield Input(placeholder="value", id="config-value")
                yield Button("Set", variant="primary", id="config-set")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Server config"
        self.run_worker(self._fetch_config())

    async def _fetch_config(self) -> None:
        try:
            result = subprocess.run(
                server_config_show_command(),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.query_one("#config-content", Static).update(
                    f"[error]Failed:[/] {result.stderr.strip()}"
                )
                return
            self.query_one("#config-content", Static).update(
                f"[dim]{result.stdout}"
            )
        except Exception as exc:
            self.query_one("#config-content", Static).update(f"[error]{exc}[/]")

    @on(Button.Pressed, "#config-set")
    def _on_set(self) -> None:
        key = self.query_one("#config-key", Input).value.strip()
        value = self.query_one("#config-value", Input).value
        if not key:
            self.app.notify("A config key is required.", severity="warning")
            return

        def done(success: bool | None) -> None:
            if success:
                self.app.notify(f"Set {key} = {value!r}", severity="information")
                self.run_worker(self._fetch_config())
                self.query_one("#config-value", Input).value = ""

        cmd = server_config_set_command(key, value)
        self.app.push_screen(
            TerminalRunnerScreen(cmd, f"Setting {key}…"), done
        )

    def action_back(self) -> None:
        self.app.pop_screen()


class TrustManagementScreen(Screen):
    """List and manage trusted certificates and join tokens."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="trust-scroll"):
            yield Static("Trust Management", classes="form-heading")
            yield Button("Refresh", id="trust-refresh", variant="primary")
            yield DataTable(id="trust-table")
            yield Static("Active Tokens", classes="form-heading")
            yield DataTable(id="token-table")
            yield Button("Add certificate…", id="trust-add")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Trust management"
        table = self.query_one("#trust-table", DataTable)
        table.add_columns("Name", "Fingerprint", "Type", "PID")
        token_table = self.query_one("#token-table", DataTable)
        token_table.add_columns("Name", "ID", "Projects")
        self.run_worker(self._fetch_trust())

    async def _fetch_trust(self) -> None:
        await self._fetch_certificates()
        await self._fetch_tokens()

    async def _fetch_certificates(self) -> None:
        try:
            result = subprocess.run(
                trust_list_command(),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.app.notify(f"Failed: {result.stderr.strip()}", severity="error")
                return
            data = json.loads(result.stdout) if result.stdout.strip() else []
            table = self.query_one("#trust-table", DataTable)
            table.clear()
            for cert in data:
                table.add_row(
                    cert.get("name", ""),
                    cert.get("fingerprint", ""),
                    cert.get("type", ""),
                    str(cert.get("pid", "")),
                    key=cert.get("fingerprint"),
                )
        except json.JSONDecodeError:
            self.app.notify("Could not parse certificate list.", severity="error")
        except Exception as exc:
            self.app.notify(str(exc), severity="error")

    async def _fetch_tokens(self) -> None:
        try:
            result = subprocess.run(
                trust_list_tokens_command(),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return
            data = json.loads(result.stdout) if result.stdout.strip() else []
            table = self.query_one("#token-table", DataTable)
            table.clear()
            for tok in data:
                projects = ",".join(tok.get("projects", []) or [])
                table.add_row(
                    tok.get("name", ""),
                    tok.get("id", ""),
                    projects,
                    key=tok.get("id"),
                )
        except Exception:
            pass

    @on(Button.Pressed, "#trust-refresh")
    def _on_refresh(self) -> None:
        self.run_worker(self._fetch_trust())

    @on(Button.Pressed, "#trust-add")
    def _on_add(self) -> None:
        self.app.push_screen(TrustAddScreen())

    @on(DataTable.RowSelected, "#trust-table")
    def _on_select_trust(self, event: DataTable.RowSelected) -> None:
        fp = event.row_key.value
        self.app.push_screen(TrustDetailScreen(fp))

    def action_back(self) -> None:
        self.app.pop_screen()


class TrustAddScreen(ModalScreen[str | None]):
    """Form to add a trusted certificate or join token."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    TrustAddScreen { align: center middle; }
    TrustAddScreen > Vertical { width: 70; height: auto; background: $panel;
        border: thick $accent; padding: 1 2; }
    TrustAddScreen Label { padding-top: 1; color: $text-muted; }
    TrustAddScreen Button { margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Add trusted client")
            yield Label("Type:")
            yield OptionList("Certificate file", "Join token", id="add-type")
            yield Label("Name *", id="name-label")
            yield Input(placeholder="e.g. my-laptop", id="trust-name")
            yield Label("Certificate path (or leave blank to generate a token):", id="cert-label")
            yield Input(placeholder="/path/to/client.crt", id="cert-path")
            yield Button("Add", variant="primary", id="trust-add-confirm")

    def on_mount(self) -> None:
        self.query_one("#cert-label", Label).display = False
        self.query_one("#cert-path", Input).display = False
        self.query_one(Input, "#cert-path").focus()

    @on(OptionList.OptionSelected, "#add-type")
    def _on_type_changed(self, event: OptionList.OptionSelected) -> None:
        is_cert = event.option.prompt == "Certificate file"
        self.query_one("#name-label", Label).display = is_cert
        self.query_one("#trust-name", Input).display = is_cert
        self.query_one("#cert-label", Label).display = is_cert
        self.query_one("#cert-path", Input).display = is_cert
        if is_cert:
            self.query_one("#trust-name", Input).focus()
        else:
            self.query_one("#cert-path", Input).focus()

    @on(Button.Pressed, "#trust-add-confirm")
    def _on_confirm(self) -> None:
        name = self.query_one("#trust-name", Input).value.strip()
        cert = self.query_one("#cert-path", Input).value.strip()
        add_type = self.query_one("#add-type", OptionList)
        option = add_type.option_prompt if add_type.selected_option else "Join token"

        if option == "Certificate file":
            if not name:
                self.app.notify("Name is required for certificates.", severity="warning")
                return
            if cert:
                cmd = trust_add_command(name, cert)
            else:
                cmd = trust_add_token_command(name)
        else:
            cmd = trust_add_token_command(name) if name else trust_add_token_command("cli-token")

        def done(success: bool | None) -> None:
            self.dismiss(name)

        self.app.push_screen(TerminalRunnerScreen(cmd, "Adding trusted client…"), done)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TrustDetailScreen(ModalScreen[str | None]):
    """View details of a trusted certificate and revoke it."""

    BINDINGS = [("escape", "close", "Close")]

    DEFAULT_CSS = """
    TrustDetailScreen { align: center middle; }
    TrustDetailScreen > Vertical { width: 80; height: auto; background: $panel;
        border: thick $accent; padding: 1 2; }
    TrustDetailScreen Label { padding-top: 1; }
    TrustDetailScreen #fingerprint { color: $text-muted; }
    """

    def __init__(self, fingerprint: str) -> None:
        super().__init__()
        self._fingerprint = fingerprint

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Certificate: {self._fingerprint[:16]}…", id="cert-title")
            yield Label("Fingerprint:", id="fp-label")
            yield Static(self._fingerprint, id="fingerprint")
            yield Button("Revoke certificate", variant="error", id="revoke-btn")

    @on(Button.Pressed, "#revoke-btn")
    def _on_revoke(self) -> None:
        cmd = trust_remove_command(self._fingerprint)

        def done(success: bool | None) -> None:
            if success:
                self.app.notify("Certificate revoked.", severity="information")
                self.dismiss(self._fingerprint)

        self.app.push_screen(
            ConfirmScreen("Revoke this certificate? This cannot be undone."),
            lambda confirmed: (
                self.app.push_screen(TerminalRunnerScreen(cmd, "Revoking…"), done)
                if confirmed else None
            ),
        )

    def action_close(self) -> None:
        self.dismiss(None)


class AdminInitScreen(Screen):
    """Run ``incus admin init`` flows: dump, minimal, auto, interactive."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="init-scroll"):
            yield Static("Daemon Initialisation", classes="form-heading")
            yield Static(
                "Configure or inspect the incus daemon. "
                "These operations require the daemon to be running.",
                id="init-hint",
            )
            with Vertical(id="init-buttons"):
                yield Button("View current config (dump)", id="btn-dump", variant="primary")
                yield Button("Minimal auto-init", id="btn-minimal")
                yield Button("Guided setup (interactive)", id="btn-interactive")
                yield Static("Auto-init options", classes="form-heading")
                yield Label("Network address (e.g. 0.0.0.0:8443):")
                yield Input(placeholder="0.0.0.0:8443", id="net-addr")
                yield Label("Storage backend (e.g. zfs, btrfs, dir):")
                yield Input(placeholder="zfs", id="storage-backend")
                yield Button("Run auto-init with options", id="btn-auto")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Daemon init"

    @on(Button.Pressed, "#btn-dump")
    def _on_dump(self) -> None:
        cmd = admin_init_dump_command()

        def done(success: bool | None) -> None:
            pass

        self.app.push_screen(TerminalRunnerScreen(cmd, "Current daemon config…"), done)

    @on(Button.Pressed, "#btn-minimal")
    def _on_minimal(self) -> None:
        self.app.push_screen(
            ConfirmScreen("Run minimal daemon init? This will configure the daemon with defaults."),
            lambda confirmed: (
                self.app.push_screen(
                    TerminalRunnerScreen(
                        admin_init_minimal_command(),
                        "Running minimal init…",
                    ),
                    lambda _: None,
                )
                if confirmed else None
            ),
        )

    @on(Button.Pressed, "#btn-interactive")
    def _on_interactive(self) -> None:
        cmd = admin_init_interactive_command()
        self.app.push_screen(TerminalRunnerScreen(cmd, "Daemon setup…"))

    @on(Button.Pressed, "#btn-auto")
    def _on_auto(self) -> None:
        net_addr = self.query_one("#net-addr", Input).value.strip() or None
        storage = self.query_one("#storage-backend", Input).value.strip() or None
        if not net_addr and not storage:
            self.app.notify("Provide at least one auto-init option.", severity="warning")
            return
        cmd = admin_init_auto_command(
            network_address=net_addr,
            storage_backend=storage,
        )
        self.app.push_screen(TerminalRunnerScreen(cmd, "Running auto-init…"))

    def action_back(self) -> None:
        self.app.pop_screen()


class ServiceLifecycleScreen(Screen):
    """Start / stop / restart / enable the incus daemon via OS services."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="svc-scroll"):
            yield Static("Daemon Lifecycle", classes="form-heading")
            yield Static(id="svc-status")
            with Horizontal(id="svc-buttons"):
                yield Button("Start", id="svc-start")
                yield Button("Stop", id="svc-stop")
                yield Button("Restart", id="svc-restart")
            with Horizontal(id="svc-boot-buttons"):
                yield Button("Enable at boot", id="svc-enable")
                yield Button("Disable at boot", id="svc-disable")
            yield Static(
                "\nNote: these control the OS-level service (systemd/launchd). "
                "For graceful daemon shutdown use the Shutdown option in the admin menu.",
                id="svc-note",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Daemon lifecycle"
        self.run_worker(self._refresh_status())

    async def _refresh_status(self) -> None:
        try:
            cmd = service_status_command()
            result = subprocess.run(cmd, capture_output=True, text=True)
            status = result.stdout.strip()
            is_active = result.returncode == 0 and status == "active"
            color = "green" if is_active else "error"
            self.query_one("#svc-status", Static).update(
                f"Daemon status: [{color}]{status}[/]"
            )
        except Exception as exc:
            self.query_one("#svc-status", Static).update(
                f"[warning]Status unknown: {exc}[/]"
            )

    def _run_svc(self, cmd_fn, label: str) -> None:
        try:
            cmd = cmd_fn()
        except Exception as exc:
            self.app.notify(str(exc), severity="error")
            return

        def done(success: bool | None) -> None:
            self.app.notify(f"{label} {'succeeded' if success else 'failed'}.", severity="information" if success else "error")
            self.run_worker(self._refresh_status())

        self.app.push_screen(TerminalRunnerScreen(cmd, f"{label}…"), done)

    @on(Button.Pressed, "#svc-start")
    def _on_start(self) -> None:
        self._run_svc(lambda: service_start_command(), "Start")

    @on(Button.Pressed, "#svc-stop")
    def _on_stop(self) -> None:
        self._run_svc(lambda: service_stop_command(), "Stop")

    @on(Button.Pressed, "#svc-restart")
    def _on_restart(self) -> None:
        self._run_svc(lambda: service_restart_command(), "Restart")

    @on(Button.Pressed, "#svc-enable")
    def _on_enable(self) -> None:
        self._run_svc(lambda: service_enable_command(), "Enable at boot")

    @on(Button.Pressed, "#svc-disable")
    def _on_disable(self) -> None:
        self._run_svc(lambda: service_disable_command(), "Disable at boot")

    def action_back(self) -> None:
        self.app.pop_screen()


class ShutdownConfirmScreen(ModalScreen[bool]):
    """Strong confirmation before shutting down the incus daemon."""

    BINDINGS = [("escape", "no", "Cancel")]

    DEFAULT_CSS = """
    ShutdownConfirmScreen { align: center middle; }
    ShutdownConfirmScreen > Vertical { width: 70; height: auto; background: $panel;
        border: thick $error; padding: 1 2; }
    ShutdownConfirmScreen Label { padding-top: 1; }
    ShutdownConfirmScreen Horizontal { height: auto; align-horizontal: right; }
    ShutdownConfirmScreen Button { margin-left: 2; }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[error]⚠ Shut down the incus daemon?[/]")
            yield Label(
                "This will stop ALL running containers and VMs, "
                "then shut down the daemon. "
                "Use this only for maintenance."
            )
            yield Label("Type [bold]shutdown[/] to confirm:")
            yield Input(placeholder="shutdown", id="confirm-input")
            with Horizontal():
                yield Button("Cancel", id="no")
                yield Button("Shut down", variant="error", id="yes")

    def on_mount(self) -> None:
        self.query_one(Input, "#confirm-input").focus()

    @on(Input.Submitted)
    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        confirm = self.query_one("#confirm-input", Input).value.strip()
        if confirm != "shutdown":
            self.app.notify("Type 'shutdown' to confirm.", severity="warning")
            return
        cmd = admin_shutdown_command()

        def done(success: bool | None) -> None:
            self.dismiss(True)

        self.app.push_screen(TerminalRunnerScreen(cmd, "Shutting down daemon…"), done)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss(False)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    BINDINGS = [("escape", "no", "Cancel")]

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical { width: 64; height: auto; background: $panel;
        border: thick $error; padding: 1 2; }
    ConfirmScreen Label { padding-bottom: 1; }
    ConfirmScreen Horizontal { height: auto; align-horizontal: right; }
    ConfirmScreen Button { margin-left: 2; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._message)
            with Horizontal():
                yield Button("Cancel", id="no")
                yield Button("Confirm", variant="error", id="yes")

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss(False)


class TerminalRunnerScreen(ModalScreen[bool]):
    """Run a command in an embedded terminal and report success/failure."""

    BINDINGS = [Binding("f10", "close", "Close", priority=True)]

    DEFAULT_CSS = """
    TerminalRunnerScreen #runner-title {
        background: $accent; color: $text; text-style: bold; padding: 0 1;
    }
    TerminalRunnerScreen TerminalWidget { height: 1fr; }
    TerminalRunnerScreen #runner-status { padding: 0 1; height: auto; }
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
