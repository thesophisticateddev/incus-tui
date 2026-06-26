"""Container access screen: a dual-pane file manager plus an embedded shell."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from incus_tui.components.explorer import FileExplorer
from incus_tui.components.incus import Container, mount_command
from incus_tui.components.terminal import TerminalWidget


class AccessScreen(Screen):
    """Dual-pane host/container file manager with an embedded shell."""

    BINDINGS = [
        Binding("f10", "close", "Close", priority=True),
        Binding("f2", "focus_next_pane", "Next pane", priority=True),
    ]

    DEFAULT_CSS = """
    AccessScreen #file-pane {
        width: 46;
        border-right: solid $accent;
    }
    AccessScreen #host-explorer {
        border-bottom: solid $panel;
    }
    AccessScreen TerminalWidget {
        width: 1fr;
    }
    """

    def __init__(self, container: Container, command: list[str]) -> None:
        super().__init__()
        self._container = container
        self._command = command
        self._host_root = Path.cwd()
        self._mountpoint: str | None = tempfile.mkdtemp(
            prefix=f"incus-{container.name}-"
        )
        self._mount_proc: asyncio.subprocess.Process | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="file-pane"):
                yield FileExplorer(
                    self._host_root,
                    "Host",
                    floor=Path(self._host_root).anchor or os.sep,
                    tree_id="host",
                    id="host-explorer",
                )
                yield FileExplorer(
                    self._mountpoint,
                    "Container (mounting…)",
                    floor=self._mountpoint,
                    tree_id="container",
                    id="container-explorer",
                )
            yield TerminalWidget(self._command)
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"{self._container.name} — files + shell"
        self.run_worker(self._mount_filesystem(), exclusive=True)

    @property
    def _container_explorer(self) -> FileExplorer:
        return self.query_one("#container-explorer", FileExplorer)

    async def _mount_filesystem(self) -> None:
        explorer = self._container_explorer
        if self._mountpoint is None:
            return
        try:
            self._mount_proc = await asyncio.create_subprocess_exec(
                *mount_command(self._container.name, self._mountpoint),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            explorer.set_title(f"Container — mount failed ({exc})")
            return

        for _ in range(50):
            if os.path.ismount(self._mountpoint):
                explorer.set_title(f"{self._container.name}:/")
                explorer.action_refresh_tree()
                return
            if self._mount_proc.returncode is not None:
                break
            await asyncio.sleep(0.2)

        stderr = b""
        if self._mount_proc is not None and self._mount_proc.stderr is not None:
            try:
                stderr = await asyncio.wait_for(self._mount_proc.stderr.read(), 1)
            except asyncio.TimeoutError:
                pass
        reason = stderr.decode(errors="replace").strip() or "could not mount"
        explorer.set_title(f"Container — mount failed ({reason})")

    @on(FileExplorer.CopyRequested)
    def _copy_between_panes(self, event: FileExplorer.CopyRequested) -> None:
        host = self.query_one("#host-explorer", FileExplorer)
        if event.explorer is host:
            dest_explorer, direction = self._container_explorer, "Host → Container"
        else:
            dest_explorer, direction = host, "Container → Host"
        destination = dest_explorer.target_dir() / event.path.name
        self.run_worker(
            self._copy(event.path, destination, dest_explorer, direction),
            exclusive=False,
        )

    async def _copy(
        self, src: Path, dest: Path, dest_explorer: FileExplorer, direction: str
    ) -> None:
        if dest.exists():
            self.notify(
                f"'{dest.name}' already exists in the destination.", severity="warning"
            )
            return
        try:
            if src.is_dir() and not src.is_symlink():
                await asyncio.to_thread(shutil.copytree, src, dest, symlinks=True)
            else:
                await asyncio.to_thread(shutil.copy2, src, dest, follow_symlinks=False)
        except PermissionError:
            self.notify(f"Permission denied copying {src.name}.", severity="error")
            return
        except OSError as exc:
            self.notify(f"Copy failed: {exc}", severity="error")
            return
        self.notify(f"{direction}: copied {src.name}", severity="information")
        dest_explorer.action_refresh_tree()

    @on(TerminalWidget.Exited)
    def _terminal_exited(self) -> None:
        self.action_close()

    def action_focus_next_pane(self) -> None:
        panes = [
            self.query_one("#host-explorer", FileExplorer).tree,
            self._container_explorer.tree,
            self.query_one(TerminalWidget),
        ]
        focused = [i for i, p in enumerate(panes) if p is self.focused]
        nxt = panes[(focused[0] + 1) % len(panes)] if focused else panes[0]
        nxt.focus()

    def action_close(self) -> None:
        self._teardown_mount()
        if self.is_current:
            self.app.pop_screen()

    def on_unmount(self) -> None:
        self._teardown_mount()

    def _teardown_mount(self) -> None:
        mountpoint = self._mountpoint
        if mountpoint is None:
            return
        self._mountpoint = None

        if self._mount_proc is not None and self._mount_proc.returncode is None:
            try:
                self._mount_proc.terminate()
            except ProcessLookupError:
                pass

        self._unmount(mountpoint)
        shutil.rmtree(mountpoint, ignore_errors=True)

    @staticmethod
    def _unmount(mountpoint: str) -> None:
        """Best-effort unmount that works across Linux (FUSE) and macOS."""
        if os.name != "posix":
            return
        for tool, args in (
            ("fusermount3", ["-u"]),
            ("fusermount", ["-u"]),
            ("umount", []),
        ):
            path = shutil.which(tool)
            if path is None:
                continue
            result = subprocess.run(
                [path, *args, mountpoint],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                return
