"""A minimal embedded terminal widget for Textual, backed by a PTY + pyte."""

from __future__ import annotations

import asyncio
import os
import signal
import struct

try:
    import fcntl
    import pty
    import termios

    _PTY_AVAILABLE = True
except ImportError:  # pragma: no cover - Windows
    _PTY_AVAILABLE = False

import pyte
from rich.segment import Segment
from rich.style import Style
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

_COLOR_ALIASES = {"brown": "yellow", "default": None}
_HEX = set("0123456789abcdefABCDEF")

_KEY_BYTES = {
    "enter": b"\r",
    "tab": b"\t",
    "backspace": b"\x7f",
    "escape": b"\x1b",
    "delete": b"\x1b[3~",
    "insert": b"\x1b[2~",
    "home": b"\x1b[H",
    "end": b"\x1b[F",
    "pageup": b"\x1b[5~",
    "pagedown": b"\x1b[6~",
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "right": b"\x1b[C",
    "left": b"\x1b[D",
    "f1": b"\x1bOP",
    "f2": b"\x1bOQ",
    "f3": b"\x1bOR",
    "f4": b"\x1bOS",
}


def _color(value: str) -> str | None:
    if value in _COLOR_ALIASES:
        return _COLOR_ALIASES[value]
    if len(value) == 6 and all(c in _HEX for c in value):
        return f"#{value}"
    return value


class TerminalWidget(Widget, can_focus=True):
    """Runs ``command`` in a PTY and renders its screen inside the TUI."""

    DEFAULT_CSS = """
    TerminalWidget {
        background: black;
    }
    """

    class Exited(Message):
        def __init__(self, widget: "TerminalWidget", returncode: int) -> None:
            super().__init__()
            self.widget = widget
            self.returncode = returncode

    def __init__(self, command: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._command = command
        self._fd: int | None = None
        self._pid: int | None = None
        self._screen: pyte.Screen | None = None
        self._stream: pyte.ByteStream | None = None
        self._started = False
        self._message: str | None = (
            None
            if _PTY_AVAILABLE
            else "Embedded terminal needs a POSIX platform (Linux/macOS)."
        )

    def on_resize(self) -> None:
        if not _PTY_AVAILABLE:
            return
        cols, rows = self.size.width, self.size.height
        if cols <= 0 or rows <= 0:
            return
        if not self._started:
            self._start(cols, rows)
        elif self._screen is not None:
            self._screen.resize(rows, cols)
            self._set_winsize(rows, cols)
            self.refresh()

    def _start(self, cols: int, rows: int) -> None:
        self._started = True
        pid, fd = pty.fork()
        if pid == 0:  # child: become the command
            os.environ["TERM"] = "xterm-256color"
            try:
                os.execvp(self._command[0], self._command)
            except OSError:
                os._exit(127)
        self._pid = pid
        self._fd = fd
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)
        self._set_winsize(rows, cols)
        asyncio.get_event_loop().add_reader(fd, self._on_readable)
        self.focus()

    def _set_winsize(self, rows: int, cols: int) -> None:
        if self._fd is None:
            return
        fcntl.ioctl(
            self._fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0)
        )

    def _on_readable(self) -> None:
        try:
            data = os.read(self._fd, 65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._cleanup_process()
            return
        self._stream.feed(data)
        self.refresh()

    def _cleanup_process(self) -> None:
        returncode = 0
        if self._fd is not None:
            try:
                asyncio.get_event_loop().remove_reader(self._fd)
            except (ValueError, OSError):
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        if self._pid is not None:
            try:
                _, status = os.waitpid(self._pid, os.WNOHANG)
                returncode = os.waitstatus_to_exitcode(status) if status else 0
            except OSError:
                pass
            self._pid = None
        self.post_message(self.Exited(self, returncode))

    def on_unmount(self) -> None:
        if self._fd is not None:
            try:
                asyncio.get_event_loop().remove_reader(self._fd)
            except (ValueError, OSError):
                pass
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGHUP)
            except OSError:
                pass
            self._pid = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        if self._screen is None:
            if self._message and y == self.size.height // 2:
                text = self._message[:width].center(width)
                return Strip([Segment(text, Style(color="yellow"))], width)
            return Strip.blank(width)
        if y >= self._screen.lines:
            return Strip.blank(width)
        row = self._screen.buffer[y]
        cursor = self._screen.cursor
        show_cursor = (
            self.has_focus and not cursor.hidden and cursor.y == y
        )
        segments = []
        for x in range(self._screen.columns):
            char = row[x]
            reverse = char.reverse ^ (show_cursor and cursor.x == x)
            style = Style(
                color=_color(char.fg),
                bgcolor=_color(char.bg),
                bold=char.bold,
                italic=char.italics,
                underline=char.underscore,
                strike=char.strikethrough,
                reverse=reverse,
            )
            segments.append(Segment(char.data or " ", style))
        return Strip(segments, self._screen.columns)

    def on_key(self, event) -> None:
        if self._fd is None:
            return
        event.stop()
        event.prevent_default()
        data = self._key_to_bytes(event)
        if data:
            try:
                os.write(self._fd, data)
            except OSError:
                pass

    def _key_to_bytes(self, event) -> bytes:
        key = event.key
        if key in _KEY_BYTES:
            return _KEY_BYTES[key]
        if key.startswith("ctrl+") and len(key) == 6 and key[5].isalpha():
            return bytes([ord(key[5].upper()) ^ 0x40])
        if event.character is not None and event.is_printable:
            return event.character.encode("utf-8")
        if event.character is not None:
            return event.character.encode("utf-8")
        return b""
