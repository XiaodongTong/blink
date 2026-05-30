from __future__ import annotations

import time
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText

from blink.models import display_width

if TYPE_CHECKING:
    from blink.tui.app import BlinkApp


def _build_horizontal_select(
    opts: list[str],
    cursor: int,
    offset: int,
    width: int,
    prefix: str,
    suffix: str,
    style_label: str = "class:status-label",
    style_accent: str = "class:status-accent",
    style_dim: str = "class:status-dim",
) -> tuple[FormattedText, int]:
    if not opts:
        return FormattedText([]), offset

    prefix_w = display_width(prefix)
    suffix_w = display_width(suffix)
    available = max(0, width - prefix_w - suffix_w)
    n = len(opts)

    def _item_w(idx: int) -> int:
        return 2 + display_width(opts[idx])

    def _build_window(start: int) -> tuple[list[int], int, bool, bool]:
        has_left = start > 0
        used = 2 if has_left else 0
        indices: list[int] = []
        for i in range(start, n):
            sep = 2 if indices else 0
            iw = sep + _item_w(i)
            if used + iw > available:
                break
            used += iw
            indices.append(i)
        has_right = bool(indices) and indices[-1] + 1 < n
        if has_right and used + 2 > available:
            if len(indices) > 1:
                last = indices.pop()
                used -= (2 + _item_w(last))
            else:
                has_right = False
        return indices, used, has_left, has_right

    off = max(0, min(offset, n - 1))
    indices, used, has_left, has_right = _build_window(off)

    if not indices:
        off = max(0, min(cursor, n - 1))
        indices = [off]
        has_left = off > 0
        has_right = off < n - 1
    elif cursor < indices[0]:
        while off > 0 and (not indices or cursor < indices[0]):
            off -= 1
            indices, used, has_left, has_right = _build_window(off)
        if not indices or cursor < indices[0]:
            off = cursor
            indices = [cursor]
            has_left = cursor > 0
            has_right = cursor < n - 1
    elif cursor > indices[-1]:
        while off < n - 1 and (not indices or cursor > indices[-1]):
            off += 1
            indices, used, has_left, has_right = _build_window(off)
        if not indices or cursor > indices[-1]:
            off = cursor
            indices = [cursor]
            has_left = cursor > 0
            has_right = cursor < n - 1

    while off > 0:
        t_idx, _, _, _ = _build_window(off - 1)
        if t_idx and cursor in t_idx:
            off -= 1
            indices, used, has_left, has_right = _build_window(off)
        else:
            break

    parts: list[tuple[str, str]] = [(style_label, prefix)]
    if has_left:
        parts.append((style_dim, "‹ "))
    for pos, i in enumerate(indices):
        if pos > 0:
            parts.append((style_dim, "  "))
        if i == cursor:
            parts.append((style_accent, f"▸ {opts[i]}"))
        else:
            parts.append((style_dim, f"  {opts[i]}"))
    if has_right:
        parts.append((style_dim, " ›"))
    parts.append((style_dim, suffix))
    return FormattedText(parts), off


def _build_ide_select_status(app: BlinkApp) -> FormattedText:
    opts = app._ide_options()
    if not opts:
        return FormattedText([])

    try:
        total_width = app._app.output.get_size().columns
    except Exception:
        total_width = 120

    names = [name for _, name in opts]
    prefix = " Select IDE:  "
    suffix = "    ←→:选择  Enter:确认  Esc:取消"
    ft, new_offset = _build_horizontal_select(
        names, app._ide_select_cursor, app._ide_scroll_offset,
        total_width, prefix, suffix,
    )
    app._ide_scroll_offset = new_offset
    return ft


def build_config_select_status(app: BlinkApp) -> FormattedText:
    panel = app._config_panel
    if panel is None:
        return FormattedText([])
    from blink.tui.app_config import ConfigSelectMode
    mode = panel.select_mode
    if mode == ConfigSelectMode.none:
        return FormattedText([])

    try:
        total_width = app._app.output.get_size().columns
    except Exception:
        total_width = 120

    opts = panel.get_select_options()
    if not opts:
        return FormattedText([])

    if mode == ConfigSelectMode.editor:
        prefix = f" Select Editor:  "
        suffix = "    ←→:选择  Enter:确认  Esc:取消"
        ft, new_offset = _build_horizontal_select(
            opts, panel.select_cursor, panel.select_scroll_offset,
            total_width, prefix, suffix,
        )
        panel.select_scroll_offset = new_offset
        return ft

    prefix = " Select Model:  "
    suffix = "    ←→:选择  Enter:确认  Esc:取消"
    ft, new_offset = _build_horizontal_select(
        opts, panel.select_cursor, panel.select_scroll_offset,
        total_width, prefix, suffix,
    )
    panel.select_scroll_offset = new_offset
    return ft


