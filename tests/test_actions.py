from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from blink.tui.actions import copy_path, detect_editors, open_in_editor


def test_detect_editors_keys() -> None:
    editors = detect_editors()
    assert "v" in editors
    assert "u" in editors
    assert "a" in editors
    assert "o" in editors
    assert editors["v"].name == "VSCode"
    assert editors["u"].name == "Cursor"
    assert editors["a"].name == "Antigravity IDE"
    assert editors["o"].name == "default"


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
