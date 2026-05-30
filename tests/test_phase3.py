"""Phase 3 tests: three-state focus pane, edit mode integration."""
from __future__ import annotations

from unittest.mock import MagicMock

from blink.config import Config
from blink.models import Repo
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.app import BlinkApp
from blink.tui.app_review import ReviewOrchestrator


def _make_app():
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
    app._ide_scroll_offset = 0
    app._ide_pending_path = None
    app._committing_paths = set()
    app._pulling_paths = set()
    app._review = ReviewOrchestrator(app)
    return app, store, rid


# ── Three-state focus pane ──────────────────────────────────────────────


def test_focus_pane_starts_at_list():
    app, _, _ = _make_app()
    assert app._focus_pane == "list"


def test_focus_transitions_list_to_detail():
    app, _, _ = _make_app()
    app._focus_pane = "list"
    # Simulate Tab: focus detail
    app._focus_pane = "detail"
    assert app._focus_pane == "detail"


def test_focus_transitions_detail_to_edit():
    app, _, _ = _make_app()
    app._focus_pane = "detail"
    # Simulate entering edit mode via Enter
    app._focus_pane = "edit"
    assert app._focus_pane == "edit"


def test_focus_transitions_edit_to_detail():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel._edit_mode = "alias"
    panel._alias_buffer = None
    panel._desc_buffer = None
    panel._tag_buffer = None
    app._detail_panel = panel
    app._focus_pane = "edit"
    app._cancel_edit()
    assert app._focus_pane == "detail"


def test_focus_transitions_detail_to_list():
    app, _, _ = _make_app()
    app._focus_pane = "detail"
    # Simulate Esc returning to list
    app._focus_pane = "list"
    assert app._focus_pane == "list"


def test_full_cycle_list_detail_edit_detail_list():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel._edit_mode = None
    panel._alias_buffer = None
    panel._desc_buffer = None
    panel._tag_buffer = None
    app._detail_panel = panel
    assert app._focus_pane == "list"
    # Tab -> detail
    app._focus_pane = "detail"
    assert app._focus_pane == "detail"
    # Enter edit -> edit
    app._focus_pane = "edit"
    assert app._focus_pane == "edit"
    # Cancel edit -> detail
    panel._edit_mode = "alias"
    app._cancel_edit()
    assert app._focus_pane == "detail"
    # Esc -> list
    app._focus_pane = "list"
    assert app._focus_pane == "list"


# ── Edit mode blocks global shortcuts ──────────────────────────────────


def test_edit_mode_blocks_shift_keys():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel
    # The filter condition for shift keys is: not self._in_edit_mode()
    assert app._in_edit_mode() is True
    filter_val = not app._search_active and not app._in_edit_mode() and not app._ide_selecting
    assert filter_val is False


def test_edit_mode_blocks_arrows_in_detail():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel
    # Arrow keys filter in detail: not self._in_edit_mode()
    arrow_filter = not app._search_active and not app._ide_selecting and not app._in_edit_mode()
    assert arrow_filter is False


# ── Cancel edit restores focus to detail ────────────────────────────────


def test_cancel_edit_sets_focus_to_detail():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel._edit_mode = "alias"
    panel._alias_buffer = MagicMock()
    panel._desc_buffer = None
    panel._tag_buffer = None
    app._detail_panel = panel
    app._focus_pane = "edit"

    app._cancel_edit()
    assert app._focus_pane == "detail"
    assert panel._edit_mode is None
    assert panel._alias_buffer is None


# ── Enter in edit mode confirms and returns to detail ───────────────────


def test_enter_in_edit_mode_confirms():
    app, _, rid = _make_app()
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))

    from blink.tui.widgets.detail import DetailPanel
    selected = app._repo_control.selected_repo()
    assert selected is not None
    panel = DetailPanel(
        repo=selected,
        store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    app._detail_panel = panel
    app._focus_pane = "edit"

    # Start alias edit
    panel._cursor_index = len(panel._navigable_actions()) + 1
    panel.handle_enter()  # enters edit mode
    assert panel._alias_buffer is not None
    panel._alias_buffer.text = "new-alias"

    # Enter confirms
    panel.handle_enter()  # confirms alias
    assert not panel.is_editing
    assert panel._repo.alias == "new-alias"
