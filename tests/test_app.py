"""Tests for BlinkApp._open_with_ide name→key conversion."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from blink.tui.actions import EditorInfo
from blink.tui.app import BlinkApp


def _make_app_with_editors(editor_name=None):
    app = BlinkApp.__new__(BlinkApp)
    app._config = MagicMock()
    app._config.editor = editor_name
    app._editors = {
        "v": EditorInfo(key="v", name="VSCode", command="/usr/local/bin/code"),
        "u": EditorInfo(key="u", name="Cursor", command="/usr/local/bin/cursor"),
        "n": EditorInfo(key="n", name="Neovim", command=None),
    }
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_scroll_offset = 0
    app._ide_pending_path = None
    app._app = MagicMock()
    return app


def test_open_with_ide_name_finds_key():
    app = _make_app_with_editors(editor_name="VSCode")
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_with_ide("/tmp/repo")
        mock_open.assert_called_once_with("/tmp/repo", "v", app._editors)
    assert not app._ide_selecting


def test_open_with_ide_name_finds_cursor():
    app = _make_app_with_editors(editor_name="Cursor")
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_with_ide("/tmp/repo")
        mock_open.assert_called_once_with("/tmp/repo", "u", app._editors)
    assert not app._ide_selecting


def test_open_with_ide_unknown_name_triggers_select():
    app = _make_app_with_editors(editor_name="NonExistent")
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_with_ide("/tmp/repo")
        mock_open.assert_not_called()
    app._config.set.assert_called_once_with("editor", None)  # pyrefly: ignore
    assert app._ide_selecting is True
    assert app._ide_pending_path == "/tmp/repo"


def test_open_with_ide_unavailable_editor_triggers_select():
    app = _make_app_with_editors(editor_name="Neovim")
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_with_ide("/tmp/repo")
        mock_open.assert_not_called()
    app._config.set.assert_called_once_with("editor", None)  # pyrefly: ignore
    assert app._ide_selecting is True


def test_open_with_ide_none_editor_triggers_select():
    app = _make_app_with_editors(editor_name=None)
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_with_ide("/tmp/repo")
        mock_open.assert_not_called()
    app._config.set.assert_not_called()  # pyrefly: ignore
    assert app._ide_selecting is True
    assert app._ide_pending_path == "/tmp/repo"
