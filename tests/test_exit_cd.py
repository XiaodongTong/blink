"""Tests for Enter-to-exit-and-cd feature."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from blink.models import Repo
from blink.config import Config
from blink.store import Store
from blink.tui.app import BlinkApp


def _make_app_with_repo(tmp_path: Path) -> BlinkApp:
    from blink.scanner import Scanner
    store = Store(":memory:")
    store.init_db()
    repo = Repo(name="test-repo", path=str(tmp_path))
    store.upsert_repo(repo)

    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = MagicMock(spec=Scanner)
    app._config = MagicMock(spec=Config)
    app._config.editor = None
    app._config.nerd_fonts = False
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._repo_control.selected_repo.return_value = repo
    app._search_bar = MagicMock()
    app._search_bar.text = ""
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._repo_list_window = MagicMock()
    app._detail_window = MagicMock()
    app._edit_status_window = MagicMock()
    app._focus_pane = "list"
    app._view_mode = "list"
    app._search_active = False
    app._search_filtering = False
    app._footer_highlight_until = 0.0
    app._last_ctrl_c = 0.0
    app._ctrl_c_quit_hint = False
    app._app = MagicMock()
    size_mock = MagicMock()
    size_mock.columns = 120
    app._app.output.get_size.return_value = size_mock
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_scroll_offset = 0
    app._ide_pending_path = None
    app._committing_paths = set()
    app._pulling_paths = set()
    from blink.tui.app_review import ReviewOrchestrator
    app._review = ReviewOrchestrator(app)
    app._config_panel = None
    app._config_selecting = False
    app._pre_config_focus = "list"
    app._exit_cd_path = None
    return app


def test_exit_and_cd_sets_path_and_exits():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app_with_repo(Path(tmp))
        repo = app._repo_control.selected_repo()
        assert repo is not None
        app._exit_and_cd(repo)
        assert app._exit_cd_path == str(Path(tmp))
        app._app.exit.assert_called_once()  # pyrefly: ignore


def test_exit_cd_path_initially_none():
    with tempfile.TemporaryDirectory() as tmp:
        app = _make_app_with_repo(Path(tmp))
        assert app._exit_cd_path is None


def test_inject_cd_calls_ioctl():
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp))
        with patch("blink.cli.fcntl") as mock_fcntl, \
             patch("blink.cli.termios") as mock_termios:
            from blink.cli import _inject_cd
            mock_termios.TIOCSTI = 0x80017472
            _inject_cd(path)
            assert mock_fcntl.ioctl.call_count == len(f"cd {path}\n")


def test_inject_cd_falls_back_to_print():
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp))
        with patch("blink.cli.fcntl.ioctl", side_effect=OSError), \
             patch("builtins.print") as mock_print:
            from blink.cli import _inject_cd
            _inject_cd(path)
            mock_print.assert_called_once()
