from __future__ import annotations

import re
import shutil
import subprocess
import webbrowser
from typing import Callable, List, Optional

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.layout.controls import UIContent, UIControl

from blink.models import Repo, RepoStatus
from blink.store import Store
from blink.tui.actions import EditorInfo, copy_path, open_in_editor


def _remote_to_https(url: str) -> str | None:
    """Convert git remote URL to browser-openable HTTPS URL."""
    if url.startswith("https://"):
        return url.removesuffix(".git")
    m = re.match(r'(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?$', url)
    if m:
        host, path = m.groups()
        return f"https://{host}/{path}"
    return None


class DetailPanel(UIControl):
    LINE_IDE = 0
    LINE_FINDER = 1
    LINE_TLOOP = 2
    LINE_COMMIT = 3
    LINE_PULL = 4
    LINE_NAME = 5
    LINE_PATH = 6
    LINE_GIT = 7
    LINE_STATUS = 8
    LINE_PINNED = 9
    LINE_ALIAS = 10
    LINE_TAGS = 11
    LINE_DESC = 12
    MAX_LINE = 12

    def __init__(self, repo: Repo, store: Store, editors: dict[str, EditorInfo],
                 on_back: Callable[[], None], on_alias_change: Callable[[str], None],
                 on_tags_change: Callable[[], None],
                 on_status_message: Callable[[str], None] = lambda msg: None,
                 on_pin_change: Callable[[], None] = lambda: None,
                 on_open_ide: Callable[[], None] = lambda: None,
                 on_commit: Callable[[], None] = lambda: None,
                 on_pull: Callable[[], None] = lambda: None) -> None:
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

        self._cursor_index = 0
        self._edit_mode: str | None = None  # None | "alias" | "description" | "tags"
        self._alias_buffer: Optional[Buffer] = None
        self._desc_buffer: Optional[Buffer] = None
        self._tag_buffer: Optional[Buffer] = None

        self._editing_alias_before = False
        self._editing_desc_before = False

    def is_focusable(self) -> bool:
        return True

    # ── cursor navigation ──────────────────────────────────────────────────────

    def cursor_up(self) -> None:
        if self._edit_mode is None:
            self._cursor_index = max(0, self._cursor_index - 1)

    def cursor_down(self) -> None:
        if self._edit_mode is None:
            self._cursor_index = min(self.MAX_LINE, self._cursor_index + 1)

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
        if line == self.LINE_ALIAS:
            self._start_alias_edit()
        elif line == self.LINE_NAME:
            self._copy_name()
        elif line == self.LINE_PATH:
            self._copy_path()
        elif line == self.LINE_DESC:
            self._start_desc_edit()
        elif line == self.LINE_GIT:
            self._open_git_url()
        elif line == self.LINE_STATUS:
            self._copy_status()
        elif line == self.LINE_TAGS:
            self._start_tags_edit()
        elif line == self.LINE_PINNED:
            self._toggle_pin()
        elif line == self.LINE_IDE:
            self._on_open_ide()
        elif line == self.LINE_FINDER:
            open_in_editor(self._repo.path, "o", self._editors)
        elif line == self.LINE_TLOOP:
            self._run_tloop()
        elif line == self.LINE_COMMIT:
            self._run_commit()
        elif line == self.LINE_PULL:
            self._on_pull()
        return True

    # ── line-specific actions ────────────────────────────────────────────────

    def _copy_name(self) -> None:
        copy_path(self._repo.name)
        self._on_status_message(f"项目名称已复制: {self._repo.name}")

    def _copy_path(self) -> None:
        copy_path(self._repo.path)
        self._on_status_message(f"项目路径已复制: {self._repo.path}")

    def _git_display_url(self) -> str:
        if not self._repo.remotes:
            return "(none)"
        https = _remote_to_https(self._repo.remotes[0].url)
        return https or self._repo.remotes[0].url

    def _open_git_url(self) -> None:
        if not self._repo.remotes:
            return
        url = self._repo.remotes[0].url
        https = _remote_to_https(url)
        target = https or url
        webbrowser.open(target)
        self._on_status_message(f"已在浏览器打开: {target}")

    def _run_tloop(self) -> None:
        if not shutil.which("tloop"):
            self._on_status_message("未安装 tloop")
            return
        subprocess.Popen(
            ["tloop", "edit", self._repo.path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _run_commit(self) -> None:
        self._on_commit()

    def _start_alias_edit(self) -> None:
        self._edit_mode = "alias"
        self._alias_buffer = Buffer()
        self._alias_buffer.text = self._repo.alias or ""

    def _start_desc_edit(self) -> None:
        self._edit_mode = "description"
        self._desc_buffer = Buffer()
        self._desc_buffer.text = self._repo.description or ""

    def _start_tags_edit(self) -> None:
        self._edit_mode = "tags"
        self._tag_buffer = Buffer()

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

    def _copy_status(self) -> None:
        text = self._status_display()
        copy_path(text)
        self._on_status_message(f"状态已复制: {text}")

    def _toggle_pin(self) -> None:
        if self._repo.id is not None:
            new_val = self._store.toggle_pin(self._repo.id)
            self._repo.pinned = new_val
            self._on_pin_change()
            status = "已置顶" if new_val else "已取消置顶"
            self._on_status_message(status)

    # ── edit mode management ─────────────────────────────────────────────────

    def _confirm_alias(self, alias: str) -> None:
        if self._repo.id is not None:
            self._store.set_alias(self._repo.id, alias)
            self._repo.alias = alias
            self._on_alias_change(alias)
        self._edit_mode = None
        self._alias_buffer = None

    def _confirm_description(self, desc: str) -> None:
        if self._repo.id is not None:
            self._store.set_description(self._repo.id, desc)
            self._repo.description = desc
        self._edit_mode = None
        self._desc_buffer = None

    def confirm_alias(self, alias: str) -> None:
        self._confirm_alias(alias)

    def handle_key(self, key: str) -> bool:
        """Handle keys when in tag edit mode (Shift+1-9 for removal)."""
        if self._edit_mode == "tags" and key in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            idx = int(key) - 1
            if idx < len(self._repo.tags) and self._repo.id is not None:
                tag = self._repo.tags[idx]
                self._store.remove_tag(self._repo.id, tag)
                self._repo.tags = self._store.get_tags_for_repo(self._repo.id)
                self._on_tags_change()
            return True
        return False

    def route_printable(self, char: str) -> None:
        if self._edit_mode == "alias" and self._alias_buffer:
            self._alias_buffer.text += char
        elif self._edit_mode == "description" and self._desc_buffer:
            self._desc_buffer.text += char
        elif self._edit_mode == "tags" and self._tag_buffer:
            self._tag_buffer.text += char

    def route_backspace(self) -> None:
        if self._edit_mode == "alias" and self._alias_buffer:
            self._alias_buffer.text = self._alias_buffer.text[:-1]
        elif self._edit_mode == "description" and self._desc_buffer:
            self._desc_buffer.text = self._desc_buffer.text[:-1]
        elif self._edit_mode == "tags" and self._tag_buffer:
            self._tag_buffer.text = self._tag_buffer.text[:-1]

    @property
    def is_editing(self) -> bool:
        return self._edit_mode is not None

    @property
    def edit_mode(self) -> str | None:
        return self._edit_mode

    @property
    def alias_buffer(self) -> Optional[Buffer]:
        return self._alias_buffer

    @property
    def desc_buffer(self) -> Optional[Buffer]:
        return self._desc_buffer

    @property
    def tag_buffer(self) -> Optional[Buffer]:
        return self._tag_buffer

    # ── rendering ────────────────────────────────────────────────────────────

    def _build_one_line(self, label: str, value: str, selected: bool, width: int = 0) -> List[tuple[str, str]]:
        """Render a single label+value line, optionally selected with full-width background."""
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

    def _build_lines(self, width: int) -> List[List[tuple[str, str]]]:
        cur = self._cursor_index
        edit = self._edit_mode

        lines: List[List[tuple[str, str]]] = []

        # Row 0: IDE
        lines.append(self._build_one_line("", "Open with IDE", cur == self.LINE_IDE, width))

        # Row 1: Finder
        lines.append(self._build_one_line("", "Open with Finder", cur == self.LINE_FINDER, width))

        # Row 2: Tloop
        lines.append(self._build_one_line("", "Add Todo Loop Task", cur == self.LINE_TLOOP, width))

        # Row 3: Commit
        lines.append(self._build_one_line("", "Commit Changes", cur == self.LINE_COMMIT, width))

        # Row 4: Pull
        lines.append(self._build_one_line("", "Pull Latest", cur == self.LINE_PULL, width))

        # Separator
        lines.append([("class:detail-sep", "─" * width)])
        # Row 5: Name
        lines.append(self._build_one_line("Name      ", self._repo.name, cur == self.LINE_NAME, width))
        # Row 6: Path
        lines.append(self._build_one_line("Path      ", self._repo.path, cur == self.LINE_PATH, width))

        # Row 7: Git
        lines.append(self._build_one_line("Git       ", self._git_display_url(), cur == self.LINE_GIT, width))

        

        # Separator
        lines.append([("class:detail-sep", "─" * width)])

        # Row 8: Status
        is_status_sel = cur == self.LINE_STATUS
        status_fragments: List[tuple[str, str]] = [
            ("class:detail-indicator" if is_status_sel else "class:dim",
             "  ▸ " if is_status_sel else "    "),
            ("class:detail-label-sel" if is_status_sel else "class:label", "Status    "),
        ]
        status_fragments.extend(self._format_status_value(is_status_sel))
        if is_status_sel and width > 0:
            line_len = sum(len(t) for _, t in status_fragments)
            if line_len < width:
                status_fragments.append(("class:detail-selected", " " * (width - line_len)))
        lines.append(status_fragments)

        # Row 9: Pinned
        pin_str = "Yes" if self._repo.pinned else "No"
        lines.append(self._build_one_line("Pinned    ", pin_str, cur == self.LINE_PINNED, width))

        # Row 10: Alias
        lines.append(self._build_one_line("Alias     ", self._repo.alias or "(none)", cur == self.LINE_ALIAS, width))

        # Row 11: Tags
        tag_str = " ".join(f"[{t}]" for t in self._repo.tags) if self._repo.tags else "(none)"
        lines.append(self._build_one_line("Tags      ", tag_str, cur == self.LINE_TAGS, width))

        # Row 12: Description
        lines.append(self._build_one_line("Desc      ", self._repo.description or "(none)", cur == self.LINE_DESC, width))

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

    def _formatted_text(self, width: int = 80) -> FormattedText:
        """Flatten all lines into a single FormattedText (for testing)."""
        parts: List[tuple[str, str]] = []
        for line in self._build_lines(width):
            parts.extend(line)
            parts.append(("", "\n"))
        return FormattedText(parts)
