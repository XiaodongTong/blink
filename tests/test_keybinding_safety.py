"""Tests for the keybinding safety refactoring: Shift-gating, Ctrl+C exit, search isolation."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from prompt_toolkit.keys import Keys

from blink.models import Repo
from blink.config import Config
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
    app._list_layout = MagicMock()
    app._mode = "list"
    app._search_active = False
    app._search_filtering = False
    app._footer_highlight_until = 0.0
    app._editing_alias = False
    app._editing_tag = False
    app._editing_repo = None
    app._last_ctrl_c = 0.0
    app._ctrl_c_quit_hint = False
    app._app = MagicMock()
    app._ide_selecting = False
    app._ide_select_cursor = 0
    app._ide_pending_repo = None
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


# --- Phase 1: Exit mechanism ---


def test_q_not_directly_bound(app_with_store):
    """q should not have a dedicated handler (only printable routing with edit-mode filter)."""
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for k in reg.keys:
            if str(k) == "q" and reg.filter is None:
                pytest.fail("q should not have an unfiltered binding")
    # q may exist in printable routing (eager + edit-mode filter) — that's acceptable


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
    app._last_ctrl_c = time.monotonic() - 3.0  # 3 seconds ago
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


def test_ctrl_c_detail_view_returns_to_list(app_with_store):
    app, store, rid = app_with_store
    event = MagicMock()
    panel = MagicMock()
    panel.is_editing = False
    panel.edit_mode = None
    app._detail_panel = panel
    kb = app._build_key_bindings()
    handler = _find_binding(kb, "c-c")
    handler(event)
    assert app._detail_panel is None


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


# --- Phase 2: Shift gating ---


def test_j_k_not_directly_bound(app_with_store):
    """j/k should not have dedicated handlers (only printable routing with edit-mode filter)."""
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for k in reg.keys:
            if str(k) in ("j", "k") and reg.filter is None:
                import pytest
                pytest.fail(f"{k} should not have an unfiltered binding")


def test_detail_bare_keys_filtered(app_with_store):
    """v/u/a/o/y bare keys should have filter requiring detail_panel."""
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    for reg in kb.bindings:
        for key in reg.keys:
            if str(key) in ("v", "u", "a", "o", "y"):
                assert reg.filter is not None, f"Bare key '{key}' should have a filter"


def test_shift_keys_present(app_with_store):
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    bound_keys = []
    for reg in kb.bindings:
        for k in reg.keys:
            bound_keys.append(k.value if hasattr(k, 'value') else str(k))
    for expected in ("I", "O", "R", "s-up", "s-down"):
        assert expected in bound_keys, f"Missing Shift-gated key: {expected}"


def test_shift_keys_blocked_during_search(app_with_store):
    """Shift-gated keys must be blocked during search active state (AC-2)."""
    app, store, rid = app_with_store
    app._search_active = True
    kb = app._build_key_bindings()
    shift_keys = {"I", "O", "R", "s-up"}
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str in shift_keys:
                assert reg.filter is not None, f"Shift key '{key_str}' missing search filter"
                assert not reg.filter(), f"Shift key '{key_str}' should be blocked during search"


def test_down_confirms_search(app_with_store):
    """Down arrow confirms search (same as Enter) when search is active."""
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


def test_e_t_routed_via_printable_characters(app_with_store):
    """e and t are now routed via the printable character loop (not dedicated handlers)."""
    app, store, rid = app_with_store
    kb = app._build_key_bindings()
    # In the new design, e and t are part of the printable-char loop (range 33-127).
    # They should NOT have dedicated kb.add() calls, only the loop-level ones.
    # We verify this by checking that e/t only appear as 'char' bindings, not as
    # top-level string key bindings (which would indicate a dedicated handler).
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = str(key)
            if key_str in ("e", "t"):
                # These should only be caught by the printable-char loop,
                # which uses the handler that routes via _route_printable
                # Verify it's not a dedicated enter/backspace handler
                import inspect
                src = inspect.getsource(reg.handler)
                assert "_route_printable" in src or "route_printable" in src, \
                    f"Key '{key_str}' should be routed via printable-char handler"


def test_detail_footer_removed(app_with_store):
    """Detail view should not have a footer window."""
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


def test_detail_view_has_no_footer(app_with_store):
    """Detail view layout should not include a footer window."""
    app, store, rid = app_with_store
    # Build the detail layout and verify it has no footer window
    app._detail_panel = MagicMock()
    layout = app._build_detail_layout()
    # The detail layout is HSplit([Window (detail), Window (border), Window (status)])
    # i.e. exactly 3 windows, no footer
    root = layout.container
    children = root.children
    assert len(children) == 3


# --- Phase 3: Search isolation ---


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
    # Active state hides the prefix; the bordered input is shown instead
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
