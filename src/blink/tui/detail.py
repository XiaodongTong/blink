from __future__ import annotations

from typing import Callable, List, Optional

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText

from blink.models import Repo
from blink.store import Store
from blink.tui.actions import EditorInfo


class DetailPanel:
    def __init__(self, repo: Repo, store: Store, editors: dict[str, EditorInfo],
                 on_back: Callable[[], None], on_alias_change: Callable[[str], None],
                 on_tags_change: Callable[[], None]) -> None:
        self._repo = repo
        self._store = store
        self._editors = editors
        self._on_back = on_back
        self._on_alias_change = on_alias_change
        self._on_tags_change = on_tags_change
        self._editing_alias = False
        self._alias_buffer: Optional[Buffer] = None
        self._tag_adding = False
        self._tag_buffer: Optional[Buffer] = None

    def _formatted_text(self) -> FormattedText:
        if self._tag_adding:
            tag_input = self._tag_buffer.text if self._tag_buffer else ""
            return self._tag_popover_text(tag_input)

        parts: List[tuple[str, str]] = []

        # Alias
        if self._editing_alias and self._alias_buffer:
            alias_val = self._alias_buffer.text
        else:
            alias_val = self._repo.alias if self._repo.alias else "(none)"
        parts.append(("class:label", "  Alias     "))
        parts.append(("class:normal", f"{alias_val}\n"))

        # Name
        parts.append(("class:label", "  Name      "))
        parts.append(("class:normal", f"{self._repo.name}\n"))

        # Path
        parts.append(("class:label", "  Path      "))
        parts.append(("class:dim", f"{self._repo.path}\n"))

        if self._repo.description:
            parts.append(("class:label", "  Desc      "))
            parts.append(("class:normal", f"{self._repo.description}\n"))

        # Separator
        parts.append(("class:detail-sep", "\n"))

        # Remotes
        if self._repo.remotes:
            parts.append(("class:label", "  Remotes\n"))
            for rm in self._repo.remotes:
                parts.append(("class:dim", "    ○ "))
                parts.append(("class:normal", f"{rm.name}"))
                parts.append(("class:dim", " → "))
                parts.append(("class:dim", f"{rm.url}\n"))
        else:
            parts.append(("class:label", "  Remotes   "))
            parts.append(("class:dim", "(none)\n"))

        # Tags
        parts.append(("class:label", "  Tags      "))
        if self._repo.tags:
            for tag in self._repo.tags:
                parts.append(("class:detail-tag-bracket", "["))
                parts.append(("class:detail-tag", tag))
                parts.append(("class:detail-tag-bracket", "] "))
        else:
            parts.append(("class:dim", "(none)"))
        parts.append(("", "\n"))

        # Separator
        parts.append(("class:detail-sep", "\n"))

        # Last scanned
        parts.append(("class:label", "  Scanned   "))
        parts.append(("class:dim", f"{self._repo.last_synced}\n"))

        # Actions
        parts.append(("class:detail-sep", "\n"))
        parts.append(("class:dim", "  Actions: "))
        parts.append(("class:normal", "e:edit alias  t:manage tags  "))
        parts.append(("class:normal", "v:VSCode  u:Cursor  a:Antigrav  o:open  "))
        parts.append(("class:normal", "y:copy path\n"))
        parts.append(("class:dim", "  [Esc] back to list"))
        return FormattedText(parts)

    def _tag_popover_text(self, add_input: str) -> FormattedText:
        parts: List[tuple[str, str]] = []
        parts.append(("class:label", "  Tag Management\n"))
        parts.append(("class:normal", "  Current tags "))
        if self._repo.tags:
            for tag in self._repo.tags:
                parts.append(("class:detail-tag-bracket", "["))
                parts.append(("class:detail-tag", tag))
                parts.append(("class:detail-tag-bracket", "] "))
        else:
            parts.append(("class:dim", "(none)"))
        parts.append(("", "\n"))
        if self._repo.tags:
            parts.append(("class:dim", "  [number] remove tag\n"))
            for i, tag in enumerate(self._repo.tags):
                parts.append(("class:dim", f"    "))
                parts.append(("class:label", f"{i+1}"))
                parts.append(("class:dim", f": {tag}\n"))
        parts.append(("class:label", "\n  Add tag "))
        parts.append(("class:status-value", add_input))
        parts.append(("class:dim", "  (Enter to add, Esc to close)\n"))
        return FormattedText(parts)

    def handle_key(self, key: str) -> bool:
        if key == "escape":
            if self._editing_alias:
                self._editing_alias = False
                return True
            if self._tag_adding:
                self._tag_adding = False
                return True
            self._on_back()
            return True
        if key == "enter" and self._tag_adding and self._tag_buffer:
            tag = self._tag_buffer.text.strip()
            if tag and self._repo.id is not None:
                self._store.add_tag(self._repo.id, tag)
                self._repo.tags = self._store.get_tags_for_repo(self._repo.id)
                self._on_tags_change()
            self._tag_adding = False
            self._tag_buffer = None
            return True
        if key in ("1", "2", "3", "4", "5", "6", "7", "8", "9") and self._tag_adding and self._repo.id is not None:
            idx = int(key) - 1
            if idx < len(self._repo.tags):
                tag = self._repo.tags[idx]
                self._store.remove_tag(self._repo.id, tag)
                self._repo.tags = self._store.get_tags_for_repo(self._repo.id)
                self._on_tags_change()
            return True
        return False

    def handle_alias_edit(self) -> bool:
        self._editing_alias = True
        self._alias_buffer = Buffer()
        self._alias_buffer.text = self._repo.alias if self._repo.alias else ""
        return True

    def handle_tag_edit(self) -> bool:
        self._tag_adding = True
        self._tag_buffer = Buffer()
        return True

    @property
    def is_editing_alias(self) -> bool:
        return self._editing_alias

    @property
    def alias_buffer(self) -> Optional[Buffer]:
        return self._alias_buffer

    @property
    def is_adding_tag(self) -> bool:
        return self._tag_adding

    @property
    def tag_buffer(self) -> Optional[Buffer]:
        return self._tag_buffer

    def confirm_alias(self, alias: str) -> None:
        if self._repo.id is not None:
            self._store.set_alias(self._repo.id, alias)
            self._repo.alias = alias
            self._on_alias_change(alias)
        self._editing_alias = False
