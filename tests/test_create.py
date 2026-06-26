"""Headless tests for the create-container form."""

import os

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Select, Switch

from incus_tui.components.create import CommandRunnerScreen, CreateContainerScreen
from tests.helpers import recorder, settle


class _CreateApp(App):
    def compose(self) -> ComposeResult:
        return []

    async def open_form(self):
        screen = CreateContainerScreen()
        await self.push_screen(screen)
        return screen


async def test_invalid_name_blocks_creation():
    app = _CreateApp()
    notes: list = []
    pushed: list = []
    async with app.run_test(size=(100, 40)) as pilot:
        app.notify = recorder(notes)
        screen = await app.open_form()
        await settle(pilot)
        # patch push_screen to detect whether the runner is launched
        app.push_screen = lambda *a, **k: pushed.append(a)

        screen.query_one("#name", Input).value = "bad name"
        screen._create()
        await settle(pilot)

        assert any(n.severity == "error" for n in notes)
        assert not pushed  # creation not started


async def test_valid_form_builds_launch_command():
    app = _CreateApp()
    captured: list = []
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await app.open_form()
        await settle(pilot)

        screen.query_one("#name", Input).value = "web-1"
        screen.query_one("#distro", Select).value = "images:debian/12"
        screen.query_one("#cpu", Input).value = "2"
        screen.query_one("#memory", Input).value = "2GiB"
        screen.query_one("#vm", Switch).value = False

        def fake_push(runner, callback=None):
            captured.append(runner)

        app.push_screen = fake_push
        screen._create()
        await settle(pilot)

        assert len(captured) == 1
        runner = captured[0]
        assert isinstance(runner, CommandRunnerScreen)
        assert runner._command[1:] == [
            "launch",
            "images:debian/12",
            "web-1",
            "-c",
            "limits.cpu=2",
            "-c",
            "limits.memory=2GiB",
        ]


async def test_custom_image_overrides_distro():
    app = _CreateApp()
    captured: list = []
    async with app.run_test(size=(100, 40)) as pilot:
        screen = await app.open_form()
        await settle(pilot)
        screen.query_one("#name", Input).value = "c1"
        screen.query_one("#custom", Input).value = "debian/13"
        app.push_screen = lambda runner, callback=None: captured.append(runner)
        screen._create()
        await settle(pilot)
        assert captured[0]._command[2] == "images:debian/13"


@pytest.mark.skipif(os.name != "posix", reason="embedded terminal needs a PTY")
async def test_command_runner_reports_success():
    class A(App):
        def compose(self) -> ComposeResult:
            return []

    app = A()
    results: list = []
    async with app.run_test(size=(100, 30)) as pilot:
        app.push_screen(
            CommandRunnerScreen(["bash", "-c", "exit 0"], "Test"),
            lambda ok: results.append(ok),
        )
        await settle(pilot, rounds=12)
        from textual.widgets import Static

        status = app.screen.query_one("#runner-status", Static)
        # render() returns the markup-rendered content
        assert "Done" in str(status.render())
        # F10 closes and reports success
        await pilot.press("f10")
        await settle(pilot)
        assert results == [True]
