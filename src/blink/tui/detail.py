from __future__ import annotations

from typing import Callable, List, Optional

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import FormattedText

from blink.models import Repo
from blink.store import Store
from blink.tui.actions import EditorInfo, copy_path, open_in_editor


class DetailPanel:
    # Line indices for the form rows
    LINE_ALIAS = 0
    LINE_NAME = 1
    LINE_PATH = 2
    LINE_DESC = 3
    LINE_REMOTES = 4
    LINE_TAGS = 5
    LINE_SCANNED = 6
    LINE_ANTIGRAVITY = 7
    LINE_CURSOR = 8
    LINE_VSCODE = 9
    LINE_FINDER = 10
    MAX_LINE = 10

    def __init__(self, repo: Repo, store: Store, editors: dict[str, EditorInfo],
                 on_back: Callable[[], None], on_alias_change: Callable[[str], None],
                 on_tags_change: Callable[[], None]) -> None:
        self._repo = repo
        self._store = store
        self._editors = editors
        self._on_back = on_back
        self._on_alias_change = on_alias_change
        self._on_tags_change = on_tags_change

        self._cursor_index = 0
        self._edit_mode: str | None = None  # None | "alias" | "description" | "tags"
        self._alias_buffer: Optional[Buffer] = None
        self._desc_buffer: Optional[Buffer] = None
        self._tag_buffer: Optional[Buffer] = None

        self._editing_alias_before = False
        self._editing_desc_before = False

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
        elif line == self.LINE_REMOTES:
            self._copy_remotes()
        elif line == self.LINE_TAGS:
            self._start_tags_edit()
        elif line == self.LINE_SCANNED:
            self._copy_scanned()
        elif line == self.LINE_ANTIGRAVITY:
            open_in_editor(self._repo.path, "a", self._editors)
        elif line == self.LINE_CURSOR:
            open_in_editor(self._repo.path, "u", self._editors)
        elif line == self.LINE_VSCODE:
            open_in_editor(self._repo.path, "v", self._editors)
        elif line == self.LINE_FINDER:
            open_in_editor(self._repo.path, "o", self._editors)
        return True

    # ── line-specific actions ────────────────────────────────────────────────

    def _copy_name(self) -> None:
        copy_path(self._repo.name)

    def _copy_path(self) -> None:
        copy_path(self._repo.path)

    def _copy_remotes(self) -> None:
        if self._repo.remotes:
            copy_path(self._repo.remotes[0].url)

    def _copy_scanned(self) -> None:
        copy_path(self._repo.last_synced)

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

    def _build_one_line(self, label: str, value: str, selected: bool) -> List[tuple[str, str]]:
        """Render a single label+value line, optionally selected."""
        cls = "selected" if selected else "normal"
        return [
            ("class:indicator" if selected else "class:dim", "  ▸ " if selected else "    "),
            ("class:label", label),
            ("class:" + cls, value + "\n"),
        ]

    def _formatted_text(self) -> FormattedText:
        cur = self._cursor_index
        edit = self._edit_mode

        parts: List[tuple[str, str]] = []

        # Row 0: Alias
        val = self._alias_buffer.text if edit == "alias" and self._alias_buffer else (self._repo.alias or "(none)")
        parts += self._build_one_line("Alias     ", val, cur == self.LINE_ALIAS)

        # Row 1: Name
        parts += self._build_one_line("Name      ", self._repo.name, cur == self.LINE_NAME)

        # Row 2: Path
        parts += self._build_one_line("Path      ", self._repo.path, cur == self.LINE_PATH)

        # Row 3: Description
        val = self._desc_buffer.text if edit == "description" and self._desc_buffer else (self._repo.description or "(none)")
        parts += self._build_one_line("Desc      ", val, cur == self.LINE_DESC)

        # Separator
        parts.append(("class:detail-sep", "\n"))

        # Row 4: Remotes
        parts += self._build_one_line("Remotes   ", self._repo.remotes[0].url if self._repo.remotes else "(none)", cur == self.LINE_REMOTES)

        # Row 5: Tags
        tag_str = " ".join(f"[{t}]" for t in self._repo.tags) if self._repo.tags else "(none)"
        parts += self._build_one_line("Tags      ", tag_str, cur == self.LINE_TAGS)

        # Separator
        parts.append(("class:detail-sep", "\n"))

        # Row 6: Scanned
        parts += self._build_one_line("Scanned   ", self._repo.last_synced, cur == self.LINE_SCANNED)

        # Separator before action rows
        parts.append(("class:detail-sep", "\n"))

        # Row 7: Antigravity
        parts += self._build_one_line("", "Antigravity", cur == self.LINE_ANTIGRAVITY)

        # Row 8: Cursor
        parts += self._build_one_line("", "Cursor", cur == self.LINE_CURSOR)

        # Row 9: VSCode
        parts += self._build_one_line("", "Visual Studio Code", cur == self.LINE_VSCODE)

        # Row 10: Finder
        parts += self._build_one_line("", "Finder", cur == self.LINE_FINDER)

        return FormattedText(parts)