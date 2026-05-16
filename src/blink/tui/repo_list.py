from __future__ import annotations

from typing import List

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

    def _tag_text(self, tags: List[str]) -> str:
        if tags:
            return "  [" + ", ".join(tags) + "]"
        return ""

    def _render_repo(self, repo: Repo, selected: bool) -> List[AnyFormattedText]:
        tag_text = self._tag_text(repo.tags)
        line1 = f"  {repo.display_name}{tag_text}"
        line2 = f"  {repo.path}"
        if selected:
            return [
                [("class:selected", line1)],
                [("class:selected-dim", line2)],
            ]
        return [
            [("class:normal", line1)],
            [("class:dim", line2)],
        ]

    def create_content(self, width: int, height: int) -> UIContent:
        lines: list[list[tuple[str, str]]] = []
        for i, repo in enumerate(self.repos):
            rendered = self._render_repo(repo, i == self.selected_index)
            lines.extend(rendered)

        if not lines:
            lines.append([("class:normal", "  No repositories found.")])
            lines.append([("class:dim", "")])

        def get_line(i: int):
            if 0 <= i < len(lines):
                return FormattedText(lines[i])
            return FormattedText([("class:normal", "")])

        return UIContent(
            get_line=get_line,
            line_count=max(len(lines), height if height > 0 else 1),
            show_cursor=False,
        )


class RepoListWindow(Window):
    def __init__(self, control: RepoListControl) -> None:
        self.control = control
        super().__init__(
            content=control,
            height=D(min=1),
            style="class:repo-list",
        )