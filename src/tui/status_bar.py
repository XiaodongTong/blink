from __future__ import annotations

import time
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import FormattedText

if TYPE_CHECKING:
    from blink.tui.app import BlinkApp


def build_status_text(app: BlinkApp) -> FormattedText:
    if app._ide_selecting:
        opts = app._ide_options()
        parts: list[tuple[str, str]] = [("class:status-label", " Select IDE:  ")]
        for i, (key, name) in enumerate(opts):
            if i > 0:
                parts.append(("class:status-dim", "  "))
            if i == app._ide_select_cursor:
                parts.append(("class:status-accent", f"▸ {name}"))
            else:
                parts.append(("class:status-dim", f"  {name}"))
        parts.append(("class:status-dim", "    "))
        parts.append(("class:footer-dim", "←→:选择  Enter:确认  Esc:取消"))
        return FormattedText(parts)
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
    highlighted = time.monotonic() < app._footer_highlight_until
    style_key = "class:footer-key" if highlighted else "class:footer-dim-key"
    style_dim = "class:footer-highlight" if highlighted else "class:footer-dim"
    hints = [
        ("Enter", "ide"), ("/", "search"),
        ("Tab", "focus"),
        ("Shift+R", "rescan"),
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
