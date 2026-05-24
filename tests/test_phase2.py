"""Phase 2 tests: VSplit two-column layout, focus management, set_repo, Enter behavior."""
from __future__ import annotations

from unittest.mock import MagicMock

from blink.config import Config
from blink.models import Remote, Repo, RepoStatus
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.app import BlinkApp
from blink.tui.detail import DetailPanel


def _make_app():
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))

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
    app._ide_pending_repo = None
    app._committing_paths = set()
    app._pulling_paths = set()
    return app, store, rid


# ── set_repo tests ──────────────────────────────────────────────────────


def test_set_repo_updates_content():
    panel = _make_panel()
    new_repo = Repo(id=2, name="other", path="/other")
    panel.set_repo(new_repo)
    assert panel._repo is new_repo


def test_set_repo_resets_cursor():
    panel = _make_panel()
    panel._cursor_index = 3
    panel.set_repo(Repo(id=2, name="x", path="/x"))
    assert panel._cursor_index == 0


def test_set_repo_clears_edit_state():
    panel = _make_panel()
    panel._start_alias_edit()
    panel.set_repo(Repo(id=2, name="x", path="/x"))
    assert not panel.is_editing
    assert panel.alias_buffer is None


# ── focus pane state ────────────────────────────────────────────────────


def test_focus_starts_on_list():
    app, _, _ = _make_app()
    assert app._focus_pane == "list"


def test_tab_switches_to_detail():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel.is_editing = False
    panel.edit_mode = None
    app._detail_panel = panel
    app._focus_pane = "list"
    kb = app._build_key_bindings()

    # Tab is registered as c-i in prompt_toolkit
    event = MagicMock()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "c-i" and reg.filter is not None and reg.filter():
                reg.handler(event)
                assert app._focus_pane == "detail"
                return
    assert False, "Tab (c-i) binding not found or filter not passing"


def test_escape_returns_to_list_from_detail():
    app, _, _ = _make_app()
    app._detail_panel = None
    app._search_active = False
    app._search_filtering = False
    app._ide_selecting = False
    app._focus_pane = "detail"

    kb = app._build_key_bindings()
    event = MagicMock()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "escape":
                fval = reg.filter() if reg.filter is not None else True
                if fval and not (reg.eager() if callable(reg.eager) else reg.eager):
                    reg.handler(event)
                    assert app._focus_pane == "list"
                    return
    assert False, "Escape handler not found"


def test_left_arrow_returns_to_list_from_detail():
    app, _, _ = _make_app()
    app._detail_panel = None
    app._focus_pane = "detail"
    app._ide_selecting = False

    kb = app._build_key_bindings()
    event = MagicMock()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "left":
                fval = reg.filter() if reg.filter is not None else True
                eager = reg.eager() if callable(reg.eager) else reg.eager
                if fval and not eager:
                    reg.handler(event)
                    assert app._focus_pane == "list"
                    return
    assert False, "Left arrow handler not found"


# ── Enter key behavior ──────────────────────────────────────────────────


def test_enter_in_list_opens_ide():
    """Enter in list pane should trigger IDE open (same as Shift+I)."""
    app, _, rid = _make_app()
    app._focus_pane = "list"
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.selected_repo = MagicMock(return_value=repo)
    app._config.preferred_ide = "v"
    # Set a real command to avoid FileNotFoundError
    app._editors = {"v": MagicMock(available=True, command="echo")}

    kb = app._build_key_bindings()
    event = MagicMock()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "c-m":  # enter
                fval = reg.filter() if reg.filter is not None else True
                if fval:
                    reg.handler(event)
                    return
    assert False, "Enter handler not found"


def test_enter_in_detail_handles_panel_action():
    app, _, rid = _make_app()
    panel = MagicMock()
    panel.is_editing = False
    app._detail_panel = panel
    app._focus_pane = "detail"

    kb = app._build_key_bindings()
    event = MagicMock()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "c-m":
                if reg.filter is None or reg.filter():
                    reg.handler(event)
                    panel.handle_enter.assert_called()
                    return


# ── Ctrl+C priority chain ───────────────────────────────────────────────


def test_ctrl_c_cancels_edit_first():
    app, _, _ = _make_app()
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel

    event = MagicMock()
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "c-c" and (reg.filter is None or reg.filter()):
                reg.handler(event)
                break
    assert panel._edit_mode is None


# ── Detail panel sections ───────────────────────────────────────────────


def _make_panel(repo=None):
    if repo is None:
        repo = Repo(id=1, name="test-repo", path="/tmp/test-repo",
                     description="A test repo", last_synced="2025-01-01T00:00:00")
        repo.remotes = [Remote(id=1, repo_id=1, name="origin", url="git@github.com:user/test.git")]
    store = Store(":memory:")
    store.init_db()
    return DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )


def test_detail_metadata_displayed():
    panel = _make_panel()
    from prompt_toolkit.formatted_text import to_plain_text
    t = to_plain_text(panel._formatted_text())
    assert "Name" in t
    assert "test-repo" in t
    assert "Path" in t
    assert "/tmp/test-repo" in t
    assert "Git" in t
    assert "Status" in t


def test_detail_local_markers_have_cursor():
    panel = _make_panel()
    panel._cursor_index = DetailPanel.LINE_PINNED
    assert panel._cursor_index == 6
    panel._cursor_index = DetailPanel.LINE_DESC
    assert panel._cursor_index == 9


def test_detail_shortcuts_displayed():
    panel = _make_panel()
    from prompt_toolkit.formatted_text import to_plain_text
    t = to_plain_text(panel._formatted_text())
    assert "Shift+I" in t
    assert "Shift+G" in t
    assert "Shift+T" in t


# ── Sync detail panel ──────────────────────────────────────────────────


def test_sync_detail_panel_creates_panel():
    app, store, rid = _make_app()
    assert app._detail_panel is None
    app._sync_detail_panel()
    assert app._detail_panel is not None
    assert app._detail_panel._repo.id == rid


def test_sync_detail_panel_updates_existing():
    app, store, rid = _make_app()
    app._init_detail_panel()
    old_panel = app._detail_panel
    new_repo = Repo(id=rid, name="updated", path="/updated")
    app._repo_control.selected_repo = MagicMock(return_value=new_repo)
    app._sync_detail_panel()
    assert app._detail_panel is old_panel  # Same panel object
    assert app._detail_panel._repo is new_repo  # Repo updated


# ── view_count increment ────────────────────────────────────────────────


def test_view_count_incremented_on_action():
    app, store, rid = _make_app()
    app._init_detail_panel()
    app._detail_panel._cursor_index = DetailPanel.LINE_ALIAS
    initial_count = app._repo_control.selected_repo().view_count
    app._detail_panel.handle_enter()
    # handle_enter calls _on_action which calls _increment_view_count
    assert app._repo_control.selected_repo().view_count == initial_count + 1
