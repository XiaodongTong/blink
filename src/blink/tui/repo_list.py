from __future__ import annotations

from typing import List

from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import AnyFormattedText, FormattedText
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.layout.layout import Window

from blink.models import Repo


class RepoListControl(UIControl):
    def __init__(self) -> None:
        self.repos: List[Repo] = []
        self.selected_index: int = 0

    def set_repos(self, repos: List[Repo]) -> None:
        self.repos = repos
        self.selected_index = 0

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

    def _render_repo(self, repo: Repo, selected: bool, width: int = 0) -> List[AnyFormattedText]:
        if selected:
            ind_s = "class:indicator"
            name_s = "class:repo-selected"
            alias_s = "class:selected-dim"
            path_s = "class:selected-dim"
            tag_s = "class:selected-tag"
            tag_b = "class:selected-tag-bracket"
        else:
            ind_s = "class:dim"
            name_s = "class:normal"
            alias_s = "class:alias"
            path_s = "class:path"
            tag_s = "class:tag"
            tag_b = "class:tag-bracket"

        line1: list[tuple[str, str]] = [(ind_s, " ▸ " if selected else "   ")]
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

        if selected and width > 0:
            pad_s = "class:selected-dim"
            line1_len = sum(len(t) for _, t in line1)
            if line1_len < width:
                line1.append((pad_s, " " * (width - line1_len)))
            line2_len = sum(len(t) for _, t in line2)
            if line2_len < width:
                line2.append((pad_s, " " * (width - line2_len)))

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
            cursor_position=Point(x=0, y=self.selected_index * 2 + 1),
        )


class RepoListWindow(Window):
    def __init__(self, control: RepoListControl) -> None:
        self.control = control
        super().__init__(
            content=control,
            height=D(min=1),
            style="class:repo-list",
        )