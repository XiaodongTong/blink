"""Tests for narrow terminal view switching: _view_mode state, key bindings, resize sync."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from blink.models import Repo
from blink.config import Config
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.app import BlinkApp
from blink.tui.app_review import ReviewOrchestrator


def _make_app(narrow: bool = False):
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))

    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._config = MagicMock(spec=Config)
    app._config.editor = None
    app._config.nerd_fonts = False
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._repo_control.repos = [Repo(id=rid, name="test-repo", path="/tmp/test")]
    app._repo_control.selected_repo = MagicMock(return_value=app._repo_control.repos[0])
    app._search_bar = MagicMock()
    app._search_bar.text = ""
    app._search_bar.clear = MagicMock()
    app._search_bar.focus = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = MagicMock()
    app._detail_panel.set_repo = MagicMock()
    app._detail_panel.is_editing = False
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
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_scroll_offset = 0
    app._ide_pending_path = None
    app._committing_paths = set()
    app._pulling_paths = set()
    app._review = ReviewOrchestrator(app)
    app._config_panel = None
    app._config_selecting = False
    app._pre_config_focus = "list"

    size_mock = MagicMock()
    size_mock.columns = 90 if narrow else 120
    app._app.output.get_size.return_value = size_mock

    return app, store, rid


def _find_binding(kb, key):
    for reg in kb.bindings:
        for k in reg.keys:
            val = k.value if hasattr(k, 'value') else str(k)
            if val == key or str(k) == key:
                if reg.filter is None or reg.filter():
                    return reg.handler
    return None


# 5.1 — initial _view_mode is "list"


def test_view_mode_initial_value():
    app, _, _ = _make_app()
    assert app._view_mode == "list"


# 5.2 — → in narrow mode sets _view_mode="detail" and focuses detail


def test_right_narrow_sets_view_mode_detail():
    app, _, _ = _make_app(narrow=True)
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "right")
    assert handler is not None
    handler(event)
    assert app._view_mode == "detail"
    assert app._focus_pane == "detail"


# 5.3 — ← in narrow mode sets _view_mode="list" and focuses list


def test_left_narrow_sets_view_mode_list():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "detail"
    app._view_mode = "detail"
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "left")
    assert handler is not None
    handler(event)
    assert app._view_mode == "list"
    assert app._focus_pane == "list"


# 5.4 — Escape in narrow mode detail view switches back to list


def test_escape_narrow_detail_switches_to_list():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "detail"
    app._view_mode = "detail"
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "escape")
    assert handler is not None
    handler(event)
    assert app._view_mode == "list"
    assert app._focus_pane == "list"


# 5.5 — / search in narrow mode detail view switches back to list view


def test_search_narrow_detail_switches_to_list():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "detail"
    app._view_mode = "detail"
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "/")
    assert handler is not None
    handler(event)
    assert app._view_mode == "list"


# 5.6 — Wide mode →/← only switch focus, do not change _view_mode


def test_wide_mode_arrow_keeps_view_mode():
    app, _, _ = _make_app(narrow=False)
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()

    handler = _find_binding(kb, "right")
    assert handler is not None
    handler(event)
    assert app._focus_pane == "detail"
    assert app._view_mode == "list"

    handler = _find_binding(kb, "left")
    assert handler is not None
    handler(event)
    assert app._focus_pane == "list"
    assert app._view_mode == "list"


# 5.7 — _sync_view_mode_for_width: narrow + focus_pane="detail" → _view_mode="detail"


def test_sync_view_mode_narrow_detail():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "detail"
    app._view_mode = "list"
    app._sync_view_mode_for_width()
    assert app._view_mode == "detail"


def test_sync_view_mode_narrow_list():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "list"
    app._view_mode = "detail"
    app._sync_view_mode_for_width()
    assert app._view_mode == "list"


def test_sync_view_mode_wide_noop():
    app, _, _ = _make_app(narrow=False)
    app._focus_pane = "detail"
    app._view_mode = "list"
    app._sync_view_mode_for_width()
    assert app._view_mode == "list"


# 5.8 — narrow mode, _detail_panel is None → → does not trigger view switch


def test_narrow_no_detail_panel_right_noop():
    app, _, _ = _make_app(narrow=True)
    app._detail_panel = None
    event = MagicMock()
    event.app = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "right")
    assert handler is not None
    handler(event)
    assert app._view_mode == "list"
    assert app._focus_pane == "list"


# 5.9 — narrow mode: enter config → _view_mode="detail"


def test_enter_config_narrow_sets_view_mode():
    app, _, _ = _make_app(narrow=True)
    app._enter_config()
    assert app._view_mode == "detail"
    assert app._focus_pane == "config"


# 5.10 — narrow mode: exit config → _view_mode matches restored focus


def test_exit_config_narrow_restores_view_mode():
    app, _, _ = _make_app(narrow=True)
    app._pre_config_focus = "list"
    app._focus_pane = "config"
    app._view_mode = "detail"
    app._exit_config()
    assert app._view_mode == "list"
    assert app._focus_pane == "list"


def test_exit_config_narrow_detail_focus():
    app, _, _ = _make_app(narrow=True)
    app._pre_config_focus = "detail"
    app._focus_pane = "config"
    app._view_mode = "detail"
    app._exit_config()
    assert app._view_mode == "detail"
    assert app._focus_pane == "detail"


# 5.11 — resize: wide→narrow with detail focus → _view_mode="detail"


def test_resize_wide_to_narrow_detail_focus():
    app, _, _ = _make_app(narrow=False)
    app._focus_pane = "detail"
    app._view_mode = "list"
    size_mock = MagicMock()
    size_mock.columns = 90
    app._app.output.get_size.return_value = size_mock
    app._sync_view_mode_for_width()
    assert app._view_mode == "detail"


def test_resize_narrow_to_wide():
    app, _, _ = _make_app(narrow=True)
    app._focus_pane = "detail"
    app._view_mode = "detail"
    size_mock = MagicMock()
    size_mock.columns = 120
    app._app.output.get_size.return_value = size_mock
    app._sync_view_mode_for_width()
    assert app._view_mode == "detail"


# 5.12 — Tab key has no binding


def test_no_tab_binding():
    app, _, _ = _make_app()
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for k in reg.keys:
            val = k.value if hasattr(k, 'value') else str(k)
            if val == "tab" or str(k) == "tab":
                if reg.filter is None or reg.filter():
                    raise AssertionError("Tab should not have any active binding")
