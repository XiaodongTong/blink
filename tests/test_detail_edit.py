from __future__ import annotations

from prompt_toolkit.formatted_text import to_plain_text

from blink.models import Remote, Repo
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


# ── cursor navigation ──────────────────────────────────────────────────


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
    assert panel._cursor_index == panel._max_cursor


def test_cursor_up_at_zero():
    panel = _make_detail_panel()
    panel.cursor_up()
    assert panel._cursor_index == 0


def test_cursor_blocked_during_edit():
    panel = _make_detail_panel()
    panel._edit_mode = "alias"
    panel.cursor_down()
    assert panel._cursor_index == 0


def test_cursor_navigates_full_range():
    panel = _make_detail_panel()
    assert panel._cursor_index == 0
    for expected in range(1, panel._max_cursor + 1):
        panel.cursor_down()
        assert panel._cursor_index == expected
    panel.cursor_down()
    assert panel._cursor_index == panel._max_cursor
    for expected in range(panel._max_cursor - 1, -1, -1):
        panel.cursor_up()
        assert panel._cursor_index == expected
    panel.cursor_up()
    assert panel._cursor_index == 0


# ── alias edit ──────────────────────────────────────────────────────────


def test_handle_enter_alias_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = len(panel._navigable_actions()) + 1
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


# ── description edit ────────────────────────────────────────────────────


def test_handle_enter_desc_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = len(panel._navigable_actions()) + 3
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


# ── tags edit ───────────────────────────────────────────────────────────


def test_handle_enter_tags_starts_edit():
    panel = _make_detail_panel()
    panel._cursor_index = len(panel._navigable_actions()) + 2
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


# ── is_editing ──────────────────────────────────────────────────────────


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


# ── pinned toggle ───────────────────────────────────────────────────────


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
    panel._cursor_index = len(panel._navigable_actions())
    panel.handle_enter()
    assert repo.pinned == 1
    assert pin_changed == [True]

    panel.handle_enter()
    assert repo.pinned == 0
    assert len(pin_changed) == 2
