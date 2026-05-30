from __future__ import annotations

from prompt_toolkit.formatted_text import to_plain_text

from blink.models import Remote, Repo, RepoStatus
from blink.store import Store
from blink.tui.widgets.detail import DetailPanel


def _make_repo(**overrides) -> Repo:
    defaults = dict(id=1, name="test-repo", alias="", path="/tmp/test-repo",
                    description="A test repo", last_synced="2025-01-01T00:00:00")
    defaults.update(overrides)
    repo = Repo(**defaults)
    repo.remotes = [Remote(id=1, repo_id=1, name="origin", url="git@github.com:user/test.git")]
    return repo


def _to_plain(formatted) -> str:
    return to_plain_text(formatted)


def _make_detail_panel(repo: Repo | None = None, focused: bool = True) -> DetailPanel:
    if repo is None:
        repo = _make_repo()
    store = Store(":memory:")
    store.init_db()
    return DetailPanel(
        repo=repo,
        store=store,
        editors={},
        on_back=lambda: None,
        on_alias_change=lambda alias: None,
        on_tags_change=lambda: None,
        is_focused=lambda f=focused: f,
    )


# ── rendering ───────────────────────────────────────────────────────────


def test_detail_panel_renders_fields():
    panel = _make_detail_panel()
    text = panel._formatted_text()
    t = _to_plain(text)
    assert "test-repo" in t
    assert "/tmp/test-repo" in t
    assert "A test repo" in t
    assert "https://github.com/user/test" in t


def test_detail_panel_renders_alias():
    repo = _make_repo(alias="my-alias")
    panel = _make_detail_panel(repo)
    t = _to_plain(panel._formatted_text())
    assert "my-alias" in t


def test_detail_panel_renders_no_alias():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "(none)" in t


def test_detail_panel_renders_tags():
    repo = _make_repo(tags=["python", "api"])
    panel = _make_detail_panel(repo)
    t = _to_plain(panel._formatted_text())
    assert "python" in t
    assert "api" in t


def test_detail_panel_renders_no_remotes():
    repo = _make_repo()
    repo.remotes = []
    panel = _make_detail_panel(repo)
    t = _to_plain(panel._formatted_text())
    assert "(none)" in t


def test_detail_panel_shows_pinned_row():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "Pinned" in t
    assert "No" in t


def test_detail_panel_shows_pinned_yes():
    repo = _make_repo(pinned=1)
    panel = _make_detail_panel(repo)
    t = _to_plain(panel._formatted_text())
    assert "Pinned" in t
    assert "Yes" in t


def test_detail_panel_line_constants():
    panel = _make_detail_panel()
    assert panel._max_cursor == 11
    assert panel._max_cursor == len(panel._navigable_actions()) + 3


def test_detail_panel_action_line_groups():
    assert len(DetailPanel._ACTION_GROUPS) == 3
    assert len(DetailPanel._ACTION_GROUPS[0]) == 3  # Terminal, IDE, Finder
    assert len(DetailPanel._ACTION_GROUPS[1]) == 3  # Git, Commit, Pull
    assert len(DetailPanel._ACTION_GROUPS[2]) == 2  # Task, Review


# ── status row ──────────────────────────────────────────────────────────


def test_detail_panel_shows_status_row():
    repo = _make_repo(status=RepoStatus(branch="main", dirty_count=2, ahead=1))
    panel = _make_detail_panel(repo)
    t = _to_plain(panel._formatted_text())
    assert "Status" in t
    assert "main" in t
    assert "+2" in t
    assert "↑1" in t


def test_detail_panel_shows_loading_status():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "Status" in t
    assert "···" in t


def test_detail_panel_status_before_pinned():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    status_pos = t.index("Status")
    pinned_pos = t.index("Pinned")
    assert status_pos < pinned_pos


# ── shortcut hints ──────────────────────────────────────────────────────


def test_detail_panel_renders_action_shortcuts():
    panel = _make_detail_panel(focused=False)
    t = _to_plain(panel._formatted_text())
    assert "Shift+1" in t
    assert "Shift+2" in t
    assert "Shift+3" in t
    assert "Shift+4" in t
    assert "Shift+5" in t
    assert "Shift+6" in t
    assert "Shift+7" in t
    assert "Shift+8" in t


def test_detail_panel_renders_action_rows():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "Open in Terminal" in t
    assert "Open with IDE" in t
    assert "Open in Finder" in t
    assert "Open in Browser" in t
    assert "Auto Commit Changes" in t
    assert "Pull Changes" in t
    assert "Add todo task" in t
    assert "AI Code Review" in t


# ── set_repo ────────────────────────────────────────────────────────────


