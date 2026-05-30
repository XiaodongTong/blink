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
    cfg_path.write_text(json.dumps({"editor": "VSCode", "scan_paths": ["/tmp"]}))
    cfg = Config(config_path=cfg_path)
    assert cfg.editor == "VSCode"
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
    cfg.set("editor", "VSCode")
    assert cfg.editor == "VSCode"
    data = json.loads(cfg_path.read_text())
    assert data["editor"] == "VSCode"


# ── _migrate_editor_key ──────────────────────────────────────────


def test_migrate_editor_key_single_letter(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"editor": "v"}))
    cfg = Config(config_path=cfg_path)
    assert cfg.editor == "VSCode"
    data = json.loads(cfg_path.read_text())
    assert data["editor"] == "VSCode"


def test_migrate_editor_key_name_unchanged(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"editor": "VSCode"}))
    cfg = Config(config_path=cfg_path)
    assert cfg.editor == "VSCode"


def test_migrate_editor_key_none_unchanged(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    assert cfg.editor is None


def test_migrate_editor_key_invalid_single_char(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"editor": "q"}))
    cfg = Config(config_path=cfg_path)
    assert cfg.editor == "q"


# ── set_model ────────────────────────────────────────────────────


def test_set_model_persists(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg = Config(config_path=cfg_path)
    cfg.set_model("commit", "opus")
    assert cfg.model_commit == "opus"
    data = json.loads(cfg_path.read_text())
    assert data["models"]["commit"] == "opus"


def test_set_model_creates_models_if_missing(tmp_path: Path) -> None:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"editor": None}))
    cfg = Config(config_path=cfg_path)
    cfg.set_model("review", "sonnet")
    assert cfg.model_review == "sonnet"
