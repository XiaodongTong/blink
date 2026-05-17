from __future__ import annotations

from blink.models import Repo
from blink.tui.repo_list import RepoListControl


def test_preferred_height_single_repo():
    control = RepoListControl()
    control.set_repos([Repo(name="test", path="/tmp/test")])
    h = control.preferred_height(80, 40, False, None)
    assert h == 2


def test_preferred_height_multiple_repos():
    control = RepoListControl()
    control.set_repos([
        Repo(name="a", path="/a"),
        Repo(name="b", path="/b"),
        Repo(name="c", path="/c"),
    ])
    h = control.preferred_height(80, 40, False, None)
    assert h == 6


def test_preferred_height_empty():
    control = RepoListControl()
    control.set_repos([])
    h = control.preferred_height(80, 40, False, None)
    assert h == 1


def test_two_line_render_selected():
    control = RepoListControl()
    control.set_repos([Repo(name="test", path="/tmp/test")])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    line1 = content.get_line(1)
    assert "test" in str(line0)
    assert "/tmp/test" in str(line1)


def test_two_line_render_with_tags():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", tags=["python", "api"])
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    line0_str = str(line0)
    assert "test" in line0_str
    assert "python" in line0_str
    assert "api" in line0_str


def test_two_line_render_unselected():
    control = RepoListControl()
    control.set_repos([Repo(name="a", path="/a"), Repo(name="b", path="/b")])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    line1 = content.get_line(1)
    line2 = content.get_line(2)
    line3 = content.get_line(3)
    assert "a" in str(line0)
    assert "/a" in str(line1)
    assert "b" in str(line2)
    assert "/b" in str(line3)


def test_display_name_shows_both_alias_and_name():
    control = RepoListControl()
    repo = Repo(name="real-name", alias="my-alias", path="/x")
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    line0_str = str(line0)
    assert "my-alias" in line0_str
    assert "real-name" in line0_str


def test_move_up_down():
    control = RepoListControl()
    control.set_repos([Repo(name="a", path="/a"), Repo(name="b", path="/b")])
    assert control.selected_index == 0
    control.move_down()
    assert control.selected_index == 1
    control.move_up()
    assert control.selected_index == 0


def test_move_up_no_wrap():
    control = RepoListControl()
    control.set_repos([Repo(name="a", path="/a")])
    control.move_up()
    assert control.selected_index == 0


def test_move_down_no_wrap():
    control = RepoListControl()
    control.set_repos([Repo(name="a", path="/a")])
    control.move_down()
    assert control.selected_index == 0