def test_set_repo_updates_display():
    panel = _make_detail_panel()
    new_repo = _make_repo(name="new-repo", path="/new/path")
    panel.set_repo(new_repo)
    t = _to_plain(panel._formatted_text())
    assert "new-repo" in t
    assert "/new/path" in t


def test_set_repo_resets_cursor_on_different_repo():
    panel = _make_detail_panel()
    panel._cursor_index = 3
    panel.set_repo(_make_repo(path="/different/repo"))
    assert panel._cursor_index == 0


def test_set_repo_preserves_cursor_on_same_repo():
    panel = _make_detail_panel()
    panel._cursor_index = 3
    panel.set_repo(_make_repo())
    assert panel._cursor_index == 3


def test_set_repo_clears_edit_mode_on_different_repo():
    panel = _make_detail_panel()
    panel._start_alias_edit()
    assert panel.is_editing
    panel.set_repo(_make_repo(path="/different/repo"))
    assert not panel.is_editing
    assert panel.alias_buffer is None


def test_set_repo_preserves_edit_mode_on_same_repo():
    panel = _make_detail_panel()
    panel._start_alias_edit()
    assert panel.is_editing
    panel.set_repo(_make_repo())
    assert panel.is_editing


# ── on_action callback ──────────────────────────────────────────────────


def test_on_action_called_on_pin_toggle():
    actions = []
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo()
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid)
    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
        on_action=lambda: actions.append(True),
    )
    panel._cursor_index = len(panel._navigable_actions())
    panel.handle_enter()
    assert actions == [True]


def test_on_action_called_on_alias_edit():
    actions = []
    panel = _make_detail_panel()
    panel._on_action = lambda: actions.append(True)
    panel._cursor_index = len(panel._navigable_actions()) + 1
    panel.handle_enter()
    assert actions == [True]


def test_on_action_called_on_desc_edit():
    actions = []
    panel = _make_detail_panel()
    panel._on_action = lambda: actions.append(True)
    panel._cursor_index = len(panel._navigable_actions()) + 3
    panel.handle_enter()
    assert actions == [True]


# ── actions section ─────────────────────────────────────────────────────


def test_actions_section_renders_action_rows():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "IDE" in t
    assert "Terminal" in t
    assert "Commit" in t
    assert "Finder" in t
    assert "Git" in t
    assert "Task" in t


def test_actions_triggers_callbacks():
    callbacks = []
    panel = _make_detail_panel()
    panel._on_open_terminal = lambda: callbacks.append("terminal")
    panel._on_open_ide = lambda: callbacks.append("ide")
    panel._on_commit = lambda: callbacks.append("commit")
    panel._on_pull = lambda: callbacks.append("pull")
    panel._on_open_finder = lambda: callbacks.append("finder")
    panel._on_open_git = lambda: callbacks.append("git")
    panel._on_add_task = lambda: callbacks.append("task")

    panel._cursor_index = 0  # Terminal
    panel.handle_enter()
    panel._cursor_index = 1  # IDE
    panel.handle_enter()
    panel._cursor_index = 4  # Commit
    panel.handle_enter()
    panel._cursor_index = 5  # Pull
    panel.handle_enter()
    panel._cursor_index = 2  # Finder
    panel.handle_enter()
    panel._cursor_index = 3  # Git
    panel.handle_enter()
    panel._cursor_index = 6  # Task
    panel.handle_enter()

    assert callbacks == ["terminal", "ide", "commit", "pull", "finder", "git", "task"]


def test_actions_do_not_increment_view_count():
    actions = []
    panel = _make_detail_panel()
    panel._on_action = lambda: actions.append(True)

    for idx in range(6):
        panel._cursor_index = idx
        panel.handle_enter()

    assert actions == []


def test_selected_action_row_shows_indicator():
    panel = _make_detail_panel()
    panel._cursor_index = 1  # IDE
    t = _to_plain(panel._formatted_text())
    assert "▸" in t


def test_actions_section_between_metadata_and_markers():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    name_pos = t.index("Name")
    ide_pos = t.index("IDE")
    pinned_pos = t.index("Pinned")
    assert name_pos < ide_pos < pinned_pos


def test_no_static_shortcut_hints_section():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    lines = [l for l in t.split("\n") if l.strip()]
    last_line = lines[-1]
    assert "Shift+I:IDE" not in last_line
    assert "Shift+O:Finder" not in last_line


def test_marker_cursor_indices():
    panel = _make_detail_panel()
    n = len(panel._navigable_actions())
    assert n + 0 == 8  # Pinned
    assert n + 1 == 9  # Alias
    assert n + 2 == 10  # Tags
    assert n + 3 == 11  # Desc
