"""Detail panel edit mode mixin — alias/description/tags input handling."""

from __future__ import annotations

from typing import Callable, Optional

from prompt_toolkit.buffer import Buffer

from blink.models import Repo
from blink.store import Store


class DetailEditMixin:
    _edit_mode: str | None
    _alias_buffer: Optional[Buffer]
    _desc_buffer: Optional[Buffer]
    _tag_buffer: Optional[Buffer]
    _repo: Repo
    _store: Store
    _on_alias_change: Callable[[str], None]
    _on_tags_change: Callable[[], None]

    # ── start editing ──────────────────────────────────────────────────────

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

    # ── confirm editing ────────────────────────────────────────────────────

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

    # ── input routing ──────────────────────────────────────────────────────

    def handle_key(self, key: str) -> bool:
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

    # ── properties ─────────────────────────────────────────────────────────

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
