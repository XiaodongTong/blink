from __future__ import annotations

from prompt_toolkit.formatted_text import to_plain_text

from blink.models import Repo, RepoStatus
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


def test_pinned_repo_shows_star():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", pinned=1)
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    line0_str = str(line0)
    assert "★" in line0_str


def test_unpinned_repo_no_star():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", pinned=0)
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line0 = content.get_line(0)
    assert "★" not in str(line0)


# ── status badge ─────────────────────────────────────────────────────────


def test_badge_shows_loading_when_no_status():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test")
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    assert "···" in str(line1)


def test_badge_shows_clean_status():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", status=RepoStatus(branch="main"))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    line1_str = str(line1)
    assert "main" in line1_str
    assert "●" in line1_str


def test_badge_shows_dirty_status():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", status=RepoStatus(branch="feature", dirty_count=3))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    line1_str = str(line1)
    assert "feature" in line1_str
    assert "○" in line1_str
    assert "+3" in line1_str


def test_badge_shows_ahead_behind():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", status=RepoStatus(branch="main", ahead=1, behind=3))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    line1_str = str(line1)
    assert "↑1" in line1_str
    assert "↓3" in line1_str


def test_badge_shows_error():
    control = RepoListControl()
    repo = Repo(name="test", id=42, path="/tmp/test")
    control.error_repo_ids.add(42)
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    assert "⚠" in str(line1)


def test_badge_right_aligned_in_width():
    control = RepoListControl()
    repo = Repo(name="test", path="/tmp/test", status=RepoStatus(branch="main"))
    control.set_repos([repo])
    content = control.create_content(80, 40)
    line1 = content.get_line(1)
    line1_str = to_plain_text(line1)
    assert len(line1_str) == 80


def test_format_status_badge_error_overrides_status():
    control = RepoListControl()
    repo = Repo(name="test", id=1, path="/tmp/test", status=RepoStatus(branch="main"))
    control.error_repo_ids.add(1)
    badge = control._format_status_badge(repo.status, is_error=True)
    badge_str = "".join(t for _, t in badge)
    assert "⚠" in badge_str
    assert "main" not in badge_str