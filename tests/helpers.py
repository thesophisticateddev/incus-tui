"""Shared helpers for the headless Textual tests."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Iterable

from textual.app import App, ComposeResult

from incus_tui.components.explorer import FileExplorer


class ExplorerApp(App):
    """Minimal host app wrapping a single FileExplorer for tests."""

    def __init__(self, root: str, floor: str | None = None) -> None:
        super().__init__()
        self._root = root
        self._floor = floor

    def compose(self) -> ComposeResult:
        yield FileExplorer(self._root, "Test", floor=self._floor, tree_id="t")


def recorder(store: list):
    """Return a drop-in replacement for ``app.notify`` that records calls."""

    def notify(message, *args, title: str = "", severity: str = "information", **kwargs):
        store.append(
            SimpleNamespace(message=str(message), title=title, severity=severity)
        )

    return notify


async def settle(pilot, rounds: int = 6, delay: float = 0.1) -> None:
    """Let the event loop, workers and threads catch up."""
    for _ in range(rounds):
        await pilot.pause()
        await asyncio.sleep(delay)


def find_node(explorer: FileExplorer, name: str):
    for child in explorer.tree.root.children:
        if child.data and child.data.path.name == name:
            return child
    return None


async def wait_for_children(
    explorer: FileExplorer, names: Iterable[str], pilot, timeout: float = 5.0
) -> None:
    wanted = set(names)
    deadline = time.time() + timeout
    present: set[str] = set()
    while time.time() < deadline:
        present = {
            c.data.path.name for c in explorer.tree.root.children if c.data
        }
        if wanted <= present:
            return
        await pilot.pause()
        await asyncio.sleep(0.1)
    raise AssertionError(f"children {wanted} never loaded; saw {present}")


async def select_node(explorer: FileExplorer, name: str, pilot):
    node = find_node(explorer, name)
    assert node is not None, f"node {name!r} not found"
    explorer.tree.move_cursor(node)
    await pilot.pause()
    return node
