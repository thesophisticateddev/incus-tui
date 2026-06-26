"""Tests for the embedded terminal widget."""

import asyncio
import os
import time
from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult

import incus_tui.components.terminal as tmod
from incus_tui.components.terminal import TerminalWidget


def _event(key, character=None, is_printable=False):
    return SimpleNamespace(key=key, character=character, is_printable=is_printable)


def test_key_to_bytes():
    w = TerminalWidget(["x"])
    assert w._key_to_bytes(_event("enter")) == b"\r"
    assert w._key_to_bytes(_event("tab")) == b"\t"
    assert w._key_to_bytes(_event("backspace")) == b"\x7f"
    assert w._key_to_bytes(_event("up")) == b"\x1b[A"
    assert w._key_to_bytes(_event("ctrl+c")) == b"\x03"
    assert w._key_to_bytes(_event("ctrl+d")) == b"\x04"
    assert w._key_to_bytes(_event("a", "a", True)) == b"a"


async def test_terminal_degrades_without_pty(monkeypatch):
    monkeypatch.setattr(tmod, "_PTY_AVAILABLE", False)

    class A(App):
        def compose(self) -> ComposeResult:
            yield TerminalWidget(["whatever"])

    app = A()
    async with app.run_test(size=(50, 10)) as pilot:
        await pilot.pause()
        w = app.query_one(TerminalWidget)
        line = w.render_line(5)
        assert "POSIX" in line.text
        assert w._started is False
        assert w._fd is None


@pytest.mark.skipif(os.name != "posix", reason="PTY is POSIX-only")
async def test_terminal_runs_command_and_renders_output():
    class A(App):
        def compose(self) -> ComposeResult:
            yield TerminalWidget(["bash", "-c", "echo terminaltest; sleep 5"])

    app = A()
    async with app.run_test(size=(80, 24)) as pilot:
        w = app.query_one(TerminalWidget)
        deadline = time.time() + 5
        found = False
        while time.time() < deadline:
            await pilot.pause()
            await asyncio.sleep(0.1)
            screen = w._screen
            if screen is not None:
                text = "\n".join(
                    "".join(screen.buffer[y][x].data for x in range(screen.columns))
                    for y in range(screen.lines)
                )
                if "terminaltest" in text:
                    found = True
                    break
        assert found, "expected command output to render in the terminal"
