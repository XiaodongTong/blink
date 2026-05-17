from __future__ import annotations

from blink.models import Remote, Repo
from blink.store import Store
from blink.tui.detail import DetailPanel


def _make_repo(**overrides) -> Repo:
    defaults = dict(id=1, name="test-repo", alias="", path="/tmp/test-repo",
                    description="A test repo", last_synced="2025-01-01T00:00:00")
    defaults.update(overrides)
    repo = Repo(**defaults)
    repo.remotes = [Remote(id=1, repo_id=1, name="origin", url="git@github.com:user/test.git")]
    return repo


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
    text_str = str(text)
    assert "test-repo" in text_str
    assert "/tmp/test-repo" in text_str
    assert "A test repo" in text_str
    assert "origin" in text_str
    assert "git@github.com:user/test.git" in text_str
    assert "2025-01-01" in text_str


def test_detail_panel_renders_alias():
    repo = _make_repo(alias="my-alias")
    panel = _make_detail_panel(repo)
    text = panel._formatted_text()
    text_str = str(text)
    assert "my-alias" in text_str


def test_detail_panel_renders_no_alias():
    panel = _make_detail_panel()
    text = panel._formatted_text()
    text_str = str(text)
    assert "(none)" in text_str


def test_detail_panel_renders_tags():
    repo = _make_repo(tags=["python", "api"])
    panel = _make_detail_panel(repo)
    text = panel._formatted_text()
    text_str = str(text)
    assert "python" in text_str
    assert "api" in text_str


def test_detail_panel_renders_no_remotes():
    repo = _make_repo()
    repo.remotes = []
    panel = _make_detail_panel(repo)
    text = panel._formatted_text()
    text_str = str(text)
    assert "(none)" in text_str


def test_detail_panel_alias_edit_creates_buffer():
    panel = _make_detail_panel()
    assert not panel.is_editing_alias
    assert panel.alias_buffer is None

    panel.handle_alias_edit()
    assert panel.is_editing_alias
    assert panel.alias_buffer is not None


def test_detail_panel_alias_edit_prepopulates_buffer():
    repo = _make_repo(alias="existing")
    panel = _make_detail_panel(repo)
    panel.handle_alias_edit()
    assert panel.alias_buffer.text == "existing"


def test_detail_panel_alias_edit_empty_repo():
    panel = _make_detail_panel()
    panel.handle_alias_edit()
    assert panel.alias_buffer.text == ""


def test_detail_panel_confirm_alias():
    repo = _make_repo()
    panel = _make_detail_panel(repo)
    panel.handle_alias_edit()
    panel.confirm_alias("new-alias")
    assert repo.alias == "new-alias"
    assert not panel.is_editing_alias


def test_detail_panel_tag_edit_creates_buffer():
    panel = _make_detail_panel()
    assert not panel.is_adding_tag
    assert panel.tag_buffer is None

    panel.handle_tag_edit()
    assert panel.is_adding_tag
    assert panel.tag_buffer is not None


def test_detail_panel_tag_popover_text():
    repo = _make_repo(tags=["python", "rust"])
    panel = _make_detail_panel(repo)
    panel.handle_tag_edit()
    panel._tag_buffer.text = "new-tag"
    text = panel._formatted_text()
    text_str = str(text)
    assert "Tag Management" in text_str
    assert "python" in text_str
    assert "rust" in text_str
    assert "new-tag" in text_str


def test_detail_panel_tag_popover_shows_numbered_tags():
    repo = _make_repo(tags=["alpha", "beta"])
    panel = _make_detail_panel(repo)
    panel.handle_tag_edit()
    text = panel._formatted_text()
    text_str = str(text)
    assert "alpha" in text_str
    assert "beta" in text_str
    assert "1" in text_str
    assert "2" in text_str


def test_detail_panel_formatted_text_shows_buffer_during_alias_edit():
    panel = _make_detail_panel()
    panel.handle_alias_edit()
    panel._alias_buffer.text = "typed-alias"
    text = panel._formatted_text()
    text_str = str(text)
    assert "typed-alias" in text_str


def test_detail_panel_formatted_text_delegates_to_popover_during_tag_edit():
    panel = _make_detail_panel()
    panel.handle_tag_edit()
    panel._tag_buffer.text = "hello"
    text = panel._formatted_text()
    text_str = str(text)
    assert "Tag Management" in text_str
    assert "hello" in text_str


def test_detail_panel_handle_key_escape_cancels_alias_edit():
    panel = _make_detail_panel()
    panel.handle_alias_edit()
    assert panel.is_editing_alias
    panel.handle_key("escape")
    assert not panel.is_editing_alias


def test_detail_panel_handle_key_escape_cancels_tag_edit():
    panel = _make_detail_panel()
    panel.handle_tag_edit()
    assert panel.is_adding_tag
    panel.handle_key("escape")
    assert not panel.is_adding_tag


def test_detail_panel_handle_key_escape_calls_on_back():
    called = [False]

    def on_back():
        called[0] = True

    repo = _make_repo()
    panel = DetailPanel(
        repo=repo,
        store=Store(":memory:"),
        editors={},
        on_back=on_back,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    )
    panel.handle_key("escape")
    assert called[0]


def test_detail_panel_handle_key_enter_adds_tag():
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="x", path="/x"))

    tags_changed = [False]

    def on_tags_change():
        tags_changed[0] = True

    repo = _make_repo(id=rid, path="/x")
    panel = DetailPanel(
        repo=repo,
        store=store,
        editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=on_tags_change,
    )
    panel.handle_tag_edit()
    panel._tag_buffer.text = "python"
    panel.handle_key("enter")
    assert not panel.is_adding_tag
    assert "python" in repo.tags
    assert tags_changed[0]


def test_detail_panel_handle_key_number_removes_tag():
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="x", path="/x"))
    store.add_tag(rid, "alpha")
    store.add_tag(rid, "beta")

    tags_changed = [False]

    def on_tags_change():
        tags_changed[0] = True

    repo = _make_repo(id=rid, path="/x")
    repo.tags = store.get_tags_for_repo(rid)
    panel = DetailPanel(
        repo=repo,
        store=store,
        editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=on_tags_change,
    )
    panel.handle_tag_edit()
    panel.handle_key("1")  # removes first tag ("alpha")
    assert "alpha" not in repo.tags
    assert "beta" in repo.tags
    assert tags_changed[0]


def test_detail_panel_is_properties():
    panel = _make_detail_panel()
    assert not panel.is_editing_alias
    assert not panel.is_adding_tag
    assert panel.alias_buffer is None
    assert panel.tag_buffer is None
