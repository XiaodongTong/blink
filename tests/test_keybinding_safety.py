"""Tests for the keybinding safety: Shift-gating, Ctrl+C exit, search isolation, focus management."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from prompt_toolkit.keys import Keys

from blink.models import Repo
from blink.config import Config
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
    app._ide_pending_path = None
    app._committing_paths = set()
    app._pulling_paths = set()
    app._review = ReviewOrchestrator(app)
    return app, store, rid


def _find_binding(kb, key):
    key_aliases = {"enter": "c-m"}
    lookup = key_aliases.get(key, key)
    for reg in kb.bindings:
        for k in reg.keys:
            val = k.value if hasattr(k, 'value') else str(k)
            if val == lookup or str(k) == key:
                if reg.filter is None or reg.filter():
                    return reg.handler
    return None


# --- Exit mechanism ---


def test_q_not_directly_bound(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for k in reg.keys:
            if str(k) == "q" and reg.filter is None:
                import pytest
                pytest.fail("q should not have an unfiltered binding")


def test_ctrl_c_first_press_sets_hint(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    event.app = MagicMock()
    assert not app._ctrl_c_quit_hint
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    assert app._ctrl_c_quit_hint is True


def test_ctrl_c_double_press_exits(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._ctrl_c_quit_hint = True
    app._last_ctrl_c = time.monotonic()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    event.app.exit.assert_called_once()


def test_ctrl_c_timeout_resets(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._ctrl_c_quit_hint = True
    app._last_ctrl_c = time.monotonic() - 3.0
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    event.app.exit.assert_not_called()
    assert app._ctrl_c_quit_hint is True


def test_ctrl_c_cancels_search_active(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._search_active = True
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    assert app._search_active is False
    assert app._search_filtering is False
    app._search_bar.clear.assert_called()


def test_ctrl_c_cancels_edit_mode(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    assert panel._edit_mode is None


def test_esc_does_not_exit(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "escape")
    handler(event)
    event.app.exit.assert_not_called()


def test_esc_clears_search_filtering(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._search_filtering = True
    app._search_bar.text = "test"
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "escape")
    handler(event)
    app._search_bar.clear.assert_called()
    assert app._search_filtering is False


# --- Shift gating ---


def test_j_k_not_directly_bound(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for k in reg.keys:
            if str(k) in ("j", "k") and reg.filter is None:
                import pytest
                pytest.fail(f"{k} should not have an unfiltered binding")


def test_shift_keys_present(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    bound_keys = []
    for reg in kb.bindings:
        for k in reg.keys:
            bound_keys.append(k.value if hasattr(k, 'value') else str(k))
    for expected in ("I", "O", "R", "G", "T", "s-up", "s-down"):
        assert expected in bound_keys, f"Missing Shift-gated key: {expected}"


def test_shift_keys_blocked_during_search(app_with_store):
    app, store, rid = app_with_store
    app._search_active = True
    kb = app._build_key_bindings()
    shift_keys = {"I", "O", "R", "G", "T", "s-up"}
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str in shift_keys:
                assert reg.filter is not None, f"Shift key '{key_str}' missing search filter"
                assert not reg.filter(), f"Shift key '{key_str}' should be blocked during search"


def test_down_confirms_search(app_with_store):
    app, store, rid = app_with_store
    app._search_active = True
    app._search_filtering = False
    kb = app._build_key_bindings()
    found = False
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str == "down" and reg.filter is not None and reg.filter():
                found = True
                break
    assert found, "down should have an active binding during search"


def test_detail_footer_removed(app_with_store):
    app, store, rid = app_with_store
    assert not hasattr(app, "_detail_footer_text")


def test_footer_text_no_q_quit(app_with_store):
    app, store, rid = app_with_store
    footer = app._footer_text()
    footer_str = str(footer)
    assert "quit" not in footer_str.lower() or "Ctrl+C" in footer_str


def test_footer_text_contains_shift_hints(app_with_store):
    app, store, rid = app_with_store
    footer = app._footer_text()
    footer_str = str(footer)
    assert "Shift" in footer_str


def test_footer_text_contains_tab_hint(app_with_store):
    app, store, rid = app_with_store
    footer = app._footer_text()
    footer_str = str(footer)
    assert "Tab" in footer_str


# --- Search isolation ---


def test_search_default_hidden(app_with_store):
    app, store, rid = app_with_store
    assert app._search_active is False
    assert app._search_filtering is False


def test_search_prefix_text_inactive():
    app, _, _ = _make_app()
    result = app._search_prefix_text()
    text = "".join(t[1] for t in result)
    assert "/" in text
    assert text.strip() == "/"


def test_search_prefix_text_active():
    app, _, _ = _make_app()
    app._search_active = True
    result = app._search_prefix_text()
    text = "".join(t[1] for t in result)
    assert "/" in text


def test_search_prefix_text_filtering():
    app, _, _ = _make_app()
    app._search_filtering = True
    app._search_bar.text = "myrepo"
    result = app._search_prefix_text()
    text = "".join(t[1] for t in result)
    assert "myrepo" in text


def test_enter_confirms_search(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._search_active = True
    app._search_bar.text = "test"
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "enter")
    handler(event)
    assert app._search_active is False
    assert app._search_filtering is True


def test_enter_search_with_empty_text(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    app._search_active = True
    app._search_bar.text = ""
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "enter")
    handler(event)
    assert app._search_active is False
    assert app._search_filtering is False


def test_status_text_shows_search_filtering(app_with_store):
    app, store, rid = app_with_store
    app._search_filtering = True
    app._search_bar.text = "myrepo"
    status = app._status_text()
    status_str = "".join(t[1] for t in status)
    assert "myrepo" in status_str
    assert "result" in status_str


def test_ctrl_c_quit_hint_footer():
    app, _, _ = _make_app()
    app._ctrl_c_quit_hint = True
    footer = app._footer_text()
    footer_str = "".join(t[1] for t in footer)
    assert "Ctrl+C" in footer_str
    assert "quit" in footer_str.lower()


def test_search_active_footer():
    app, _, _ = _make_app()
    app._search_active = True
    footer = app._footer_text()
    footer_str = "".join(t[1] for t in footer)
    assert "confirm" in footer_str.lower()
    assert "cancel" in footer_str.lower()


# --- Focus management ---


def test_focus_starts_on_list():
    app, _, _ = _make_app()
    assert app._focus_pane == "list"


def test_search_available_from_both_panes(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    # "/" binding should work when not in detail panel too (focus_pane == "list")
    app._focus_pane = "list"
    app._search_active = False
    found = False
    for reg in kb.bindings:
        for key in reg.keys:
            if str(key) == "/" and reg.filter is not None:
                try:
                    if reg.filter():
                        found = True
                except Exception:
                    pass
    assert found, "/ should be available in list pane"


# --- New key bindings (Shift+1–8) ---


def test_shift_number_keys_present(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    bound_keys = []
    for reg in kb.bindings:
        for k in reg.keys:
            bound_keys.append(k.value if hasattr(k, 'value') else str(k))
    for key in ("!", "@", "#", "$", "%", "^", "&", "*"):
        assert key in bound_keys, f"Missing Shift+number key binding for '{key}'"


def test_shift_number_keys_blocked_during_search(app_with_store):
    app, store, rid = app_with_store
    app._search_active = True
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str in ("!", "@", "#", "$", "%", "^", "&", "*"):
                assert reg.filter is not None, f"Shift key '{key_str}' missing search filter"
                assert not reg.filter(), f"Shift key '{key_str}' should be blocked during search"


def test_shift_number_keys_blocked_during_edit(app_with_store):
    app, store, rid = app_with_store
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel
    kb = app._build_key_bindings()
    # Check that the non-eager G/T bindings (Shift+action, not printable routing) are blocked
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str in ("!", "@", "#", "$", "%", "^", "&", "*") and not reg.eager():
                assert reg.filter is not None
                assert not reg.filter(), f"Shift key '{key_str}' should be blocked during edit"


# --- Footer hints ---


def test_footer_no_action_shortcut_hints(app_with_store):
    app, store, rid = app_with_store
    footer = app._footer_text()
    footer_str = "".join(t[1] for t in footer)
    assert "terminal" not in footer_str
    assert "git:" not in footer_str
    assert "task:" not in footer_str
    assert "review" not in footer_str
    assert "report" not in footer_str
    assert "pull" not in footer_str