def build_status_text(app: BlinkApp) -> FormattedText:
    if app._ide_selecting:
        return _build_ide_select_status(app)
    if app._config_selecting:
        return build_config_select_status(app)
    if app._pulling_paths:
        return FormattedText([("class:status-label", " 正在拉取...")])
    if app._review.branch_loading:
        return FormattedText([("class:status-label", " 正在获取分支列表...")])
    if app._review.selecting:
        total = len(app._review.branches)
        idx = app._review.branch_cursor + 1
        branch = app._review.branches[app._review.branch_cursor] if app._review.branches else ""
        return FormattedText([
            ("class:status-label", f" Review [{idx}/{total}]: "),
            ("class:status-accent", f"▸ {branch}"),
            ("class:status-dim", "    "),
            ("class:footer-dim", "←→:选择  Enter:确认  Esc:取消"),
        ])
    if app._review.reviewing_paths:
        stage_labels = {
            "collecting": "收集上下文...",
            "merging": "合并分支...",
            "reviewing": "AI 审查中...",
            "verifying": "验证发现...",
        }
        stage = app._review.review_stage
        label = stage_labels.get(stage, "正在 review...")
        return FormattedText([("class:status-label", f" 🔍 {label}")])
    if app._committing_paths:
        return FormattedText([("class:status-label", " 正在提交...")])
    if app._detail_panel is not None and app._detail_panel.is_editing:
        mode = app._detail_panel.edit_mode
        if mode == "alias" and app._detail_panel.alias_buffer:
            return FormattedText([
                ("class:status-label", " Alias: "),
                ("class:status-value", app._detail_panel.alias_buffer.text),
                ("", " "),
            ])
        if mode == "description" and app._detail_panel.desc_buffer:
            return FormattedText([
                ("class:status-label", " Desc: "),
                ("class:status-value", app._detail_panel.desc_buffer.text),
                ("", " "),
            ])
        if mode == "tags" and app._detail_panel.tag_buffer:
            return FormattedText([
                ("class:status-label", " Tag: "),
                ("class:status-value", app._detail_panel.tag_buffer.text),
                ("", " "),
            ])
    count = len(app._repo_control.repos)
    if app._search_filtering and app._search_bar.text:
        return FormattedText([
            ("class:status-accent", f" {count}"),
            ("class:status-label", f" result{'s' if count != 1 else ''} for "),
            ("class:status-value", app._search_bar.text),
        ])
    if app._scanning:
        return FormattedText([
            ("class:status-accent", " ⟳ "),
            ("class:status-label", "Scanning..."),
        ])
    if app._fetching_status:
        return FormattedText([
            ("class:status-accent", " ⟳ "),
            ("class:status-label", "Loading status…"),
        ])
    if app._scan_status:
        return FormattedText([("class:status-accent", f" {app._scan_status}")])
    repo = app._repo_control.selected_repo()
    if repo:
        if repo.description:
            return FormattedText([
                ("class:status-value", f" {repo.description}"),
                ("class:status-dim", f"  {repo.path}"),
            ])
        return FormattedText([("class:status-value", f" {repo.path}")])
    return FormattedText([])


def build_search_prefix_text(app: BlinkApp) -> FormattedText:
    if app._search_filtering and app._search_bar.text:
        return FormattedText([
            ("class:search-prefix", " / "),
            ("class:search-keyword", app._search_bar.text),
        ])
    return FormattedText([("class:search-prefix", " /")])


def build_footer_text(app: BlinkApp) -> FormattedText:
    if app._ctrl_c_quit_hint:
        return FormattedText([("class:status-accent", " Press Ctrl+C again to quit")])
    if app._search_active:
        return _styled_footer_hints([("Enter", "confirm"), ("Esc/Ctrl+C", "cancel")])
    if app._ide_selecting:
        return _styled_footer_hints([("←→", "选择"), ("Enter", "确认"), ("Esc", "取消")])
    if app._focus_pane == "config":
        return _styled_footer_hints([
            ("↑↓", "navigate"), ("Enter", "select"),
            ("e", "edit"), ("Esc", "back"),
        ])
    highlighted = time.monotonic() < app._footer_highlight_until
    style_key = "class:footer-key" if highlighted else "class:footer-dim-key"
    style_dim = "class:footer-highlight" if highlighted else "class:footer-dim"
    hints = [
        ("Enter", "ide"), ("/", "search"),
        ("Tab", "focus"),
        ("Shift+R", "rescan"),
        ("Shift+S", "config"),
    ]
    parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
    for i, (key, desc) in enumerate(hints):
        if i > 0:
            parts.append(("class:footer-dim", "  "))
        parts.append((style_key, key))
        parts.append((style_dim, f":{desc}"))
    return FormattedText(parts)


def _styled_footer_hints(hints: list[tuple[str, str]]) -> FormattedText:
    parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
    for i, (key, desc) in enumerate(hints):
        if i > 0:
            parts.append(("class:footer-dim", "  "))
        parts.append(("class:footer-key", key))
        parts.append(("class:footer-dim", f":{desc}"))
    return FormattedText(parts)
