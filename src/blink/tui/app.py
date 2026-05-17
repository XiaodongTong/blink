from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style

from blink.models import Repo
from blink.store import Store
from blink.scanner import Scanner, ScanResult
from blink.tui.repo_list import RepoListControl, RepoListWindow
from blink.tui.search import SearchBar
from blink.tui.actions import EditorInfo, copy_path, detect_editors, open_in_editor
from blink.tui.detail import DetailPanel


class BlinkApp:
    def __init__(self, store: Store, scanner: Scanner, is_first_run: bool = False) -> None:
        self._store = store
        self._scanner = scanner
        self._editors: Dict[str, EditorInfo] = detect_editors()
        self._scanning = False
        self._scan_status = ""

        self._repo_control = RepoListControl()
        self._search_bar = SearchBar(on_change=self._on_search_change)

        self._status_control = FormattedTextControl(text=self._status_text)
        self._footer_control = FormattedTextControl(text=self._footer_text)

        self._detail_panel: Optional[DetailPanel] = None
        self._list_layout: Optional[Layout] = None

        self._mode: str = "list"
        self._search_active: bool = False
        self._search_filtering: bool = False
        self._footer_highlight_until: float = 0.0
        self._editing_alias = False
        self._alias_buffer = Buffer()
        self._editing_tag = False
        self._tag_buffer = Buffer()
        self._editing_repo: Optional[Repo] = None

        self._last_ctrl_c: float = 0.0
        self._ctrl_c_quit_hint: bool = False

        self._list_layout = self._build_list_layout()

        self._app = Application(
            layout=self._list_layout,
            key_bindings=self._build_key_bindings(),
            style=self._build_style(),
            full_screen=True,
            mouse_support=False,
        )

        self._load_repos()

    def _in_edit_mode(self) -> bool:
        if self._editing_alias or self._editing_tag:
            return True
        if self._detail_panel is not None:
            return self._detail_panel.is_editing_alias or self._detail_panel.is_adding_tag
        return False

    def _in_tag_mode(self) -> bool:
        if self._editing_tag:
            return True
        if self._detail_panel is not None:
            return self._detail_panel.is_adding_tag
        return False

    def _build_list_layout(self) -> Layout:
        return Layout(
            HSplit([
                Window(
                    content=FormattedTextControl(text=self._search_prefix_text),
                    height=D.exact(1),
                    style="class:search-bar",
                ),
                ConditionalContainer(
                    self._search_bar.window,
                    filter=Condition(lambda: self._search_active),
                ),
                Window(height=D.exact(1), char="─", style="class:border"),
                RepoListWindow(self._repo_control),
                Window(height=D.exact(1), char="─", style="class:border"),
                Window(content=self._status_control, height=D.exact(1), style="class:status"),
                Window(content=self._footer_control, height=D.exact(1), style="class:footer"),
            ])
        )

    def _build_style(self) -> Style:
        return Style.from_dict({
            # Search
            "search-bar": "fg:#c9d1d9 bg:#0d1117",
            "search-input": "fg:#c9d1d9 bg:#0d1117",
            "search-prefix": "fg:#58a6ff bg:#0d1117",
            # Repo list — normal row
            "repo-list": "",
            "normal": "fg:#c9d1d9",
            "dim": "fg:#484f58",
            "path": "fg:#484f58",
            "tag": "fg:#3fb950",
            "tag-bracket": "fg:#238636",
            # Repo list — selected row
            "indicator": "fg:#58a6ff bold bg:#264f78",
            "repo-selected": "fg:#f0f6fc bg:#264f78",
            "selected-dim": "fg:#8db9e2 bg:#264f78",
            "selected-tag": "fg:#7ee787 bg:#264f78",
            "selected-tag-bracket": "fg:#3fb950 bg:#264f78",
            # Empty state
            "empty": "fg:#484f58 italic",
            # Borders
            "border": "fg:#30363d",
            # Status bar
            "status": "bg:#161b22",
            "status-label": "fg:#8b949e bg:#161b22",
            "status-value": "fg:#c9d1d9 bg:#161b22",
            "status-accent": "fg:#58a6ff bg:#161b22",
            "status-dim": "fg:#484f58 bg:#161b22",
            # Footer
            "footer": "bg:#0d1117",
            "footer-key": "bold fg:#58a6ff bg:#0d1117",
            "footer-dim": "fg:#30363d bg:#0d1117",
            "footer-dim-key": "bold fg:#30363d bg:#0d1117",
            "footer-highlight": "fg:#c9d1d9 bg:#0d1117",
            # Search
            "search-keyword": "fg:#8b949e bg:#0d1117",
            # Detail panel
            "detail-panel": "fg:#c9d1d9",
            "label": "bold fg:#58a6ff",
            "detail-sep": "fg:#30363d",
            # Tags in detail
            "detail-tag": "fg:#3fb950",
            "detail-tag-bracket": "fg:#238636",
        })

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _(event):
            # Priority chain: edit mode → search active → detail view → list view double-quit
            if self._detail_panel is not None:
                if self._detail_panel.is_editing_alias:
                    self._detail_panel._editing_alias = False
                    self._app.invalidate()
                    return
                if self._detail_panel.is_adding_tag:
                    self._detail_panel._tag_adding = False
                    self._detail_panel._tag_buffer = None
                    self._app.invalidate()
                    return
                self._show_list_view()
                return
            if self._editing_alias or self._editing_tag:
                self._cancel_edit()
                return
            if self._search_active:
                self._search_bar.clear()
                self._search_active = False
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()
                return
            # List view: double Ctrl+C to quit
            now = time.monotonic()
            if self._ctrl_c_quit_hint and (now - self._last_ctrl_c) < 2.0:
                event.app.exit()
                return
            self._last_ctrl_c = now
            self._ctrl_c_quit_hint = True
            self._app.invalidate()
            threading.Timer(2.0, self._reset_ctrl_c_hint).start()

        @kb.add("escape")
        def _(event):
            if self._detail_panel is not None:
                if self._detail_panel.is_editing_alias:
                    self._detail_panel._editing_alias = False
                    self._app.invalidate()
                    return
                if self._detail_panel.is_adding_tag:
                    self._detail_panel._tag_adding = False
                    self._detail_panel._tag_buffer = None
                    self._app.invalidate()
                    return
                self._show_list_view()
            elif self._editing_alias or self._editing_tag:
                self._cancel_edit()
            elif self._search_active:
                self._search_bar.clear()
                self._search_active = False
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()
            elif self._search_filtering:
                self._search_bar.clear()
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()

        @kb.add("down", filter=Condition(lambda: not self._search_active))
        @kb.add("s-down", filter=Condition(lambda: not self._search_active))
        def _(event):
            if self._mode == "list":
                self._repo_control.move_down()
                self._app.invalidate()

        @kb.add("up", filter=Condition(lambda: not self._search_active))
        @kb.add("s-up", filter=Condition(lambda: not self._search_active))
        def _(event):
            if self._mode == "list":
                self._repo_control.move_up()
                self._app.invalidate()

        @kb.add("/", filter=Condition(lambda: not self._search_active))
        def _(event):
            if self._mode == "list" and not self._editing_alias and not self._editing_tag:
                self._search_active = True
                self._search_filtering = False
                self._search_bar.focus(event.app)
                self._app.invalidate()

        # Detail-view bare keys (v/u/a/o/y only work in detail view)
        for key in ("v", "u", "a", "o"):
            def make_handler(k):
                def _(event):
                    if self._in_edit_mode():
                        return
                    repo = self._get_active_repo()
                    if repo:
                        open_in_editor(repo.path, k, self._editors)
                return _
            kb.add(key, filter=Condition(lambda: self._detail_panel is not None))(make_handler(key))

        # Shift-gated keys for list view
        for skey, raw in (("V", "v"), ("U", "u"), ("A", "a"), ("O", "o")):
            def make_shift_handler(k):
                def _(event):
                    self._trigger_footer_highlight()
                    if self._in_edit_mode():
                        return
                    repo = self._get_active_repo()
                    if repo:
                        open_in_editor(repo.path, k, self._editors)
                return _
            kb.add(skey, filter=Condition(lambda: not self._search_active))(make_shift_handler(raw))

        @kb.add("y", filter=Condition(lambda: self._detail_panel is not None))
        def _(event):
            if self._in_edit_mode():
                return
            repo = self._get_active_repo()
            if repo:
                copy_path(repo.path)
                self._scan_status = f"Copied: {repo.path}"
                self._app.invalidate()

        @kb.add("Y", filter=Condition(lambda: not self._search_active))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                copy_path(repo.path)
                self._scan_status = f"Copied: {repo.path}"
                self._app.invalidate()

        @kb.add("R", filter=Condition(lambda: not self._search_active))
        def _(event):
            self._trigger_footer_highlight()
            if not self._scanning and self._mode == "list" and not self._in_edit_mode():
                self._start_background_scan()

        @kb.add("enter")
        def _(event):
            if self._search_active:
                self._search_active = False
                if self._search_bar.text:
                    self._search_filtering = True
                self._app.invalidate()
                return
            if self._editing_alias:
                alias = self._alias_buffer.text.strip()
                if self._editing_repo and self._editing_repo.id is not None:
                    self._store.set_alias(self._editing_repo.id, alias)
                    self._editing_repo.alias = alias
                    self._load_repos()
                self._cancel_edit()
            elif self._editing_tag:
                tag = self._tag_buffer.text.strip()
                if tag and self._editing_repo and self._editing_repo.id is not None:
                    self._store.add_tag(self._editing_repo.id, tag)
                    self._editing_repo.tags = self._store.get_tags_for_repo(self._editing_repo.id)
                    self._tag_buffer.text = ""
                    self._load_repos()
                self._app.invalidate()
            elif self._detail_panel is not None:
                if self._detail_panel.is_adding_tag and self._detail_panel._tag_buffer:
                    tag = self._detail_panel._tag_buffer.text.strip()
                    if tag and self._detail_panel._repo.id is not None:
                        self._detail_panel._store.add_tag(self._detail_panel._repo.id, tag)
                        self._detail_panel._repo.tags = self._detail_panel._store.get_tags_for_repo(
                            self._detail_panel._repo.id
                        )
                        self._detail_panel._on_tags_change()
                    self._detail_panel._tag_buffer.text = ""
                    self._app.invalidate()
                elif self._detail_panel.is_editing_alias and self._detail_panel._alias_buffer:
                    alias = self._detail_panel._alias_buffer.text.strip()
                    self._detail_panel.confirm_alias(alias)
                    self._app.invalidate()
            elif self._mode == "list" and not self._detail_panel:
                repo = self._repo_control.selected_repo()
                if repo:
                    self._show_detail_view(repo)

        @kb.add("e", filter=Condition(lambda: self._detail_panel is not None))
        def _(event):
            if not self._detail_panel.is_editing_alias and not self._detail_panel.is_adding_tag:
                self._detail_panel.handle_alias_edit()
                self._app.invalidate()

        @kb.add("t", filter=Condition(lambda: self._detail_panel is not None))
        def _(event):
            if not self._detail_panel.is_editing_alias and not self._detail_panel.is_adding_tag:
                self._detail_panel.handle_tag_edit()
                self._app.invalidate()

        for i in range(1, 10):
            def make_tag_remove(n):
                def _(event):
                    if self._editing_tag and self._editing_repo and self._editing_repo.id is not None:
                        tags = self._editing_repo.tags
                        if n <= len(tags):
                            tag = tags[n - 1]
                            self._store.remove_tag(self._editing_repo.id, tag)
                            self._editing_repo.tags = self._store.get_tags_for_repo(self._editing_repo.id)
                            self._load_repos()
                    elif self._detail_panel is not None and self._detail_panel.is_adding_tag:
                        self._detail_panel.handle_key(str(n))
                        self._app.invalidate()
                return _
            kb.add(str(i), filter=Condition(lambda: not self._search_active))(make_tag_remove(i))

        # Backspace — route to active buffer in any edit mode
        @kb.add("backspace", eager=True, filter=Condition(lambda: self._in_edit_mode()))
        def _(event):
            self._route_backspace()

        # Printable non-digit chars — route to active buffer in any edit mode
        for code in range(33, 127):
            char = chr(code)
            if char.isdigit():
                continue
            def make_handler(c):
                def _(event):
                    self._route_printable(c)
                return _
            kb.add(char, eager=True, filter=Condition(lambda: self._in_edit_mode()))(make_handler(char))

        # Space — route to active buffer
        @kb.add("space", eager=True, filter=Condition(lambda: self._in_edit_mode()))
        def _(event):
            self._route_printable(" ")

        # Digits 0-9 — route to buffer only when NOT in tag mode (tag mode reserves 1-9 for removal)
        for d in "0123456789":
            def make_handler(c):
                def _(event):
                    self._route_printable(c)
                return _
            kb.add(d, eager=True, filter=Condition(lambda: self._in_edit_mode() and not self._in_tag_mode()))(
                make_handler(d)
            )

        return kb

    def _route_printable(self, char: str) -> None:
        if self._editing_alias:
            self._alias_buffer.text += char
        elif self._editing_tag:
            self._tag_buffer.text += char
        elif self._detail_panel is not None:
            if self._detail_panel.is_editing_alias and self._detail_panel._alias_buffer:
                self._detail_panel._alias_buffer.text += char
            elif self._detail_panel.is_adding_tag and self._detail_panel._tag_buffer:
                self._detail_panel._tag_buffer.text += char
        self._app.invalidate()

    def _route_backspace(self) -> None:
        if self._editing_alias:
            self._alias_buffer.text = self._alias_buffer.text[:-1]
        elif self._editing_tag:
            self._tag_buffer.text = self._tag_buffer.text[:-1]
        elif self._detail_panel is not None:
            if self._detail_panel.is_editing_alias and self._detail_panel._alias_buffer:
                self._detail_panel._alias_buffer.text = self._detail_panel._alias_buffer.text[:-1]
            elif self._detail_panel.is_adding_tag and self._detail_panel._tag_buffer:
                self._detail_panel._tag_buffer.text = self._detail_panel._tag_buffer.text[:-1]
        self._app.invalidate()

    def _get_active_repo(self) -> Optional[Repo]:
        if self._detail_panel is not None:
            return self._detail_panel._repo
        return self._repo_control.selected_repo()

    def _start_alias_edit(self, repo: Repo) -> None:
        self._mode = "edit_alias"
        self._editing_alias = True
        self._editing_tag = False
        self._editing_repo = repo
        self._alias_buffer.text = repo.alias if repo.alias else ""
        self._scan_status = f"Editing alias for {repo.name} — Enter: save, Esc: cancel"
        self._app.invalidate()

    def _start_tag_edit(self, repo: Repo) -> None:
        self._mode = "edit_tag"
        self._editing_alias = False
        self._editing_tag = True
        self._editing_repo = repo
        self._tag_buffer.text = ""
        self._scan_status = f"Managing tags for {repo.name} — 1-9: remove tag, type & Enter: add, Esc: cancel"
        self._app.invalidate()

    def _cancel_edit(self) -> None:
        self._editing_alias = False
        self._editing_tag = False
        self._editing_repo = None
        self._mode = "list"
        self._scan_status = ""
        self._app.invalidate()

    def _search_prefix_text(self) -> FormattedText:
        if self._search_active:
            return FormattedText([("class:search-prefix", " / ")])
        if self._search_filtering and self._search_bar.text:
            return FormattedText([
                ("class:search-prefix", " / "),
                ("class:search-keyword", self._search_bar.text),
            ])
        return FormattedText([("class:search-prefix", " /")])

    def _reset_ctrl_c_hint(self) -> None:
        self._ctrl_c_quit_hint = False
        self._app.invalidate()

    def _reset_footer_highlight(self) -> None:
        self._footer_highlight_until = 0.0
        self._app.invalidate()

    def _trigger_footer_highlight(self) -> None:
        self._footer_highlight_until = time.monotonic() + 2.0
        self._app.invalidate()
        threading.Timer(2.0, self._reset_footer_highlight).start()

    def _show_detail_view(self, repo: Repo) -> None:
        self._detail_panel = DetailPanel(
            repo=repo,
            store=self._store,
            editors=self._editors,
            on_back=self._show_list_view,
            on_alias_change=lambda alias: self._refresh_repo_alias(repo, alias),
            on_tags_change=lambda: self._refresh_repo_tags(repo),
        )
        self._mode = "detail"
        detail_layout = Layout(
            HSplit([
                Window(
                    content=FormattedTextControl(text=self._detail_panel._formatted_text),
                    style="class:detail-panel",
                ),
                Window(height=D.exact(1), char="─", style="class:border"),
                Window(content=self._status_control, height=D.exact(1), style="class:status"),
                Window(content=FormattedTextControl(text=self._detail_footer_text), height=D.exact(1), style="class:footer"),
            ])
        )
        self._app.layout = detail_layout
        self._app.invalidate()

    def _show_list_view(self) -> None:
        self._detail_panel = None
        self._mode = "list"
        self._app.layout = self._list_layout
        self._footer_control.text = self._footer_text
        self._app.invalidate()

    def _refresh_repo_alias(self, repo: Repo, alias: str) -> None:
        self._load_repos()

    def _refresh_repo_tags(self, repo: Repo) -> None:
        self._load_repos()

    def _on_search_change(self, text: str) -> None:
        repos = self._store.search_repos(text)
        self._repo_control.set_repos(repos)
        self._app.invalidate()

    def _load_repos(self) -> None:
        repos = self._store.search_repos(self._search_bar.text)
        self._repo_control.set_repos(repos)

    def _start_background_scan(self) -> None:
        self._scanning = True
        self._scan_status = "Scanning..."
        self._app.invalidate()

        def on_result(sr: ScanResult) -> None:
            rid = self._store.upsert_repo(sr.repo)
            for remote in sr.remotes:
                remote.repo_id = rid
                self._store.upsert_remote(remote)
            self._load_repos()

        def done(results: List[ScanResult]) -> None:
            self._scanning = False
            self._scan_status = f"Scan complete — {len(results)} repos found"
            self._app.invalidate()

        def run() -> None:
            results = self._scanner.run_scan(blocking=True, on_result=on_result)
            done(results)

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _styled_footer_hints(self, hints: list[tuple[str, str]]) -> FormattedText:
        parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
        for i, (key, desc) in enumerate(hints):
            if i > 0:
                parts.append(("class:footer-dim", "  "))
            parts.append(("class:footer-key", key))
            parts.append(("class:footer-dim", f":{desc}"))
        return FormattedText(parts)

    def _status_text(self) -> FormattedText:
        if self._editing_alias:
            buf_text = self._alias_buffer.text
            return FormattedText([
                ("class:status-label", " Alias: "),
                ("class:status-value", buf_text),
            ])
        if self._editing_tag:
            buf_text = self._tag_buffer.text
            return FormattedText([
                ("class:status-label", " Tag: "),
                ("class:status-value", buf_text),
            ])
        if self._detail_panel is not None:
            if self._detail_panel.is_editing_alias and self._detail_panel._alias_buffer:
                buf_text = self._detail_panel._alias_buffer.text
                return FormattedText([
                    ("class:status-label", " Alias: "),
                    ("class:status-value", buf_text),
                ])
            if self._detail_panel.is_adding_tag and self._detail_panel._tag_buffer:
                buf_text = self._detail_panel._tag_buffer.text
                return FormattedText([
                    ("class:status-label", " Tag: "),
                    ("class:status-value", buf_text),
                ])
        count = len(self._repo_control.repos)
        if self._search_filtering and self._search_bar.text:
            return FormattedText([
                ("class:status-accent", f" {count}"),
                ("class:status-label", f" result{'s' if count != 1 else ''} for "),
                ("class:status-value", self._search_bar.text),
            ])
        if self._scanning:
            return FormattedText([
                ("class:status-accent", " ⟳ "),
                ("class:status-label", "Scanning..."),
            ])
        return FormattedText([
            ("class:status-accent", f" {count}"),
            ("class:status-label", f" repo{'s' if count != 1 else ''}"),
        ])

    def _footer_text(self) -> FormattedText:
        if self._ctrl_c_quit_hint:
            return FormattedText([
                ("class:status-accent", " Press Ctrl+C again to quit"),
            ])
        if self._search_active:
            return self._styled_footer_hints([
                ("Enter", "confirm"), ("Esc/Ctrl+C", "cancel"),
            ])
        if self._editing_alias:
            return self._styled_footer_hints([
                ("Enter", "save alias"), ("Esc", "cancel"),
            ])
        if self._editing_tag:
            return self._styled_footer_hints([
                ("1-9", "remove tag"), ("Enter", "add tag"), ("Esc", "cancel"),
            ])
        highlighted = time.monotonic() < self._footer_highlight_until
        style_key = "class:footer-key" if highlighted else "class:footer-dim-key"
        style_dim = "class:footer-highlight" if highlighted else "class:footer-dim"
        hints = [
            ("Shift+↑/↓", "nav"), ("Enter", "detail"), ("/", "search"),
            ("Shift+V", "code"), ("Shift+U", "cursor"), ("Shift+A", "antigrav"),
            ("Shift+O", "open"), ("Shift+Y", "yank"), ("Shift+R", "rescan"),
        ]
        parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
        for i, (key, desc) in enumerate(hints):
            if i > 0:
                parts.append(("class:footer-dim", "  "))
            parts.append((style_key, key))
            parts.append((style_dim, f":{desc}"))
        return FormattedText(parts)

    def _detail_footer_text(self) -> FormattedText:
        if self._detail_panel is not None:
            if self._detail_panel.is_editing_alias:
                return self._styled_footer_hints([
                    ("Enter", "save alias"), ("Esc", "cancel"),
                ])
            if self._detail_panel.is_adding_tag:
                return self._styled_footer_hints([
                    ("1-9", "remove tag"), ("Enter", "add tag"), ("Esc", "cancel"),
                ])
        return self._styled_footer_hints([
            ("e", "edit alias"), ("t", "manage tags"), ("v", "code"),
            ("u", "cursor"), ("a", "antigrav"), ("o", "open"),
            ("y", "copy path"), ("Ctrl+C", "back"), ("Esc", "back"),
        ])

    def run(self) -> None:
        self._app.run()

    def run_scan_blocking(self, on_progress: Optional[Callable[[int], None]] = None) -> None:
        results = self._scanner.run_scan(blocking=True, on_progress=on_progress)
        for sr in results:
            rid = self._store.upsert_repo(sr.repo)
            for remote in sr.remotes:
                remote.repo_id = rid
                self._store.upsert_remote(remote)
        self._load_repos()
