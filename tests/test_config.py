from __future__ import annotations

import json
from pathlib import Path

from blink.config import Config


def test_creates_config_on_first_run(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg_path.exists()
    data = json.loads(cfg_path.read_text())
    assert "scan_paths" in data
    assert data["editor"] is None


def test_loads_existing_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"editor": "v", "scan_paths": ["/tmp"]}))
    cfg = Config(config_path=cfg_path)
    assert cfg.editor == "v"
    assert cfg.scan_paths == ["/tmp"]


def test_corrupted_config_replaced(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("not valid json {{{")
    cfg = Config(config_path=cfg_path)
    assert cfg.editor is None
    data = json.loads(cfg_path.read_text())
    assert data["editor"] is None


def test_non_object_config_replaced(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("42")
    cfg = Config(config_path=cfg_path)
    assert cfg.editor is None


def test_db_path(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg.db_path() == tmp_path / ".blink" / "blink.db"


def test_auto_sync_days_default(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg.auto_sync_days == 0


def test_exclude_dirs(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert "node_modules" in cfg.exclude_dirs


def test_set_persists(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    cfg.set("editor", "v")
    assert cfg.editor == "v"
    data = json.loads(cfg_path.read_text())
    assert data["editor"] == "v"
