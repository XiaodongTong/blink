from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.controls import UIContent, UIControl

from blink.config import Config
from blink.tui.actions import EditorInfo


class ConfigSelectMode(Enum):
    none = "none"
    editor = "editor"
    model = "model"


_EDITABLE_ITEMS: list[tuple[str, str, str]] = [
    ("Editor", "editor", "editor"),
    ("Commit Model", "commit", "model"),
    ("Review Model", "review", "model"),
    ("Task Model", "task", "model"),
    ("Task Review", "task_review", "model"),
]

_READONLY_ITEMS: list[tuple[str, str]] = [
    ("Scan Paths", "scan_paths"),
    ("Exclude Dirs", "exclude_dirs"),
    ("Auto Sync", "auto_sync_days"),
    ("Nerd Fonts", "nerd_fonts"),
]

MODEL_OPTIONS = ["haiku", "sonnet", "opus"]

_INDENT = "  "


class ConfigPanel(UIControl):
    def __init__(self, config: Config, editors: Dict[str, EditorInfo]) -> None:
        self._config = config
        self._editors = editors
        self._cursor: int = 0
        self._max_editable = len(_EDITABLE_ITEMS)
        self._select_mode = ConfigSelectMode.none
        self._select_cursor: int = 0
        self._select_scroll_offset: int = 0

    def is_focusable(self) -> bool:
        return True

    @property
    def select_mode(self) -> ConfigSelectMode:
        return self._select_mode

    @select_mode.setter
    def select_mode(self, mode: ConfigSelectMode) -> None:
        self._select_mode = mode
        self._select_cursor = 0
        self._select_scroll_offset = 0

    @property
    def select_cursor(self) -> int:
        return self._select_cursor

    @select_cursor.setter
    def select_cursor(self, val: int) -> None:
        self._select_cursor = val

    @property
    def select_scroll_offset(self) -> int:
        return self._select_scroll_offset

    @select_scroll_offset.setter
    def select_scroll_offset(self, val: int) -> None:
        self._select_scroll_offset = val

    def cursor_up(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1

    def cursor_down(self) -> None:
        if self._cursor < self._max_editable - 1:
            self._cursor += 1

    def create_content(self, width: int, height: int) -> UIContent:
        lines = self._build_lines(width)
        line_count = len(lines)

        def get_line(i: int) -> FormattedText:
            if 0 <= i < line_count:
                return lines[i]
            return FormattedText([("", "")])

        return UIContent(get_line=get_line, line_count=line_count)

    def _get_current_value(self, item_key: str, item_type: str) -> str:
        if item_type == "editor":
            val = self._config.editor
            return val or "(not set)"
        return self._config.models.get(item_key, "")

    def _get_editor_options(self) -> list[str]:
        return [e.name for e in self._editors.values() if e.available]

    def _build_lines(self, width: int) -> list[FormattedText]:
        lines: list[FormattedText] = []
        lines.append(FormattedText([("class:detail-section", f"{_INDENT}Settings")]))

        for idx, (label, key, itype) in enumerate(_EDITABLE_ITEMS):
            value = self._get_current_value(key, itype)
            selected = idx == self._cursor
            lines.append(self._render_editable_row(label, value, selected))

        lines.append(FormattedText([("class:detail-section", f"{_INDENT}Read-only")]))

        for label, key in _READONLY_ITEMS:
            value = self._format_readonly_value(key)
            lines.append(self._render_readonly_row(label, value))

        return lines

    def _render_editable_row(
        self, label: str, value: str, selected: bool
    ) -> FormattedText:
        if selected:
            return FormattedText([
                ("class:detail-selected", f"{_INDENT}▸ {label}:  "),
                ("class:detail-selected", value),
                ("class:detail-selected", "  [Enter]"),
            ])
        return FormattedText([
            ("class:detail-label", f"{_INDENT}  {label}:  "),
            ("class:detail-value", value),
        ])

    def _render_readonly_row(self, label: str, value: str) -> FormattedText:
        return FormattedText([
            ("class:detail-label", f"{_INDENT}  {label}:  "),
            ("class:detail-dim", value),
            ("class:detail-dim", " (read-only)"),
        ])

    def _format_readonly_value(self, key: str) -> str:
        if key == "scan_paths":
            paths = self._config.scan_paths
            if len(paths) <= 2:
                return ", ".join(paths)
            return f"{paths[0]}, ... (+{len(paths) - 1})"
        if key == "exclude_dirs":
            dirs = self._config.exclude_dirs
            return f"{len(dirs)} dirs"
        if key == "auto_sync_days":
            val = self._config.auto_sync_days
            return "disabled" if val == 0 else f"{val} days"
        if key == "nerd_fonts":
            return str(self._config.nerd_fonts)
        return ""

    def get_select_options(self) -> list[str]:
        if self._select_mode == ConfigSelectMode.editor:
            return self._get_editor_options()
        if self._select_mode == ConfigSelectMode.model:
            return list(MODEL_OPTIONS)
        return []

    def confirm_selection(self) -> None:
        opts = self.get_select_options()
        if not opts or self._select_cursor >= len(opts):
            return
        _, key, itype = _EDITABLE_ITEMS[self._cursor]
        chosen = opts[self._select_cursor]
        if itype == "editor":
            self._config.set("editor", chosen)
        else:
            self._config.set_model(key, chosen)
        self._select_mode = ConfigSelectMode.none

    def cancel_selection(self) -> None:
        self._select_mode = ConfigSelectMode.none

    def reload(self) -> None:
        pass
