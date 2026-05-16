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


def detect_editors() -> Dict[str, EditorInfo]:
    editors: Dict[str, EditorInfo] = {}
    for key, name, cmd in [
        ("v", "VSCode", "code"),
        ("u", "Cursor", "cursor"),
        ("a", "Antigravity", None),
        ("o", "default", None),
    ]:
        found = shutil.which(cmd) if cmd else None
        if name == "Antigravity":
            found = shutil.which("open")
        if name == "default":
            found = shutil.which("open")
        editors[key] = EditorInfo(key=key, name=name, command=found)
    return editors


def open_in_editor(repo_path: str, editor_key: str, editors: Dict[str, EditorInfo]) -> None:
    info = editors.get(editor_key)
    if info is None or not info.available:
        return
    if editor_key == "a":
        subprocess.Popen(["open", "-a", "Antigravity", repo_path],
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
