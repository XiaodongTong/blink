from __future__ import annotations

from prompt_toolkit.formatted_text import to_plain_text

from blink.models import Remote, Repo, RepoStatus
from blink.store import Store
from blink.tui.detail import DetailPanel


def _make_repo(**overrides) -> Repo:
    defaults = dict(id=1, name="test-repo", alias="", path="/tmp/test-repo",
                    description="A test repo", last_synced="2025-01-01T00:00:00")
    defaults.update(overrides)
    repo = Repo(**defaults)
    repo.remotes = [Remote(id=1, repo_id=1, name="origin", url="git@github.com:user/test.git")]
    return repo


def _to_plain(formatted) -> str:
    return to_plain_text(formatted)


def _make_detail_panel(repo: Repo = None) -> DetailPanel:
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
    )


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


# ── line selection ─────────────────────────────────────────────────────────

def test_cursor_starts_at_zero():
    panel = _make_detail_panel()
    assert panel._cursor_index == 0


def test_cursor_down_moves():
    panel = _make_detail_panel()
    panel.cursor_down()
    assert panel._cursor_index == 1


def test_cursor_up_moves():
    panel = _make_detail_panel()
    panel.cursor_down()
    panel.cursor_up()
    assert panel._cursor_index == 0


def test_cursor_down_at_max():
    panel = _make_detail_panel()
    for _ in range(15):
        panel.cursor_down()
    assert panel._cursor_index == DetailPanel.MAX_LINE


def test_cursor_up_at_zero():
    panel = _make_detail_panel()
    panel.cursor_up()
    assert panel._cursor_index == 0


def test_cursor_blocked_during_edit():
    panel = _make_detail_panel()
    panel._edit_mode = "alias"
    panel.cursor_down()
    assert panel._cursor_index == 0


# ── alias edit ─────────────────────────────────────────────────────────────

def test_handle_enter_alias_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_ALIAS
    panel.handle_enter()
    assert panel._edit_mode == "alias"


def test_alias_edit_buffer_prepopulated():
    repo = _make_repo(alias="existing")
    panel = _make_detail_panel(repo)
    panel._start_alias_edit()
    assert panel.alias_buffer.text == "existing"


def test_handle_enter_confirm_alias():
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
    )
    panel._start_alias_edit()
    panel._alias_buffer.text = "new-alias"
    panel.handle_enter()
    assert repo.alias == "new-alias"
    assert panel._edit_mode is None


def test_handle_enter_alias_with_empty_buffer():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo()
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid, alias="old-alias")

    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel._start_alias_edit()
    panel._alias_buffer.text = ""
    panel.handle_enter()
    assert repo.alias == ""


# ── description edit ─────────────────────────────────────────────────────

def test_handle_enter_desc_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_DESC
    panel.handle_enter()
    assert panel._edit_mode == "description"


def test_desc_edit_buffer_prepopulated():
    repo = _make_repo(description="existing desc")
    panel = _make_detail_panel(repo)
    panel._start_desc_edit()
    assert panel.desc_buffer.text == "existing desc"


def test_handle_enter_confirm_description():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo(description="original")
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid, description="original")

    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel._start_desc_edit()
    panel._desc_buffer.text = "new description"
    panel.handle_enter()
    assert repo.description == "new description"
    assert panel._edit_mode is None


# ── tags edit ─────────────────────────────────────────────────────────────

def test_handle_enter_tags_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_TAGS
    panel.handle_enter()
    assert panel._edit_mode == "tags"


def test_handle_enter_tags_adds_tag():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo()
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid, path="/x", alias="", description="A test repo")

    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel._start_tags_edit()
    panel._tag_buffer.text = "python"
    panel.handle_enter()
    assert "python" in repo.tags
    # Enter stays in tags edit mode for more tag additions
    assert panel._edit_mode == "tags"


def test_handle_key_number_removes_tag():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo()
    rid = store.upsert_repo(repo)
    store.add_tag(rid, "alpha")
    store.add_tag(rid, "beta")
    repo = _make_repo(id=rid, path="/x", alias="", description="A test repo")
    repo.tags = store.get_tags_for_repo(rid)

    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel._start_tags_edit()
    panel.handle_key("1")
    assert "alpha" not in repo.tags
    assert "beta" in repo.tags


def test_handle_enter_confirm_description_clears_edit_mode():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo(description="original")
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid, description="original")

    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel._start_desc_edit()
    panel._desc_buffer.text = "new description"
    panel.handle_enter()
    assert repo.description == "new description"
    assert panel._edit_mode is None


# ── copy actions ──────────────────────────────────────────────────────────

