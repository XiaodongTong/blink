from __future__ import annotations

from typing import List, Optional

from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import AnyFormattedText, FormattedText
from prompt_toolkit.layout.containers import ScrollOffsets
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.layout import Window

from blink.models import Repo, RepoStatus, display_width
from blink.tui.icons import get_icon, BRANCH_NF, BRANCH_ASCII, PIN_NF, PIN_ASCII


class RepoListControl(UIControl):
    def __init__(self, nerd_fonts: bool = False) -> None:
        self.repos: List[Repo] = []
        self.selected_index: int = 0
        self.error_repo_ids: set[int] = set()
        self.nerd_fonts: bool = nerd_fonts

    def is_focusable(self) -> bool:
        return True

    def set_repos(self, repos: List[Repo], reset_selection: bool = True) -> None:
        self.repos = repos
        if reset_selection:
            self.selected_index = 0
        elif self.selected_index >= len(repos):
            self.selected_index = max(0, len(repos) - 1)

    def selected_repo(self) -> Repo | None:
        if 0 <= self.selected_index < len(self.repos):
            return self.repos[self.selected_index]
        return None

    def move_up(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1

    def move_down(self) -> None:
        if self.selected_index < len(self.repos) - 1:
            self.selected_index += 1

    def preferred_width(self, max_available_width: int) -> int | None:
        return max_available_width

    def preferred_height(self, width: int, max_available_height: int, wrap_lines: bool, get_line_prefix) -> int | None:
        return max(len(self.repos) * 2, 1)

    def _format_status_badge(self, status: Optional[RepoStatus], is_error: bool = False,
                             selected: bool = False) -> list[tuple[str, str]]:
        sel = "-sel" if selected else ""
        if is_error:
            return [("class:status-loading" + sel, " ⚠")]
        if status is None:
            return [("class:status-loading" + sel, " ···")]
        parts: list[tuple[str, str]] = []
        branch = status.branch or "HEAD"
        branch_icon = get_icon(self.nerd_fonts, BRANCH_NF, BRANCH_ASCII)
        branch_prefix = f" {branch_icon}" if branch_icon else " "
        parts.append(("class:status-clean" + sel, f"{branch_prefix}{branch}"))
        if status.dirty_count > 0:
            parts.append(("class:status-dirty" + sel, f" ○ +{status.dirty_count}"))
        else:
            parts.append(("class:status-clean" + sel, " ●"))
        if status.ahead > 0 and status.behind > 0:
            parts.append(("class:status-ahead-behind" + sel, f" ↑{status.ahead} ↓{status.behind}"))
        elif status.ahead > 0:
            parts.append(("class:status-ahead-behind" + sel, f" ↑{status.ahead}"))
        elif status.behind > 0:
            parts.append(("class:status-ahead-behind" + sel, f" ↓{status.behind}"))
        return parts

    def _badge_display_width(self, badge: list[tuple[str, str]]) -> int:
        return sum(display_width(t) for _, t in badge)

    def _render_repo(self, repo: Repo, selected: bool, width: int = 0) -> List[AnyFormattedText]:
        if selected:
            ind_s = "class:indicator"
            name_s = "class:repo-selected"
            alias_s = "class:selected-dim"
            path_s = "class:selected-dim"
            tag_s = "class:selected-tag"
            tag_b = "class:selected-tag-bracket"
            pin_s = "class:indicator"
        else:
            ind_s = "class:dim"
            name_s = "class:repo-name"
            alias_s = "class:alias"
            path_s = "class:repo-path-dim"
            tag_s = "class:tag"
            tag_b = "class:tag-bracket"
            pin_s = "class:tag"

        line1: list[tuple[str, str]] = [(ind_s, " ▸ " if selected else "   ")]
        if repo.pinned:
            pin_char = get_icon(self.nerd_fonts, PIN_NF, PIN_ASCII)
            line1.append((pin_s, pin_char))
        if repo.alias:
            line1.append((name_s, repo.name))
            line1.append((alias_s, f" ({repo.alias})"))
        else:
            line1.append((name_s, repo.name))

        for tag in repo.tags:
            line1.append((tag_b, " ["))
            line1.append((tag_s, tag))
            line1.append((tag_b, "]"))

        line2: list[tuple[str, str]] = [(path_s, f"     {repo.path}")]

        is_error = repo.id is not None and repo.id in self.error_repo_ids
        badge = self._format_status_badge(repo.status, is_error, selected=selected)

        if width > 0:
            pad_s = "class:selected-dim" if selected else "class:repo-path-dim"
            path_text = f"     {repo.path}"
            badge_w = self._badge_display_width(badge)
            path_w = display_width(path_text)
            available = width - path_w - badge_w
            if available > 0:
                line2.append((pad_s, " " * available))
            line2.extend(badge)

            if selected:
                line1_len = sum(len(t) for _, t in line1)
                if line1_len < width:
                    line1.append(("class:selected-dim", " " * (width - line1_len)))

        return [line1, line2]

    def create_content(self, width: int, height: int) -> UIContent:
        lines: list[list[tuple[str, str]]] = []
        for i, repo in enumerate(self.repos):
            rendered = self._render_repo(repo, i == self.selected_index, width)
            lines.extend(rendered)

        if not lines:
            lines.append([("class:empty", "  No repositories found.")])
            lines.append([("class:dim", "")])

        def get_line(i: int):
            if 0 <= i < len(lines):
                return FormattedText(lines[i])
            return FormattedText([("class:normal", "")])

        return UIContent(
            get_line=get_line,
            line_count=max(len(lines), height if height > 0 else 1),
            show_cursor=False,
            cursor_position=Point(x=0, y=self.selected_index * 2),
        )


class RepoListWindow(Window):
    def __init__(self, control: RepoListControl) -> None:
        self.control = control
        super().__init__(
            content=control,
            height=D(min=1),
            style="class:repo-list",
            scroll_offsets=ScrollOffsets(bottom=1),
        )