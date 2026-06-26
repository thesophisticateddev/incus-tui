"""A full-featured directory explorer widget with graceful error handling."""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Iterator

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Label, Static
from textual.worker import Worker

try:
    import grp
    import pwd

    _IDS = True
except ImportError:  # pragma: no cover - Windows
    _IDS = False

ICONS = {
    "up": "^",
    "new": "+",
    "rename": "~",
    "delete": "x",
    "copy": ">",
    "info": "i",
    "refresh": "*",
}


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def describe_path(path: Path) -> dict[str, str]:
    """Collect human-readable properties for a path (no exceptions escape)."""
    info: dict[str, str] = {"Path": str(path)}
    try:
        st = path.lstat()
    except OSError as exc:
        info["Error"] = str(exc)
        return info

    if stat.S_ISLNK(st.st_mode):
        kind = "Symlink"
        try:
            info["Target"] = os.readlink(path)
        except OSError:
            pass
    elif stat.S_ISDIR(st.st_mode):
        kind = "Directory"
    elif stat.S_ISREG(st.st_mode):
        kind = "File"
    else:
        kind = "Special"

    info["Type"] = kind
    info["Permissions"] = f"{stat.filemode(st.st_mode)}  ({oct(st.st_mode & 0o777)})"
    info["Size"] = _human_size(st.st_size)

    owner = str(st.st_uid)
    group = str(st.st_gid)
    if _IDS:
        try:
            owner = f"{pwd.getpwuid(st.st_uid).pw_name} ({st.st_uid})"
        except (KeyError, OSError):
            pass
        try:
            group = f"{grp.getgrgid(st.st_gid).gr_name} ({st.st_gid})"
        except (KeyError, OSError):
            pass
    info["Owner"] = owner
    info["Group"] = group
    info["Modified"] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return info


class ExplorerTree(DirectoryTree):
    """DirectoryTree that surfaces directory-read errors as messages."""

    class PathError(Message):
        def __init__(self, tree: "ExplorerTree", path: Path, error: str) -> None:
            super().__init__()
            self.tree = tree
            self.path = path
            self.error = error

    def _directory_content(self, location: Path, worker: Worker) -> Iterator[Path]:
        try:
            entries = list(location.iterdir())
        except OSError as exc:
            reason = (
                "Permission denied" if isinstance(exc, PermissionError) else str(exc)
            )
            self.post_message(self.PathError(self, location, reason))
            return
        for entry in entries:
            if worker.is_cancelled:
                break
            yield entry


