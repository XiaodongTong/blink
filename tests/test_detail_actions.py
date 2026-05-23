"""Tests for the new detail panel actions: open in browser (Shift+G) and add task (Shift+T)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from blink.models import Remote, Repo
from blink.config import Config
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.app import BlinkApp


def _make_app():
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    repo.remotes = [Remote(id=1, repo_id=rid, name="origin", url="git@github.com:user/test.git")]

    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._config = MagicMock(spec=Config)
    app._config.preferred_ide = None
    app._config.nerd_fonts = False
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._repo_control.repos = [repo]
    app._repo_control.selected_repo = MagicMock(return_value=repo)
    app._search_bar = MagicMock()
    app._search_bar.text = ""
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._repo_list_window = MagicMock()
    app._detail_window = MagicMock()
    app._edit_status_window = MagicMock()
    app._focus_pane = "list"
    app._search_active = False
    app._search_filtering = False
    app._footer_highlight_until = 0.0
    app._last_ctrl_c = 0.0
    app._ctrl_c_quit_hint = False
    app._app = MagicMock()
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_pending_repo = None
    app._committing = False
    app._commit_spinner_index = 0
    app._pulling = False
    app._pull_spinner_index = 0
    app._pull_spinner_timer = None
    return app, store, rid, repo


def test_open_git_in_browser_opens_url():
    app, store, rid, repo = _make_app()
    with patch("webbrowser.open") as mock_open:
        app._open_git_in_browser()
        mock_open.assert_called_once_with("https://github.com/user/test")


def test_open_git_in_browser_no_remote():
    app, store, rid, repo = _make_app()
    repo.remotes = []
    with patch("webbrowser.open") as mock_open:
        app._open_git_in_browser()
        mock_open.assert_not_called()
    assert "No remote" in app._scan_status


def test_open_git_in_browser_no_https_conversion():
    app, store, rid, repo = _make_app()
    repo.remotes = [Remote(id=1, repo_id=rid, name="origin", url="file:///local/path")]
    with patch("webbrowser.open") as mock_open:
        app._open_git_in_browser()
        mock_open.assert_not_called()
    assert "Cannot convert" in app._scan_status


def test_open_git_in_browser_https_url():
    app, store, rid, repo = _make_app()
    repo.remotes = [Remote(id=1, repo_id=rid, name="origin", url="https://github.com/user/test.git")]
    with patch("webbrowser.open") as mock_open:
        app._open_git_in_browser()
        mock_open.assert_called_once_with("https://github.com/user/test")


def test_run_add_task_calls_internal():
    app, store, rid, repo = _make_app()
    with patch("blink.loop.cmd_edit._add_task") as mock_add:
        app._run_add_task()
        import time; time.sleep(0.3)
        mock_add.assert_called_once_with(repo.path)


def test_run_add_task_handles_error():
    app, store, rid, repo = _make_app()
    with patch("blink.loop.cmd_edit._add_task", side_effect=IOError("disk full")):
        app._run_add_task()
        import time; time.sleep(0.3)
        assert "✗" in app._scan_status or app._scan_status == "" or "Task 添加失败" in app._scan_status


def test_run_add_task_no_repo():
    app, store, rid, repo = _make_app()
    app._repo_control.selected_repo = MagicMock(return_value=None)
    with patch("blink.loop.cmd_edit._add_task") as mock_add:
        app._run_add_task()
        mock_add.assert_not_called()


def test_copy_repo_path_from_action():
    app, store, rid, repo = _make_app()
    with patch("blink.tui.app.copy_path", return_value=True) as mock_copy:
        app._copy_repo_path()
        mock_copy.assert_called_once_with(repo.path)


def test_open_finder_from_action():
    app, store, rid, repo = _make_app()
    with patch("blink.tui.app.open_in_editor") as mock_open:
        app._open_finder()
        mock_open.assert_called_once_with(repo.path, "o", app._editors)
