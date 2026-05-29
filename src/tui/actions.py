from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class EditorInfo:
    key: str
    name: str
    command: Optional[str]

    @property
    def available(self) -> bool:
        return self.command is not None


IDE_CHOICES = [("v", "VSCode"), ("u", "Cursor"), ("a", "Antigravity")]


def _detect_antigravity() -> tuple[str, str]:
    """Return (app_name, command) for Antigravity, preferring IDE variant."""
    if shutil.which("open"):
        result = subprocess.run(
            ["osascript", "-e", 'id of app "Antigravity IDE"'],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return "Antigravity IDE", "open"
        result = subprocess.run(
            ["osascript", "-e", 'id of app "Antigravity"'],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return "Antigravity", "open"
    return "Antigravity IDE", "none"


def detect_editors() -> Dict[str, EditorInfo]:
    editors: Dict[str, EditorInfo] = {}
    anti_name, anti_cmd = _detect_antigravity()
    for key, name, cmd in [
        ("v", "VSCode", "code"),
        ("u", "Cursor", "cursor"),
        ("a", anti_name, anti_cmd if anti_cmd != "none" else None),
        ("o", "default", "open"),
    ]:
        found = shutil.which(cmd) if cmd else None
        editors[key] = EditorInfo(key=key, name=name, command=found)
    return editors


def open_in_editor(repo_path: str, editor_key: str, editors: Dict[str, EditorInfo]) -> None:
    info = editors.get(editor_key)
    if info is None or not info.available:
        return
    if editor_key == "a":
        subprocess.Popen(["open", "-a", info.name, repo_path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif editor_key == "o":
        subprocess.Popen(["open", repo_path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif info.command:
        subprocess.Popen([info.command, repo_path],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def copy_path(repo_path: str) -> bool:
    try:
        proc = subprocess.run(
            ["pbcopy"],
            input=repo_path.encode(),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def open_terminal(repo_path: str) -> bool:
    """Open a new terminal window at the given path.

    Supports iTerm2 and macOS Terminal.app. Returns True on success.
    """
    # Try iTerm2 first
    iterm_script = f'''
    tell application "iTerm2"
        activate
        set newWindow to (create window with default profile)
        tell current session of newWindow
            write text "cd {repo_path}"
        end tell
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", iterm_script],
            check=True, capture_output=True, timeout=5,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        pass

    # Fallback to macOS Terminal.app
    terminal_script = f'''
    tell application "Terminal"
        activate
        do script "cd {repo_path}"
    end tell
    '''
    try:
        subprocess.run(
            ["osascript", "-e", terminal_script],
            check=True, capture_output=True, timeout=5,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        pass

    # Last resort: open -a Terminal
    try:
        subprocess.Popen(
            ["open", "-a", "Terminal", repo_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False