def test_handle_enter_name_copies(monkeypatch):
    copied = []
    monkeypatch.setattr("blink.tui.detail.copy_path", lambda t: copied.append(t) or None)
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_NAME
    panel.handle_enter()
    assert copied == ["test-repo"]


def test_handle_enter_path_copies(monkeypatch):
    copied = []
    monkeypatch.setattr("blink.tui.detail.copy_path", lambda t: copied.append(t) or None)
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_PATH
    panel.handle_enter()
    assert copied == ["/tmp/test-repo"]


def test_handle_enter_git_opens_browser(monkeypatch):
    opened = []
    monkeypatch.setattr("blink.tui.detail.webbrowser.open", lambda u: opened.append(u) or None)
    panel = _make_detail_panel()
    panel._cursor_index = DetailPanel.LINE_GIT
    panel.handle_enter()
    assert opened == ["https://github.com/user/test"]


def test_handle_enter_git_none(monkeypatch):
    opened = []
    monkeypatch.setattr("blink.tui.detail.webbrowser.open", lambda u: opened.append(u) or None)
    repo = _make_repo()
    repo.remotes = []
    panel = _make_detail_panel(repo)
    panel._cursor_index = DetailPanel.LINE_GIT
    panel.handle_enter()
    assert opened == []


# ── is_editing ─────────────────────────────────────────────────────────────

def test_is_editing_false_by_default():
    panel = _make_detail_panel()
    assert not panel.is_editing


def test_is_editing_true_when_alias():
    panel = _make_detail_panel()
    panel._edit_mode = "alias"
    assert panel.is_editing


def test_is_editing_true_when_description():
    panel = _make_detail_panel()
    panel._edit_mode = "description"
    assert panel.is_editing


def test_is_editing_true_when_tags():
    panel = _make_detail_panel()
    panel._edit_mode = "tags"
    assert panel.is_editing


# ── pinned toggle ─────────────────────────────────────────────────────────

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


def test_handle_enter_pinned_toggles():
    store = Store(":memory:")
    store.init_db()
    repo = _make_repo()
    rid = store.upsert_repo(repo)
    repo = _make_repo(id=rid)

    pin_changed = []
    panel = DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
        on_pin_change=lambda: pin_changed.append(True),
    )
    panel._cursor_index = DetailPanel.LINE_PINNED
    panel.handle_enter()
    assert repo.pinned == 1
    assert pin_changed == [True]

    panel.handle_enter()
    assert repo.pinned == 0
    assert len(pin_changed) == 2


def test_detail_panel_line_constants():
    assert DetailPanel.LINE_IDE == 0
    assert DetailPanel.LINE_FINDER == 1
    assert DetailPanel.LINE_TLOOP == 2
    assert DetailPanel.LINE_COMMIT == 3
    assert DetailPanel.LINE_PULL == 4
    assert DetailPanel.LINE_NAME == 5
    assert DetailPanel.LINE_PATH == 6
    assert DetailPanel.LINE_GIT == 7
    assert DetailPanel.LINE_STATUS == 8
    assert DetailPanel.LINE_PINNED == 9
    assert DetailPanel.LINE_ALIAS == 10
    assert DetailPanel.LINE_TAGS == 11
    assert DetailPanel.LINE_DESC == 12
    assert DetailPanel.MAX_LINE == 12


# ── status row ─────────────────────────────────────────────────────────────


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


def test_detail_panel_status_between_git_and_pinned():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    git_pos = t.index("Git")
    status_pos = t.index("Status")
    pinned_pos = t.index("Pinned")
    assert git_pos < status_pos < pinned_pos


def test_handle_enter_status_copies(monkeypatch):
    copied = []
    monkeypatch.setattr("blink.tui.detail.copy_path", lambda t: copied.append(t) or None)
    repo = _make_repo(status=RepoStatus(branch="main", dirty_count=1))
    panel = _make_detail_panel(repo)
    panel._cursor_index = DetailPanel.LINE_STATUS
    panel.handle_enter()
    assert len(copied) == 1
    assert "main" in copied[0]
    assert "+1" in copied[0]


# ── pull row ───────────────────────────────────────────────────────────────


def test_detail_panel_renders_pull_row():
    panel = _make_detail_panel()
    t = _to_plain(panel._formatted_text())
    assert "Pull Latest" in t


def test_handle_enter_pull_calls_callback():
    pulled = []
    panel = _make_detail_panel()
    panel._on_pull = lambda: pulled.append(True)
    panel._cursor_index = DetailPanel.LINE_PULL
    panel.handle_enter()
    assert pulled == [True]