class TextPromptScreen(ModalScreen[str | None]):
    """Generic single-line text prompt (used for new folder / rename)."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    TextPromptScreen { align: center middle; }
    TextPromptScreen > Vertical { width: 60; height: auto; background: $panel;
        border: thick $accent; padding: 1 2; }
    TextPromptScreen Label { padding-bottom: 1; }
    TextPromptScreen Button { margin-top: 1; }
    """

    def __init__(self, prompt: str, value: str = "", button: str = "OK") -> None:
        super().__init__()
        self._prompt = prompt
        self._value = value
        self._button = button

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._prompt)
            yield Input(value=self._value, placeholder="name")
            yield Button(self._button, variant="primary", id="ok")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(self.query_one(Input).value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


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
                yield Button("Delete", variant="error", id="yes")

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def action_no(self) -> None:
        self.dismiss(False)


class PropertiesScreen(ModalScreen[None]):
    BINDINGS = [("escape,enter,q", "dismiss", "Close")]
    DEFAULT_CSS = """
    PropertiesScreen { align: center middle; }
    PropertiesScreen > Vertical { width: 72; height: auto; max-height: 80%;
        background: $panel; border: thick $accent; padding: 1 2; }
    PropertiesScreen .row { height: auto; }
    PropertiesScreen .key { width: 14; color: $text-muted; text-style: bold; }
    PropertiesScreen #hint { padding-top: 1; color: $text-muted; }
    """

    def __init__(self, info: dict[str, str]) -> None:
        super().__init__()
        self._info = info

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Properties", classes="key")
            for key, value in self._info.items():
                with Horizontal(classes="row"):
                    yield Static(key, classes="key")
                    yield Static(value)
            yield Static("Press Esc to close", id="hint")

    def action_dismiss(self) -> None:
        self.dismiss(None)


class FileExplorer(Vertical):
    """A directory tree with a toolbar; reusable for host and container."""

    BINDINGS = [
        Binding("u", "go_up", "Up", show=False),
        Binding("n", "new_folder", "New folder", show=False),
        Binding("m", "rename", "Rename", show=False),
        Binding("delete", "delete", "Delete", show=False),
        Binding("c", "copy", "Copy to other pane", show=False),
        Binding("i", "properties", "Properties", show=False),
        Binding("r", "refresh_tree", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    FileExplorer { height: 1fr; }
    FileExplorer .pane-title {
        background: $accent; color: $text; text-style: bold; padding: 0 1;
    }
    FileExplorer #toolbar {
        height: auto; layout: grid; grid-size: 4; grid-rows: 1;
        grid-gutter: 0 1; background: $boost; padding: 0 1;
    }
    FileExplorer #toolbar Button {
        width: 1fr; height: 1; min-width: 0; border: none; padding: 0;
    }
    FileExplorer DirectoryTree { height: 1fr; }
    """

    class CopyRequested(Message):
        def __init__(self, explorer: "FileExplorer", path: Path) -> None:
            super().__init__()
            self.explorer = explorer
            self.path = path

    def __init__(
        self,
        root: str | Path,
        title: str,
        floor: str | Path | None = None,
        tree_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._root = Path(root)
        self._title = title
        self._floor = os.path.normpath(str(floor)) if floor is not None else None
        self._tree_id = tree_id

    def compose(self) -> ComposeResult:
        yield Static(
            self._title_text(), classes="pane-title", id=f"{self._tree_id}-title"
        )
        with Horizontal(id="toolbar"):
            yield Button(f"{ICONS['up']} Up", id="up")
            yield Button(f"{ICONS['new']} New", id="new")
            yield Button(f"{ICONS['rename']} Rename", id="rename")
            yield Button(f"{ICONS['delete']} Delete", id="delete")
            yield Button(f"{ICONS['copy']} Copy", id="copy")
            yield Button(f"{ICONS['info']} Info", id="info")
            yield Button(f"{ICONS['refresh']} Refresh", id="refresh")
        yield ExplorerTree(str(self._root), id=self._tree_id)

    @property
    def tree(self) -> ExplorerTree:
        return self.query_one(ExplorerTree)

    def _title_text(self) -> str:
        return f" {self._title}: {self._root} "

    def _refresh_title(self) -> None:
        self.query_one(f"#{self._tree_id}-title", Static).update(self._title_text())

    def set_title(self, title: str) -> None:
        self._title = title
        self._refresh_title()

    def set_root(self, path: Path) -> None:
        self._root = path
        self.tree.path = str(path)
        self._refresh_title()

    def _selected_path(self) -> Path | None:
        node = self.tree.cursor_node
        if node is not None and node.data is not None:
            return node.data.path
        return None

    def target_dir(self) -> Path:
        """Where new items land: the selected dir, its parent, or the root."""
        selected = self._selected_path()
        if selected is None:
            return self._root
        return selected if selected.is_dir() else selected.parent

    def _require_selection(self, what: str) -> Path | None:
        path = self._selected_path()
        if path is None:
            self.app.notify(f"Select a file or folder to {what}.", severity="warning")
        return path

    @on(Button.Pressed)
    def _toolbar(self, event: Button.Pressed) -> None:
        actions = {
            "up": self.action_go_up,
            "new": self.action_new_folder,
            "rename": self.action_rename,
            "delete": self.action_delete,
            "copy": self.action_copy,
            "info": self.action_properties,
            "refresh": self.action_refresh_tree,
        }
        action = actions.get(event.button.id or "")
        if action is not None:
            event.stop()
            action()

    @on(ExplorerTree.PathError)
    def _path_error(self, event: ExplorerTree.PathError) -> None:
        self.app.notify(
            f"{event.path}: {event.error}",
            title="Cannot open folder",
            severity="error",
        )

    def action_go_up(self) -> None:
        current = os.path.normpath(str(self._root))
        parent = os.path.dirname(current)
        if parent == current:
            self.app.notify("Already at the filesystem root.", severity="warning")
            return
        if self._floor is not None:
            try:
                allowed = os.path.commonpath([parent, self._floor]) == self._floor
            except ValueError:
                allowed = False
            if not allowed:
                self.app.notify(
                    "Already at the top of this filesystem.", severity="warning"
                )
                return
        self.set_root(Path(parent))

    def action_refresh_tree(self) -> None:
        self.tree.reload()

    def action_new_folder(self) -> None:
        target = self.target_dir()

        def create(name: str | None) -> None:
            if not name:
                return
            new_dir = target / name
            try:
                new_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                self.app.notify(f"'{name}' already exists.", severity="warning")
                return
            except PermissionError:
                self.app.notify(
                    f"Permission denied creating '{name}'.", severity="error"
                )
                return
            except OSError as exc:
                self.app.notify(f"Could not create folder: {exc}", severity="error")
                return
            self.app.notify(f"Created {new_dir}", severity="information")
            self.tree.reload()

        self.app.push_screen(TextPromptScreen(f"New folder in:\n{target}", button="Create"), create)

    def action_rename(self) -> None:
        path = self._require_selection("rename")
        if path is None:
            return

        def rename(new_name: str | None) -> None:
            if not new_name or new_name == path.name:
                return
            destination = path.parent / new_name
            if destination.exists():
                self.app.notify(f"'{new_name}' already exists.", severity="warning")
                return
            try:
                path.rename(destination)
            except PermissionError:
                self.app.notify("Permission denied renaming.", severity="error")
                return
            except OSError as exc:
                self.app.notify(f"Could not rename: {exc}", severity="error")
                return
            self.app.notify(f"Renamed to {new_name}", severity="information")
            self.tree.reload()

        self.app.push_screen(
            TextPromptScreen(f"Rename:\n{path}", value=path.name, button="Rename"),
            rename,
        )

    def action_delete(self) -> None:
        path = self._require_selection("delete")
        if path is None:
            return

        def confirmed(yes: bool) -> None:
            if yes:
                self.run_worker(self._do_delete(path), exclusive=False)

        kind = "folder and its contents" if path.is_dir() else "file"
        self.app.push_screen(
            ConfirmScreen(f"Delete this {kind}?\n\n{path}\n\nThis cannot be undone."),
            confirmed,
        )

    async def _do_delete(self, path: Path) -> None:
        try:
            if path.is_dir() and not path.is_symlink():
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(os.remove, path)
        except PermissionError:
            self.app.notify(f"Permission denied deleting {path.name}.", severity="error")
            return
        except OSError as exc:
            self.app.notify(f"Could not delete: {exc}", severity="error")
            return
        self.app.notify(f"Deleted {path.name}", severity="information")
        self.tree.reload()

    def action_copy(self) -> None:
        path = self._require_selection("copy")
        if path is None:
            return
        self.post_message(self.CopyRequested(self, path))

    def action_properties(self) -> None:
        path = self._selected_path()
        if path is None:
            self.app.notify("Select a file or folder first.", severity="warning")
            return
        self.app.push_screen(PropertiesScreen(describe_path(path)))
