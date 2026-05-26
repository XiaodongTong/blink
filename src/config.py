from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DIR = Path.home() / ".blink"
DEFAULT_CONFIG_PATH = DEFAULT_DIR / "config.json"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "scan_paths": [str(Path.home())],
    "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", ".vscode", "Library", "Applications", "node_modules", "__pycache__"],
    "editor": "code",
    "preferred_ide": None,
    "auto_sync_days": 0,
    "nerd_fonts": False,
    "models": {
        "commit": "haiku",
        "task_review": "opus",
        "review": "opus",
        "task": "opus",
    },
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
    def preferred_ide(self) -> Optional[str]:
        return self._data.get("preferred_ide")

    @property
    def auto_sync_days(self) -> int:
        return int(self._data.get("auto_sync_days", _DEFAULT_CONFIG["auto_sync_days"]))

    @property
    def nerd_fonts(self) -> bool:
        return bool(self._data.get("nerd_fonts", _DEFAULT_CONFIG["nerd_fonts"]))

    @property
    def models(self) -> Dict[str, str]:
        defaults = _DEFAULT_CONFIG["models"]
        configured = self._data.get("models", {})
        return {**defaults, **configured}

    @property
    def model_commit(self) -> str:
        return self.models["commit"]

    @property
    def model_review(self) -> str:
        return self.models["review"]

    @property
    def model_task(self) -> str:
        return self.models["task"]

    def db_path(self) -> Path:
        return self._path.parent / "blink.db"

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()


_MODEL_DEFAULTS = {"commit": "haiku", "task_review": "opus", "review": "opus", "task": "opus"}


def get_default_model(purpose: str) -> str:
    """Read default model for a purpose from ~/.blink/config.json.

    purpose: "commit", "task_review", "review", or "task"
    """
    try:
        with open(DEFAULT_CONFIG_PATH, "r") as f:
            data = json.load(f)
        return data.get("models", {}).get(purpose, _MODEL_DEFAULTS[purpose])
    except Exception:
        return _MODEL_DEFAULTS[purpose]
