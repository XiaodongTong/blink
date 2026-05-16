"""Tests for printable character routing to alias/tag buffers in all edit modes."""
from __future__ import annotations

from unittest.mock import MagicMock

from blink.models import Remote, Repo
from blink.store import Store
from blink.tui.detail import DetailPanel


def _make_store_with_repo() -> tuple[Store, int]:
    store = Store(":memory:")
    store.init_db()
    rid = store.upsert_repo(Repo(name="test-repo", path="/tmp/test"))
    return store, rid


def test_route_printable_list_alias_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_alias_edit(repo)
    assert app._editing_alias
    assert app._alias_buffer.text == ""

    app._route_printable("h")
    app._route_printable("e")
    app._route_printable("l")
    app._route_printable("l")
    app._route_printable("o")
    assert app._alias_buffer.text == "hello"


def test_route_backspace_list_alias_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_alias_edit(repo)
    app._route_printable("a")
    app._route_printable("b")
    assert app._alias_buffer.text == "ab"
    app._route_backspace()
    assert app._alias_buffer.text == "a"
    app._route_backspace()
    assert app._alias_buffer.text == ""


def test_route_printable_list_tag_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_tag_edit(repo)
    assert app._editing_tag
    assert app._tag_buffer.text == ""

    app._route_printable("p")
    app._route_printable("y")
    assert app._tag_buffer.text == "py"


def test_route_backspace_list_tag_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_tag_edit(repo)
    app._route_printable("x")
    app._route_backspace()
    assert app._tag_buffer.text == ""


def test_route_printable_detail_alias_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    assert app._detail_panel is not None

    app._detail_panel.handle_alias_edit()
    assert app._detail_panel.is_editing_alias
    assert app._detail_panel._alias_buffer is not None

    app._route_printable("n")
    app._route_printable("e")
    app._route_printable("w")
    assert app._detail_panel._alias_buffer.text == "new"


def test_route_backspace_detail_alias_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    app._detail_panel.handle_alias_edit()
    app._route_printable("a")
    app._route_printable("b")
    app._route_backspace()
    assert app._detail_panel._alias_buffer.text == "a"


def test_route_printable_detail_tag_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    app._detail_panel.handle_tag_edit()
    assert app._detail_panel.is_adding_tag
    assert app._detail_panel._tag_buffer is not None

    app._route_printable("r")
    app._route_printable("u")
    app._route_printable("s")
    app._route_printable("t")
    assert app._detail_panel._tag_buffer.text == "rust"


def test_route_backspace_detail_tag_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    app._detail_panel.handle_tag_edit()
    app._route_printable("x")
    app._route_backspace()
    assert app._detail_panel._tag_buffer.text == ""


def test_route_printable_space_to_buffer(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_alias_edit(repo)
    app._route_printable("h")
    app._route_printable("i")
    app._route_printable(" ")
    app._route_printable("t")
    app._route_printable("h")
    app._route_printable("e")
    app._route_printable("r")
    app._route_printable("e")
    assert app._alias_buffer.text == "hi there"


def test_route_printable_ignored_in_normal_mode(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    assert app._mode == "list"
    assert not app._editing_alias
    assert not app._editing_tag
    assert app._detail_panel is None

    app._route_printable("x")
    # No crash, buffer unchanged
    assert app._alias_buffer.text == ""
    assert app._tag_buffer.text == ""


def test_status_text_shows_alias_buffer_in_list_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_alias_edit(repo)
    app._route_printable("f")
    app._route_printable("o")
    app._route_printable("o")
    status = app._status_text()
    assert "foo" in str(status)


def test_status_text_shows_tag_buffer_in_list_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._start_tag_edit(repo)
    app._route_printable("b")
    app._route_printable("a")
    app._route_printable("r")
    status = app._status_text()
    assert "bar" in str(status)


def test_status_text_shows_alias_buffer_in_detail_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    app._detail_panel.handle_alias_edit()
    app._route_printable("z")
    status = app._status_text()
    assert "z" in str(status)


def test_status_text_shows_tag_buffer_in_detail_edit(app_with_store):
    app, store, rid = app_with_store
    repo = Repo(id=rid, name="test-repo", path="/tmp/test")
    app._repo_control.set_repos([repo])

    app._show_detail_view(repo)
    app._detail_panel.handle_tag_edit()
    app._route_printable("w")
    status = app._status_text()
    assert "w" in str(status)


def test_in_edit_mode_list_alias():
    from blink.scanner import Scanner
    store, rid = _make_store_with_repo()
    from blink.tui.app import BlinkApp
    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._list_layout = MagicMock()
    app._mode = "list"
    app._editing_alias = True
    app._editing_tag = False
    assert app._in_edit_mode() is True
    assert app._in_tag_mode() is False


def test_in_edit_mode_list_tag():
    from blink.scanner import Scanner
    store, rid = _make_store_with_repo()
    from blink.tui.app import BlinkApp
    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._list_layout = MagicMock()
    app._mode = "list"
    app._editing_alias = False
    app._editing_tag = True
    assert app._in_edit_mode() is True
    assert app._in_tag_mode() is True


def test_in_edit_mode_detail_alias():
    from blink.scanner import Scanner
    store, rid = _make_store_with_repo()
    from blink.tui.app import BlinkApp
    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._list_layout = MagicMock()
    app._mode = "detail"
    app._editing_alias = False
    app._editing_tag = False
    panel = MagicMock()
    panel.is_editing_alias = True
    panel.is_adding_tag = False
    app._detail_panel = panel
    assert app._in_edit_mode() is True
    assert app._in_tag_mode() is False


def test_in_edit_mode_detail_tag():
    from blink.scanner import Scanner
    store, rid = _make_store_with_repo()
    from blink.tui.app import BlinkApp
    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._list_layout = MagicMock()
    app._mode = "detail"
    app._editing_alias = False
    app._editing_tag = False
    panel = MagicMock()
    panel.is_editing_alias = False
    panel.is_adding_tag = True
    app._detail_panel = panel
    assert app._in_edit_mode() is True
    assert app._in_tag_mode() is True


def test_in_edit_mode_normal():
    from blink.scanner import Scanner
    store, rid = _make_store_with_repo()
    from blink.tui.app import BlinkApp
    scanner = MagicMock(spec=Scanner)
    app = BlinkApp.__new__(BlinkApp)
    app._store = store
    app._scanner = scanner
    app._editors = {}
    app._scanning = False
    app._scan_status = ""
    app._repo_control = MagicMock()
    app._search_bar = MagicMock()
    app._status_control = MagicMock()
    app._footer_control = MagicMock()
    app._detail_panel = None
    app._list_layout = MagicMock()
    app._mode = "list"
    app._editing_alias = False
    app._editing_tag = False
    assert app._in_edit_mode() is False
    assert app._in_tag_mode() is False
