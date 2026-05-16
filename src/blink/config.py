from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DIR = Path.home() / ".blink"
DEFAULT_CONFIG_PATH = DEFAULT_DIR / "config.json"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "scan_paths": [str(Path.home())],
    "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", ".vscode", "Library", "Applications", "node_modules", "__pycache__"],
    "editor": "code",
    "auto_sync_days": 0,
}


class Config:
    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or DEFAULT_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("config must be a JSON object")
                self._data = {**_DEFAULT_CONFIG, **data}
            except (json.JSONDecodeError, ValueError, OSError):
                self._data = dict(_DEFAULT_CONFIG)
                self._save()
        else:
            self._data = dict(_DEFAULT_CONFIG)
            self._ensure_dir()
            self._save()

    def _save(self) -> None:
        self._ensure_dir()
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
            f.write("\n")

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def scan_paths(self) -> List[str]:
        return list(self._data.get("scan_paths", _DEFAULT_CONFIG["scan_paths"]))

    @property
    def exclude_dirs(self) -> List[str]:
        return list(self._data.get("exclude_dirs", _DEFAULT_CONFIG["exclude_dirs"]))

    @property
    def editor(self) -> str:
        return str(self._data.get("editor", _DEFAULT_CONFIG["editor"]))

    @property
    def auto_sync_days(self) -> int:
        return int(self._data.get("auto_sync_days", _DEFAULT_CONFIG["auto_sync_days"]))

    def db_path(self) -> Path:
        return self._path.parent / "blink.db"

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()
