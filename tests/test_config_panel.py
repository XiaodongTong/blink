from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from blink.config import Config
from blink.tui.actions import EditorInfo
from blink.tui.app_config import ConfigPanel, ConfigSelectMode


def _make_config(tmp_path: Path, editor: str | None = None) -> Config:
    cfg_path = tmp_path / ".blink" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"editor": editor}
    cfg_path.write_text(json.dumps(data))
    return Config(config_path=cfg_path)


def _make_editors() -> dict[str, EditorInfo]:
    return {
        "v": EditorInfo(key="v", name="VSCode", command="/usr/local/bin/code"),
        "u": EditorInfo(key="u", name="Cursor", command="/usr/local/bin/cursor"),
        "n": EditorInfo(key="n", name="Neovim", command=None),
    }


def _extract_texts(ft_list: list) -> list[str]:
    return [text for item in ft_list for text in (item[1],)]


def _all_text(panel: ConfigPanel) -> str:
    content = panel.create_content(80, 40)
    texts = []
    for i in range(content.line_count):
        line = content.get_line(i)
        texts.append("".join(item[1] for item in line))
    return "\n".join(texts)


# ── rendering ────────────────────────────────────────────────────


def test_renders_editable_items(tmp_path: Path) -> None:
    config = _make_config(tmp_path, editor="VSCode")
    panel = ConfigPanel(config, _make_editors())
    text = _all_text(panel)
    assert "Editor:" in text
    assert "Commit Model:" in text
    assert "Review Model:" in text
    assert "Task Model:" in text
    assert "Task Review:" in text


def test_renders_readonly_items(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    text = _all_text(panel)
    assert "Scan Paths:" in text
    assert "Exclude Dirs:" in text
    assert "Auto Sync:" in text
    assert "Nerd Fonts:" in text
    assert "(read-only)" in text


def test_selected_row_has_enter_hint(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    content = panel.create_content(80, 40)
    first_row = content.get_line(1)
    assert "[Enter]" in "".join(item[1] for item in first_row)


def test_line_count(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    content = panel.create_content(80, 40)
    # 1 section header + 5 editable + 1 section header + 4 readonly = 11
    assert content.line_count == 11


# ── cursor navigation ────────────────────────────────────────────


def test_cursor_down_wraps_at_max(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    for _ in range(10):
        panel.cursor_down()
    assert panel._cursor == 4  # 5 editable items, 0-indexed


def test_cursor_up_stops_at_zero(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.cursor_up()
    assert panel._cursor == 0


def test_cursor_navigates(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.cursor_down()
    assert panel._cursor == 1
    panel.cursor_up()
    assert panel._cursor == 0


# ── select mode ──────────────────────────────────────────────────


def test_enter_select_mode_editor(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.select_mode = ConfigSelectMode.editor
    assert panel.select_mode == ConfigSelectMode.editor
    assert panel.select_cursor == 0


def test_select_mode_model(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.select_mode = ConfigSelectMode.model
    opts = panel.get_select_options()
    assert opts == ["haiku", "sonnet", "opus"]


# ── editor options filter ────────────────────────────────────────


def test_editor_options_only_available(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    editors = _make_editors()
    panel = ConfigPanel(config, editors)
    opts = panel._get_editor_options()
    assert "VSCode" in opts
    assert "Cursor" in opts
    assert "Neovim" not in opts


# ── confirm selection ────────────────────────────────────────────


def test_confirm_editor_selection(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    editors = _make_editors()
    panel = ConfigPanel(config, editors)
    panel.select_mode = ConfigSelectMode.editor
    panel.select_cursor = 1  # Cursor
    panel.confirm_selection()
    assert config.editor == "Cursor"
    assert panel.select_mode == ConfigSelectMode.none


def test_confirm_model_selection(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.cursor_down()  # move to Commit Model
    panel.select_mode = ConfigSelectMode.model
    panel.select_cursor = 2  # opus
    panel.confirm_selection()
    assert config.model_commit == "opus"
    assert panel.select_mode == ConfigSelectMode.none


def test_cancel_selection(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    panel = ConfigPanel(config, _make_editors())
    panel.select_mode = ConfigSelectMode.editor
    panel.cancel_selection()
    assert panel.select_mode == ConfigSelectMode.none
