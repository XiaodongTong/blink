"""Tests for printable character routing to detail panel buffers during edit modes."""
from __future__ import annotations

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


def _make_detail_panel_with_store(repo=None):
    if repo is None:
        repo = _make_repo()
    store = Store(":memory:")
    store.init_db()
    return DetailPanel(
        repo=repo, store=store, editors={},
        on_back=lambda: None,
        on_alias_change=lambda a: None,
        on_tags_change=lambda: None,
    ), store


def test_route_printable_to_alias_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_alias_edit()
    assert panel._alias_buffer is not None
    panel._alias_buffer.text = "old"

    panel.route_printable("n")
    panel.route_printable("e")
    panel.route_printable("w")
    assert panel._alias_buffer.text == "oldnew"


def test_route_backspace_alias_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_alias_edit()
    assert panel._alias_buffer is not None
    panel._alias_buffer.text = "alias"

    panel.route_backspace()
    assert panel._alias_buffer.text == "alia"


def test_route_printable_to_desc_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_desc_edit()
    assert panel._desc_buffer is not None
    panel._desc_buffer.text = ""

    panel.route_printable("n")
    panel.route_printable("e")
    panel.route_printable("w")
    assert panel._desc_buffer.text == "new"


def test_route_backspace_desc_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_desc_edit()
    assert panel._desc_buffer is not None
    panel._desc_buffer.text = "desc"

    panel.route_backspace()
    assert panel._desc_buffer.text == "des"


def test_route_printable_to_tag_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_tags_edit()
    assert panel._tag_buffer is not None
    panel._tag_buffer.text = ""

    panel.route_printable("p")
    panel.route_printable("y")
    assert panel._tag_buffer.text == "py"


def test_route_backspace_tag_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_tags_edit()
    assert panel._tag_buffer is not None
    panel._tag_buffer.text = "tag"

    panel.route_backspace()
    assert panel._tag_buffer.text == "ta"


def test_route_printable_space_to_buffer():
    panel, _ = _make_detail_panel_with_store()
    panel._start_alias_edit()
    assert panel._alias_buffer is not None
    panel._alias_buffer.text = ""

    panel.route_printable("h")
    panel.route_printable("i")
    panel.route_printable(" ")
    panel.route_printable("t")
    assert panel._alias_buffer.text == "hi t"


def test_route_printable_ignored_when_not_editing():
    panel, _ = _make_detail_panel_with_store()
    panel.route_printable("x")
    assert panel._edit_mode is None