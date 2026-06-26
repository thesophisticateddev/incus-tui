"""Tests for cross-pane copy in the access screen (no real incus mount)."""

import os
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from incus_tui.components.access import AccessScreen
from incus_tui.components.explorer import FileExplorer
from incus_tui.components.incus import Container
from tests.helpers import select_node, settle, wait_for_children


class _OfflineAccess(AccessScreen):
    """AccessScreen that skips the real `incus file mount` step.

    The container pane simply uses the temp mountpoint directory as a stand-in
    filesystem, which is all the copy logic needs.
    """

    async def _mount_filesystem(self) -> None:  # pragma: no cover - trivial
        return


@pytest.mark.skipif(os.name != "posix", reason="embedded terminal needs a PTY")
async def test_cross_pane_copy_both_directions(tmp_path):
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "h.txt").write_text("from host")

    container = Container(
        name="dummy", status="Running", type="container", ipv4="", ipv6=""
    )
    screen = _OfflineAccess(container, ["sleep", "30"])

    class A(App):
        def compose(self) -> ComposeResult:
            return []

    app = A()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.push_screen(screen)
        await settle(pilot)

        host = screen.query_one("#host-explorer", FileExplorer)
        container_pane = screen.query_one("#container-explorer", FileExplorer)
        mount = Path(screen._mountpoint)

        # --- host -> container ---
        host.set_root(host_dir)
        host.action_refresh_tree()
        await wait_for_children(host, {"h.txt"}, pilot)
        await select_node(host, "h.txt", pilot)
        host.action_copy()
        await settle(pilot, rounds=10)
        assert (mount / "h.txt").exists()
        assert (mount / "h.txt").read_text() == "from host"

        # --- container -> host ---
        (mount / "c.txt").write_text("from container")
        container_pane.action_refresh_tree()
        await wait_for_children(container_pane, {"h.txt", "c.txt"}, pilot)
        await select_node(container_pane, "c.txt", pilot)
        host.set_root(host_dir)
        host.action_refresh_tree()
        await settle(pilot)
        container_pane.action_copy()
        await settle(pilot, rounds=10)
        assert (host_dir / "c.txt").exists()
        assert (host_dir / "c.txt").read_text() == "from container"


@pytest.mark.skipif(os.name != "posix", reason="embedded terminal needs a PTY")
async def test_copy_refuses_to_overwrite(tmp_path):
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "dup.txt").write_text("host version")

    container = Container(
        name="dummy", status="Running", type="container", ipv4="", ipv6=""
    )
    screen = _OfflineAccess(container, ["sleep", "30"])
    notes: list = []

    class A(App):
        def compose(self) -> ComposeResult:
            return []

    app = A()
    async with app.run_test(size=(140, 40)) as pilot:
        await app.push_screen(screen)
        await settle(pilot)
        from tests.helpers import recorder

        app.notify = recorder(notes)

        host = screen.query_one("#host-explorer", FileExplorer)
        mount = Path(screen._mountpoint)
        (mount / "dup.txt").write_text("container version")

        host.set_root(host_dir)
        host.action_refresh_tree()
        await wait_for_children(host, {"dup.txt"}, pilot)
        await select_node(host, "dup.txt", pilot)
        host.action_copy()
        await settle(pilot, rounds=10)

        # destination untouched, warning raised
        assert (mount / "dup.txt").read_text() == "container version"
        assert any("already exists" in n.message for n in notes)
