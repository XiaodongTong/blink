from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Optional, Tuple

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType

_FocusedChecker = Callable[[], bool]

from blink.models import Repo, RepoStatus, display_width
from blink.store import Store
from blink.tui.actions import EditorInfo
from blink.tui.detail_edit import DetailEditMixin

_INDENT = "            "  # 12 spaces (aligns with value column)


def _remote_to_https(url: str) -> str | None:
    if url.startswith("https://"):
        return url.removesuffix(".git")
    m = re.match(r'(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?$', url)
    if m:
        host, path = m.groups()
        return f"https://{host}/{path}"
    return None


class DetailPanel(DetailEditMixin, UIControl):
    _ACTION_GROUPS: list[list[tuple[str, str]]] = [
        [
            ("Terminal  ", "Open in Terminal"),
            ("IDE       ", "Open with IDE"),
            ("Finder    ", "Open in Finder"),
        ],
        [
            ("Git       ", "Open in Browser"),
            ("Commit    ", "Auto Commit Changes"),
            ("Pull      ", "Pull Changes"),
        ],
        [
            ("Task      ", "Add todo task"),
            ("Review    ", "AI Code Review"),
        ],
    ]

    _ACTION_SHORTCUTS: dict[int, str] = {
        0: "Shift+1", 1: "Shift+2", 2: "Shift+3",
        3: "Shift+4", 4: "Shift+5", 5: "Shift+6",
        6: "Shift+7", 7: "Shift+8",
    }

    def __init__(self, repo: Repo, store: Store, editors: dict[str, EditorInfo],
                 on_back: Callable[[], None], on_alias_change: Callable[[str], None],
                 on_tags_change: Callable[[], None],
                 is_focused: _FocusedChecker = lambda: False,
                 on_status_message: Callable[[str], None] = lambda msg: None,
                 on_pin_change: Callable[[], None] = lambda: None,
                 on_open_ide: Callable[[], None] = lambda: None,
                 on_commit: Callable[[], None] = lambda: None,
                 on_pull: Callable[[], None] = lambda: None,
                 on_action: Callable[[], None] = lambda: None,
                 on_open_finder: Callable[[], None] = lambda: None,
                 on_open_git: Callable[[], None] = lambda: None,
                 on_add_task: Callable[[], None] = lambda: None,
                 on_review: Callable[[], None] = lambda: None,
                 on_open_terminal: Callable[[], None] = lambda: None,
                 on_copy_path: Callable[[], None] = lambda: None,
                 on_open_report: Callable[[], None] = lambda: None,
                 last_report_paths: dict[str, str] | None = None) -> None:
        self._repo = repo
        self._store = store
        self._editors = editors
        self._on_back = on_back
        self._on_alias_change = on_alias_change
        self._on_tags_change = on_tags_change
        self._on_status_message = on_status_message
        self._on_pin_change = on_pin_change
        self._on_open_ide = on_open_ide
        self._on_commit = on_commit
        self._on_pull = on_pull
        self._on_action = on_action
        self._on_open_finder = on_open_finder
        self._on_open_git = on_open_git
        self._on_add_task = on_add_task
        self._on_review = on_review
        self._on_open_terminal = on_open_terminal
        self._on_copy_path = on_copy_path
        self._on_open_report = on_open_report
        self._last_report_paths = last_report_paths or {}

        self._cursor_index = 0
        self._is_focused = is_focused
        self._edit_mode: str | None = None
        self._alias_buffer: Optional[Buffer] = None
        self._desc_buffer: Optional[Buffer] = None
        self._tag_buffer: Optional[Buffer] = None
        self._path_line_range: Tuple[int, int] = (0, 0)
        self._repo_line_range: Tuple[int, int] = (0, 0)

    def set_repo(self, repo: Repo) -> None:
        same_repo = self._repo is not None and self._repo.path == repo.path
        self._repo = repo
        if not same_repo:
            self._cursor_index = 0
            self._edit_mode = None
            self._alias_buffer = None
            self._desc_buffer = None
            self._tag_buffer = None

    @property
    def focused(self) -> bool:
        return self._is_focused()

    def is_focusable(self) -> bool:
        return True

    # ── cursor navigation ──────────────────────────────────────────────────────

    def _navigable_actions(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for group in self._ACTION_GROUPS:
            items.extend(group)
        if self._has_review_report():
            items.append(("Report    ", "View Review Report"))
        return items

    def _has_review_report(self) -> bool:
        return self._repo.path in self._last_report_paths

    @property
    def _max_cursor(self) -> int:
        return len(self._navigable_actions()) + 3

    def _group_starts(self) -> list[int]:
        starts: list[int] = []
        offset = 0
        for group in self._ACTION_GROUPS:
            starts.append(offset)
            offset += len(group)
        starts.append(len(self._navigable_actions()))
        return starts

    def _current_group(self) -> int:
        starts = self._group_starts()
        for i in range(len(starts) - 1, -1, -1):
            if starts[i] <= self._cursor_index:
                return i
        return 0

    def cursor_up(self) -> None:
        if self._edit_mode is None:
            self._cursor_index = max(0, self._cursor_index - 1)

    def cursor_down(self) -> None:
        if self._edit_mode is None:
            self._cursor_index = min(self._max_cursor, self._cursor_index + 1)

    def cursor_group_down(self) -> None:
        if self._edit_mode is not None:
            return
        starts = self._group_starts()
        group = self._current_group()
        if group + 1 < len(starts):
            self._cursor_index = starts[group + 1]

    def cursor_group_up(self) -> None:
        if self._edit_mode is not None:
            return
        starts = self._group_starts()
        group = self._current_group()
        if group > 0:
            self._cursor_index = starts[group - 1]

    # ── enter handler ─────────────────────────────────────────────────────────

    def handle_enter(self) -> bool:
        if self._edit_mode == "alias":
            alias = self._alias_buffer.text.strip() if self._alias_buffer else ""
            self._confirm_alias(alias)
            return True
        if self._edit_mode == "description":
            desc = self._desc_buffer.text.strip() if self._desc_buffer else ""
            self._confirm_description(desc)
            return True
        if self._edit_mode == "tags":
            tag = self._tag_buffer.text.strip() if self._tag_buffer else ""
            if tag and self._repo.id is not None:
                self._store.add_tag(self._repo.id, tag)
                self._repo.tags = self._store.get_tags_for_repo(self._repo.id)
                self._on_tags_change()
            self._tag_buffer = Buffer()
            return True

        line = self._cursor_index
        n_actions = len(self._navigable_actions())
        if line < n_actions:
            dispatch = [
                self._on_open_terminal,
                self._on_open_ide,
                self._on_open_finder,
                self._on_open_git,
                self._on_commit,
                self._on_pull,
                self._on_add_task,
                self._on_review,
            ]
            if line < len(dispatch):
                dispatch[line]()
            elif line == len(dispatch) and self._has_review_report():
                self._on_open_report()
        else:
            marker_idx = line - n_actions
            if marker_idx == 0:
                self._toggle_pin()
                self._on_action()
            elif marker_idx == 1:
                self._start_alias_edit()
                self._on_action()
            elif marker_idx == 2:
                self._start_tags_edit()
                self._on_action()
            elif marker_idx == 3:
                self._start_desc_edit()
                self._on_action()
        return True

    # ── line-specific actions ────────────────────────────────────────────────

    def _git_display_url(self) -> str:
        if not self._repo.remotes:
            return "(none)"
        https = _remote_to_https(self._repo.remotes[0].url)
        return https or self._repo.remotes[0].url

    def _format_status_value(self, selected: bool) -> List[tuple[str, str]]:
        sel = "-sel" if selected else ""
        status = self._repo.status
        if status is None:
            return [("class:status-loading" + sel, "···")]
        fragments: List[tuple[str, str]] = []
        branch = status.branch or "HEAD"
        fragments.append(("class:status-clean" + sel, branch))
        if status.dirty_count > 0:
            fragments.append(("class:status-dirty" + sel, f" ○ +{status.dirty_count}"))
        else:
            fragments.append(("class:status-clean" + sel, " ●"))
        if status.ahead > 0 and status.behind > 0:
            fragments.append(("class:status-ahead-behind" + sel, f" ↑{status.ahead} ↓{status.behind}"))
        elif status.ahead > 0:
            fragments.append(("class:status-ahead-behind" + sel, f" ↑{status.ahead}"))
        elif status.behind > 0:
            fragments.append(("class:status-ahead-behind" + sel, f" ↓{status.behind}"))
        return fragments

    def _status_display(self) -> str:
        status = self._repo.status
        if status is None:
            return "···"
        branch = status.branch or "HEAD"
        parts = [branch]
        if status.dirty_count > 0:
            parts.append(f"○ +{status.dirty_count}")
        else:
            parts.append("●")
        if status.ahead > 0:
            parts.append(f"↑{status.ahead}")
        if status.behind > 0:
            parts.append(f"↓{status.behind}")
        return " ".join(parts)

    def _toggle_pin(self) -> None:
        if self._repo.id is not None:
            new_val = self._store.toggle_pin(self._repo.id)
            self._repo.pinned = new_val
            self._on_pin_change()
            status = "已置顶" if new_val else "已取消置顶"
            self._on_status_message(status)

    # ── rendering ────────────────────────────────────────────────────────────

    @staticmethod
    def _wrap_value(value: str, max_width: int) -> List[str]:
        if max_width <= 0 or display_width(value) <= max_width:
            return [value] if value else ["(none)"]
        chunks: List[str] = []
        current = ""
        current_w = 0
        for ch in value:
            cw = 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
            if current_w + cw > max_width and current:
                chunks.append(current)
                current = ch
                current_w = cw
            else:
                current += ch
                current_w += cw
        if current:
            chunks.append(current)
        return chunks

    def _build_info_lines(self, label: str, value: str, width: int, *, clickable: bool = False) -> List[List[tuple[str, str]]]:
        prefix_len = 4 + display_width(label)
        max_val_w = width - prefix_len
        chunks = self._wrap_value(value, max_val_w)
        val_cls = "detail-clickable" if clickable else "normal"
        result: List[List[tuple[str, str]]] = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                result.append([
                    ("class:dim", "    "),
                    ("class:label", label),
                    ("class:" + val_cls, chunk),
                ])
            else:
                result.append([
                    ("class:dim", _INDENT),
                    ("class:" + val_cls, chunk),
                ])
        return result

    def _build_marker_line(self, label: str, value: str, selected: bool, width: int = 0) -> List[tuple[str, str]]:
        cls = "detail-selected" if selected else "normal"
        lbl = "detail-label-sel" if selected else "label"
        pad_cls = "detail-selected"
        fragments: List[tuple[str, str]] = [
            ("class:detail-indicator" if selected else "class:dim", "  ▸ " if selected else "    "),
            ("class:" + lbl, label),
            ("class:" + cls, value),
        ]
        if selected and width > 0:
            line_len = sum(len(t) for _, t in fragments)
            if line_len < width:
                fragments.append(("class:" + pad_cls, " " * (width - line_len)))
        return fragments

    def _build_action_line(self, label: str, desc: str, selected: bool, width: int = 0, *, index: int = 0, max_desc_len: int = 16) -> List[tuple[str, str]]:
        shortcut = self._ACTION_SHORTCUTS.get(index, "")
        if selected:
            fragments: List[tuple[str, str]] = [
                ("class:detail-indicator", "  ▸ "),
                ("class:detail-label-sel", label),
                ("class:detail-selected", desc),
                ("class:detail-selected", " " * (max_desc_len - len(desc) + 1)),
                ("class:detail-selected", "[Enter]"),
            ]
            line_len = sum(len(t) for _, t in fragments)
            if line_len < width:
                fragments.append(("class:detail-selected", " " * (width - line_len)))
        else:
            fragments = [
                ("class:dim", "    "),
                ("class:label", label),
                ("class:normal", desc),
            ]
            if shortcut:
                fragments.append(("class:normal", " " * (max_desc_len - len(desc))))
                fragments.append(("class:normal", " "))
                fragments.append(("class:detail-shortcut-dim", f"[{shortcut}]"))
        return fragments

    def _build_lines(self, width: int) -> List[List[tuple[str, str]]]:
        cur = self._cursor_index

        lines: List[List[tuple[str, str]]] = []

        # ── Metadata section (read-only, no cursor) ──
        lines.extend(self._build_info_lines("Name      ", self._repo.name, width))
        path_start = len(lines)
        lines.extend(self._build_info_lines("Path      ", self._repo.path, width, clickable=True))
        self._path_line_range = (path_start, len(lines) - 1)
        repo_start = len(lines)
        lines.extend(self._build_info_lines("Repo      ", self._git_display_url(), width, clickable=True))
        self._repo_line_range = (repo_start, len(lines) - 1)

        # Status row (styled, but not cursor-navigable)
        status_fragments: List[tuple[str, str]] = [
            ("class:dim", "    "),
            ("class:label", "Status    "),
        ]
        status_fragments.extend(self._format_status_value(False))
        lines.append(status_fragments)

        # Separator
        lines.append([("class:detail-sep", "─" * width)])

        # ── Actions section with group dividers ──
        actions = self._navigable_actions()
        max_desc_len = max((len(d) for _, d in actions), default=0)
        action_idx = 0
        for g, group in enumerate(self._ACTION_GROUPS):
            if g > 0:
                lines.append([("class:detail-sep", "─" * width)])
            for label, desc in group:
                is_sel = (cur == action_idx) and self._is_focused()
                lines.append(self._build_action_line(label, desc, is_sel, width, index=action_idx, max_desc_len=max_desc_len))
                action_idx += 1
        if self._has_review_report():
            is_sel = (cur == action_idx) and self._is_focused()
            lines.append(self._build_action_line("Report    ", "View Review Report", is_sel, width, index=action_idx, max_desc_len=max_desc_len))

        n_actions = len(actions)

        # Separator
        lines.append([("class:detail-sep", "─" * width)])

        # ── Local Markers section ──
        pin_str = "Yes" if self._repo.pinned else "No"
        lines.append(self._build_marker_line("Pinned    ", pin_str, cur == n_actions and self._is_focused(), width))
        lines.append(self._build_marker_line("Alias     ", self._repo.alias or "(none)", cur == n_actions + 1 and self._is_focused(), width))
        tag_str = " ".join(f"[{t}]" for t in self._repo.tags) if self._repo.tags else "(none)"
        lines.append(self._build_marker_line("Tags      ", tag_str, cur == n_actions + 2 and self._is_focused(), width))
        lines.append(self._build_marker_line("Desc      ", self._repo.description or "(none)", cur == n_actions + 3 and self._is_focused(), width))

        return lines

    def create_content(self, width: int, height: int) -> UIContent:
        rendered = self._build_lines(width)

        def get_line(i: int):
            if 0 <= i < len(rendered):
                return FormattedText(rendered[i])
            return FormattedText([("class:normal", "")])

        return UIContent(
            get_line=get_line,
            line_count=len(rendered),
            show_cursor=False,
        )

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
            y = mouse_event.position.y
            ps, pe = self._path_line_range
            if ps <= y <= pe:
                self._on_copy_path()
                return None
            rs, re_ = self._repo_line_range
            if rs <= y <= re_:
                self._on_open_git()
                return None
        return NotImplemented

    def _formatted_text(self, width: int = 80) -> FormattedText:
        parts: List[tuple[str, str]] = []
        for line in self._build_lines(width):
            parts.extend(line)
            parts.append(("", "\n"))
        return FormattedText(parts)
