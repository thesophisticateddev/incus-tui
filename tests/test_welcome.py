"""Tests for the welcome banner."""

from textual.app import App, ComposeResult
from textual.widgets import Static

from incus_tui.components.welcome import _DESCRIPTION, _TITLE_ART, MarkdownHeader


def test_title_is_a_large_multirow_banner():
    # Terminals can't do 48pt, so "large" means a tall figlet banner.
    assert _TITLE_ART.count("\n") >= 3
    assert "Incus containers" in _DESCRIPTION


class _HeaderApp(App):
    def compose(self) -> ComposeResult:
        yield MarkdownHeader()


async def test_header_renders_left_aligned():
    app = _HeaderApp()
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        title = app.query_one("#app-title", Static)
        subtitle = app.query_one("#app-subtitle", Static)
        assert title.styles.text_align == "left"
        assert subtitle.styles.text_align == "left"
