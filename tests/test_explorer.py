"""Headless tests for the FileExplorer widget and its dialogs."""

import os

from textual.widgets import Button, Input

from incus_tui.components.explorer import ConfirmScreen, FileExplorer, TextPromptScreen, describe_path
from tests.helpers import (
    ExplorerApp,
    recorder,
    select_node,
    settle,
    wait_for_children,
)


# -- describe_path (pure) ------------------------------------------------------


def test_describe_path_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    os.chmod(f, 0o640)
    info = describe_path(f)
    assert info["Type"] == "File"
    assert info["Permissions"].startswith("-rw-r-----")
    assert "0o640" in info["Permissions"]
    assert info["Size"] == "5 B"
    assert set(info) >= {"Path", "Type", "Permissions", "Size", "Owner", "Group", "Modified"}


def test_describe_path_dir(tmp_path):
    assert describe_path(tmp_path)["Type"] == "Directory"


def test_describe_path_symlink(tmp_path):
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "l"
    link.symlink_to(target)
    info = describe_path(link)
    assert info["Type"] == "Symlink"
    assert info["Target"] == str(target)


# -- toolbar -------------------------------------------------------------------


async def test_button_labels_use_ascii_icons(tmp_path):
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        labels = [b.label.plain for b in app.query(Button)]
    assert labels == [
        "^ Up",
        "+ New",
        "~ Rename",
        "x Delete",
        "> Copy",
        "i Info",
        "* Refresh",
    ]


# -- navigation / floor clamp --------------------------------------------------


async def test_go_up_and_floor_clamp(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    app = ExplorerApp(str(sub), floor=str(tmp_path))
    notes: list = []
    async with app.run_test() as pilot:
        app.notify = recorder(notes)
        exp = app.query_one(FileExplorer)

        exp.action_go_up()  # sub -> tmp_path (== floor, allowed)
        assert os.path.normpath(str(exp._root)) == os.path.normpath(str(tmp_path))

        exp.action_go_up()  # would go above floor -> blocked
        assert os.path.normpath(str(exp._root)) == os.path.normpath(str(tmp_path))
        assert any("top of this filesystem" in n.message for n in notes)


# -- permission error popup ----------------------------------------------------


async def test_permission_error_toast(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (tmp_path / "ok").mkdir()
    os.chmod(locked, 0)
    app = ExplorerApp(str(tmp_path), floor=str(tmp_path))
    notes: list = []
    try:
        async with app.run_test() as pilot:
            app.notify = recorder(notes)
            exp = app.query_one(FileExplorer)
            await wait_for_children(exp, {"locked", "ok"}, pilot)
            node = await select_node(exp, "locked", pilot)
            node.expand()
            await settle(pilot)
            assert any("Permission denied" in n.message for n in notes)
            assert any(n.severity == "error" for n in notes)
    finally:
        os.chmod(locked, 0o755)


# -- create folder -------------------------------------------------------------


async def test_new_folder_create_and_duplicate(tmp_path):
    app = ExplorerApp(str(tmp_path), floor=str(tmp_path))
    notes: list = []
    async with app.run_test() as pilot:
        app.notify = recorder(notes)
        exp = app.query_one(FileExplorer)

        exp.action_new_folder()
        await pilot.pause()
        assert isinstance(app.screen, TextPromptScreen)
        app.screen.query_one(Input).value = "newdir"
        await pilot.press("enter")
        await settle(pilot)
        assert (tmp_path / "newdir").is_dir()

        exp.action_new_folder()
        await pilot.pause()
        app.screen.query_one(Input).value = "newdir"
        await pilot.press("enter")
        await settle(pilot)
        assert any("already exists" in n.message for n in notes)


# -- rename --------------------------------------------------------------------


async def test_rename_and_collision(tmp_path):
    (tmp_path / "old.txt").write_text("x")
    (tmp_path / "taken.txt").write_text("y")
    app = ExplorerApp(str(tmp_path), floor=str(tmp_path))
    notes: list = []
    async with app.run_test() as pilot:
        app.notify = recorder(notes)
        exp = app.query_one(FileExplorer)
        await wait_for_children(exp, {"old.txt", "taken.txt"}, pilot)

        await select_node(exp, "old.txt", pilot)
        exp.action_rename()
        await pilot.pause()
        assert isinstance(app.screen, TextPromptScreen)
        app.screen.query_one(Input).value = "new.txt"
        await pilot.press("enter")
        await settle(pilot)
        assert (tmp_path / "new.txt").exists()
        assert not (tmp_path / "old.txt").exists()

        await wait_for_children(exp, {"new.txt", "taken.txt"}, pilot)
        await select_node(exp, "new.txt", pilot)
        exp.action_rename()
        await pilot.pause()
        app.screen.query_one(Input).value = "taken.txt"
        await pilot.press("enter")
        await settle(pilot)
        assert any("already exists" in n.message for n in notes)


# -- delete --------------------------------------------------------------------


async def test_delete_file_dir_and_cancel(tmp_path):
    (tmp_path / "victim.txt").write_text("x")
    nested = tmp_path / "vdir" / "sub"
    nested.mkdir(parents=True)
    (nested / "f").write_text("y")
    (tmp_path / "keep.txt").write_text("z")

    app = ExplorerApp(str(tmp_path), floor=str(tmp_path))
    async with app.run_test() as pilot:
        exp = app.query_one(FileExplorer)
        await wait_for_children(exp, {"victim.txt", "vdir", "keep.txt"}, pilot)

        # delete a file
        await select_node(exp, "victim.txt", pilot)
        exp.action_delete()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.click("#yes")
        await settle(pilot)
        assert not (tmp_path / "victim.txt").exists()

        # delete a non-empty directory
        await wait_for_children(exp, {"vdir", "keep.txt"}, pilot)
        await select_node(exp, "vdir", pilot)
        exp.action_delete()
        await pilot.pause()
        await pilot.click("#yes")
        await settle(pilot)
        assert not (tmp_path / "vdir").exists()

        # cancelling keeps the file
        await wait_for_children(exp, {"keep.txt"}, pilot)
        await select_node(exp, "keep.txt", pilot)
        exp.action_delete()
        await pilot.pause()
        await pilot.press("escape")
        await settle(pilot)
        assert (tmp_path / "keep.txt").exists()
