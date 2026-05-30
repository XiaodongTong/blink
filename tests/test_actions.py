from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from blink.tui.actions import (
    EditorInfo, copy_path, detect_editors, find_editor_by_name, open_in_editor,
)


def test_detect_editors_keys() -> None:
    editors = detect_editors()
    assert "v" in editors
    assert "u" in editors
    assert "a" in editors
    assert "o" in editors
    assert "i" in editors
    assert "p" in editors
    assert "w" in editors
    assert "g" in editors
    assert "s" in editors
    assert "z" in editors
    assert "x" in editors
    assert "n" in editors
    assert editors["v"].name == "VSCode"
    assert editors["u"].name == "Cursor"
    assert editors["a"].name.startswith("Antigravity")
    assert editors["i"].name == "IntelliJ"
    assert editors["p"].name == "PyCharm"
    assert editors["w"].name == "WebStorm"
    assert editors["g"].name == "GoLand"
    assert editors["s"].name == "Sublime"
    assert editors["z"].name == "Zed"
    assert editors["x"].name == "Xcode"
    assert editors["n"].name == "Neovim"
    assert editors["o"].name == "System"


def test_detect_editors_open_available() -> None:
    editors = detect_editors()
    assert editors["o"].available is True


def test_open_in_editor_default(tmp_path: Path) -> None:
    editors = detect_editors()
    repo = str(tmp_path / "myrepo")
    Path(repo).mkdir()
    with patch("subprocess.Popen") as mock_popen:
        open_in_editor(repo, "o", editors)
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == ["open", repo]


def test_open_in_editor_code(tmp_path: Path) -> None:
    editors = detect_editors()
    if not editors["v"].available:
        return
    repo = str(tmp_path / "myrepo")
    Path(repo).mkdir()
    with patch("subprocess.Popen") as mock_popen:
        open_in_editor(repo, "v", editors)
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0][0].endswith("code")


def test_copy_path(tmp_path: Path) -> None:
    result = copy_path("/tmp/test-repo")
    assert result is True


def test_copy_path_failure() -> None:
    with patch("subprocess.run", side_effect=subprocess.SubprocessError):
        assert copy_path("/tmp/test") is False


def test_find_editor_by_name_match() -> None:
    editors = {
        "v": EditorInfo(key="v", name="VSCode", command="/usr/local/bin/code"),
        "u": EditorInfo(key="u", name="Cursor", command="/usr/local/bin/cursor"),
    }
    assert find_editor_by_name("VSCode", editors) == "v"
    assert find_editor_by_name("Cursor", editors) == "u"


def test_find_editor_by_name_no_match() -> None:
    editors = {
        "v": EditorInfo(key="v", name="VSCode", command="/usr/local/bin/code"),
    }
    assert find_editor_by_name("NonExistent", editors) is None


def test_find_editor_by_name_accepts_dict_no_detect() -> None:
    editors = {
        "a": EditorInfo(key="a", name="Antigravity IDE", command="open"),
    }
    assert find_editor_by_name("Antigravity IDE", editors) == "a"
