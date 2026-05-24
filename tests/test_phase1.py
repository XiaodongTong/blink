"""Phase 1 tests: icon system, color styles, detail panel slimming, shortcut passthrough."""
from __future__ import annotations

import json
from pathlib import Path

from unittest.mock import MagicMock

from blink.config import Config
from blink.models import Remote, Repo, RepoStatus
from blink.store import Store
from blink.tui.detail import DetailPanel
from blink.tui.icons import get_icon, BRANCH_NF, BRANCH_ASCII, PIN_NF, PIN_ASCII
from blink.tui.repo_list import RepoListControl
from prompt_toolkit.formatted_text import to_plain_text


# ── 1.5.1 & 1.5.2 Icon system ────────────────────────────────────────────


def test_icon_returns_ascii_when_nerd_fonts_false():
    assert get_icon(False, BRANCH_NF, BRANCH_ASCII) == BRANCH_ASCII
    assert get_icon(False, PIN_NF, PIN_ASCII) == PIN_ASCII


def test_icon_returns_nerd_when_nerd_fonts_true():
    assert get_icon(True, BRANCH_NF, BRANCH_ASCII) == BRANCH_NF
    assert get_icon(True, PIN_NF, PIN_ASCII) == PIN_NF


def test_icon_returns_ascii_when_nf_char_empty():
    assert get_icon(True, "", "fallback") == "fallback"


def test_repo_list_no_nerd_fonts_ascii():
    control = RepoListControl(nerd_fonts=False)
    repo = Repo(name="test", path="/tmp/test", pinned=1, status=RepoStatus(branch="main"))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = to_plain_text(content.get_line(0))
    assert PIN_ASCII in line0
    line1 = to_plain_text(content.get_line(1))
    assert "main" in line1


def test_repo_list_nerd_fonts_uses_nf_chars():
    control = RepoListControl(nerd_fonts=True)
    repo = Repo(name="test", path="/tmp/test", pinned=1, status=RepoStatus(branch="main"))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = to_plain_text(content.get_line(0))
    assert PIN_NF in line0
    line1 = to_plain_text(content.get_line(1))
    assert BRANCH_NF in line1


def test_config_nerd_fonts_default_false(tmp_path: Path):
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg.nerd_fonts is False


def test_config_nerd_fonts_set_true(tmp_path: Path):
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    cfg.set("nerd_fonts", True)
    assert cfg.nerd_fonts is True
    data = json.loads(cfg_path.read_text())
    assert data["nerd_fonts"] is True


# ── 1.5.3 _get_active_repo in detail view ────────────────────────────────


def _make_app_mock():
    from blink.config import Config
    from blink.scanner import Scanner
    from blink.tui.app import BlinkApp

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
    app._reviewing_paths = set()
    app._review_branch_loading = False
    app._review_selecting = False
    app._review_branches = []
    app._review_branch_cursor = 0
    app._last_report_paths = {}
    return app, store, rid


def test_get_active_repo_in_list_view():
    app, store, rid = _make_app_mock()
    repo = app._get_active_repo()
    assert repo is not None
    assert repo.id == rid


def test_get_active_repo_always_returns_list_selection():
    app, store, rid = _make_app_mock()
    # In two-column mode, _get_active_repo() always returns the list selection
    repo = app._get_active_repo()
    assert repo is not None
    assert repo.id == rid

    # Even with detail panel set, it returns the list selection
    panel = MagicMock()
    panel._repo = Repo(id=rid, name="detail-repo", path="/tmp/detail")
    panel.is_editing = False
    app._detail_panel = panel
    repo = app._get_active_repo()
    assert repo.id == rid  # Still from the repo control


# ── Detail panel slimming ────────────────────────────────────────────────


def _make_detail_panel(repo=None):
    if repo is None:
        repo = Repo(id=1, name="test-repo", alias="", path="/tmp/test-repo",
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


def test_detail_panel_has_action_and_marker_lines():
    assert DetailPanel.MAX_LINE == 10
    assert hasattr(DetailPanel, "LINE_PINNED")
    assert hasattr(DetailPanel, "LINE_ALIAS")
    assert hasattr(DetailPanel, "LINE_TAGS")
    assert hasattr(DetailPanel, "LINE_DESC")
    assert hasattr(DetailPanel, "LINE_IDE")
    assert hasattr(DetailPanel, "LINE_PATH")
    assert hasattr(DetailPanel, "LINE_COMMIT")
    assert hasattr(DetailPanel, "LINE_FINDER")
    assert hasattr(DetailPanel, "LINE_GIT")
    assert hasattr(DetailPanel, "LINE_TASK")
    assert hasattr(DetailPanel, "LINE_REVIEW")


def test_detail_panel_action_line_constants():
    assert DetailPanel.LINE_IDE == 0
    assert DetailPanel.LINE_PATH == 6
    assert DetailPanel.LINE_COMMIT == 2
    assert DetailPanel.LINE_FINDER == 4
    assert DetailPanel.LINE_GIT == 1
    assert DetailPanel.LINE_TASK == 3
    assert DetailPanel.LINE_REVIEW == 5


# ── Shortcut passthrough filter ──────────────────────────────────────────


def test_shift_keys_work_in_detail_view():
    app, store, rid = _make_app_mock()
    panel = MagicMock()
    panel._repo = Repo(id=rid, name="test", path="/tmp/test")
    panel.is_editing = False
    app._detail_panel = panel
    kb = app._build_key_bindings()
    # The dedicated shift-gated bindings use "not self._in_edit_mode()" filter.
    # Check that at least one binding per shift key is active in detail view.
    shift_keys = {"I", "O", "P", "C", "U", "G", "T"}
    active_keys = set()
    for reg in kb.bindings:
        for key in reg.keys:
            key_str = key.value if hasattr(key, 'value') else str(key)
            if key_str in shift_keys and reg.filter is not None and reg.filter():
                active_keys.add(key_str)
    for k in shift_keys:
        assert k in active_keys, f"Shift key '{k}' should have an active binding in detail view (non-editing)"


def test_shift_keys_blocked_during_edit_mode():
    app, store, rid = _make_app_mock()
    panel = MagicMock()
    panel.is_editing = True
    panel.edit_mode = "alias"
    app._detail_panel = panel
    assert app._in_edit_mode() is True
    # The shift key filter condition: not self._search_active and not self._in_edit_mode() and not self._ide_selecting
    filter_val = not app._search_active and not app._in_edit_mode() and not app._ide_selecting
    assert not filter_val, "Shift key filter should be False during edit mode"
