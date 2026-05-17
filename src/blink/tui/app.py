from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
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

    # ── edit mode helpers ────────────────────────────────────────────────────

    def _in_edit_mode(self) -> bool:
        if self._detail_panel is not None:
            return self._detail_panel.is_editing
        return False

    def _in_tag_mode(self) -> bool:
        if self._detail_panel is not None:
            return self._detail_panel.edit_mode == "tags"
        return False

    # ── layouts ─────────────────────────────────────────────────────────────

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

    def _build_detail_layout(self) -> Layout:
        return Layout(
            HSplit([
                Window(
                    content=self._detail_panel,
                    style="class:detail-panel",
                ),
                Window(height=D.exact(1), char="─", style="class:border"),
                Window(content=self._status_control, height=D.exact(1), style="class:status"),
                # No footer in detail view per spec
            ])
        )

    # ── styles ───────────────────────────────────────────────────────────────

    def _build_style(self) -> Style:
        return Style.from_dict({
            # Search
            "search-bar": "fg:#c9d1d9 bg:#0d1117",
            "search-input": "fg:#c9d1d9 bg:#0d1117",
            "search-prefix": "fg:#58a6ff bg:#0d1117",
            # Repo list — normal row
            "repo-list": "",
            "normal": "fg:#e6edf3",
            "dim": "fg:#484f58",
            "alias": "fg:#8b949e",
            "path": "fg:#6e7681",
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
            "status": "",
            "status-label": "fg:#8b949e",
            "status-value": "fg:#c9d1d9",
            "status-accent": "fg:#58a6ff",
            "status-dim": "fg:#6e7681",
            # Footer
            "footer": "",
            "footer-key": "bold fg:#79c0ff",
            "footer-dim": "fg:#8b949e",
            "footer-dim-key": "bold fg:#58a6ff",
            "footer-highlight": "fg:#f0f6fc",
            # Search
            "search-keyword": "fg:#8b949e bg:#0d1117",
            # Detail panel
            "detail-panel": "fg:#c9d1d9",
            "label": "bold fg:#58a6ff",
            "detail-label-sel": "bold fg:#58a6ff bg:#264f78",
            "detail-sep": "fg:#30363d",
            # Selected row in detail panel
            "detail-selected": "fg:#f0f6fc bg:#264f78",
            "detail-indicator": "fg:#58a6ff bold bg:#264f78",
            # Tags in detail
            "detail-tag": "fg:#3fb950",
            "detail-tag-bracket": "fg:#238636",
        })

    # ── key bindings ─────────────────────────────────────────────────────────

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        # ── Ctrl+C ──────────────────────────────────────────────────────────
        @kb.add("c-c")
        def _(event):
            # Priority: edit mode → search active → detail view → double-quit
            if self._detail_panel is not None and self._detail_panel.is_editing:
                if self._detail_panel.edit_mode == "alias":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._alias_buffer = None
                elif self._detail_panel.edit_mode == "description":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._desc_buffer = None
                elif self._detail_panel.edit_mode == "tags":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._tag_buffer = None
                self._app.invalidate()
                return
            if self._search_active:
                self._search_bar.clear()
                self._search_active = False
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()
                return
            if self._detail_panel is not None:
                self._show_list_view()
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

        # ── Escape ───────────────────────────────────────────────────────────
        @kb.add("escape")
        def _(event):
            if self._detail_panel is not None and self._detail_panel.is_editing:
                if self._detail_panel.edit_mode == "alias":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._alias_buffer = None
                elif self._detail_panel.edit_mode == "description":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._desc_buffer = None
                elif self._detail_panel.edit_mode == "tags":
                    self._detail_panel._edit_mode = None
                    self._detail_panel._tag_buffer = None
                self._app.invalidate()
                return
            if self._search_active:
                self._search_bar.clear()
                self._search_active = False
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()
                return
            if self._search_filtering:
                self._search_bar.clear()
                self._search_filtering = False
                self._load_repos()
                self._app.invalidate()
                return
            if self._detail_panel is not None:
                self._show_list_view()
                return

        # ── Arrow keys — list view navigation ───────────────────────────────
        @kb.add("down", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        @kb.add("s-down", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        def _(event):
            self._repo_control.move_down()
            self._app.invalidate()

        @kb.add("up", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        @kb.add("s-up", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        def _(event):
            self._repo_control.move_up()
            self._app.invalidate()

        # ── Arrow keys — detail view line navigation ──────────────────────────
        @kb.add("down", filter=Condition(lambda: self._detail_panel is not None and not self._search_active))
        def _(event):
            if self._detail_panel:
                self._detail_panel.cursor_down()
                self._app.invalidate()

        @kb.add("up", filter=Condition(lambda: self._detail_panel is not None and not self._search_active))
        def _(event):
            if self._detail_panel:
                self._detail_panel.cursor_up()
                self._app.invalidate()

        # ── Search ───────────────────────────────────────────────────────────
        @kb.add("/", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        def _(event):
            self._search_active = True
            self._search_filtering = False
            self._search_bar.focus(event.app)
            self._app.invalidate()

        # ── Shift-gated list view actions ───────────────────────────────────
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
            kb.add(skey, filter=Condition(lambda: not self._search_active and self._detail_panel is None))(make_shift_handler(raw))

        @kb.add("P", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._repo_control.selected_repo()
            if repo:
                copy_path(repo.path)
                self._scan_status = f"Copied: {repo.path}"
                self._app.invalidate()
                threading.Timer(5.0, self._clear_scan_status).start()

        @kb.add("R", filter=Condition(lambda: not self._search_active and self._detail_panel is None))
        def _(event):
            self._trigger_footer_highlight()
            if not self._scanning and not self._in_edit_mode():
                self._start_background_scan()

        # ── Enter ────────────────────────────────────────────────────────────
        @kb.add("enter")
        def _(event):
            if self._search_active:
                self._search_active = False
                if self._search_bar.text:
                    self._search_filtering = True
                self._app.invalidate()
                return
            if self._detail_panel is not None:
                self._detail_panel.handle_enter()
                self._app.invalidate()
                return
            if self._mode == "list":
                repo = self._repo_control.selected_repo()
                if repo:
                    self._show_detail_view(repo)

        # ── Detail view: bare keys (v/u/a/o/y) — work via Enter on action rows ─

        # ── Tag removal 1-9 (detail panel tag edit mode) ────────────────────
        for i in range(1, 10):
            def make_tag_remove(n):
                def _(event):
                    if self._detail_panel is not None and self._detail_panel.edit_mode == "tags":
                        self._detail_panel.handle_key(str(n))
                        self._app.invalidate()
                return _
            kb.add(str(i), filter=Condition(lambda: not self._search_active))(make_tag_remove(i))

        # ── Backspace — route to active buffer in any edit mode ──────────────
        @kb.add("backspace", eager=True, filter=Condition(lambda: self._in_edit_mode()))
        def _(event):
            self._route_backspace()

        # ── Printable chars — route to active buffer in any edit mode ────────
        for code in range(33, 127):
            char = chr(code)
            if char.isdigit():
                continue
            def make_handler(c):
                def _(event):
                    self._route_printable(c)
                return _
            kb.add(char, eager=True, filter=Condition(lambda: self._in_edit_mode()))(make_handler(char))

        # ── Space — route to active buffer ───────────────────────────────────
        @kb.add("space", eager=True, filter=Condition(lambda: self._in_edit_mode()))
        def _(event):
            self._route_printable(" ")

        # ── Non-ASCII printable (CJK etc.) — Keys.Any catches everything ──────
        @kb.add(Keys.Any, filter=Condition(lambda: self._in_edit_mode()))
        def _(event):
            key_seq = event.key_sequence
            if key_seq and len(key_seq) == 1:
                k = key_seq[0].key
                if isinstance(k, str) and k.isprintable() and len(k) == 1 and ord(k) > 127:
                    self._route_printable(k)

        # ── Digits 0-9 — route to buffer only when NOT in tag mode ─────────────
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
        if self._detail_panel is not None and self._detail_panel.is_editing:
            self._detail_panel.route_printable(char)
        self._app.invalidate()

    def _route_backspace(self) -> None:
        if self._detail_panel is not None and self._detail_panel.is_editing:
            self._detail_panel.route_backspace()
        self._app.invalidate()

    # ── repo helpers ─────────────────────────────────────────────────────────

    def _get_active_repo(self) -> Optional[Repo]:
        if self._detail_panel is not None:
            return self._detail_panel._repo
        return self._repo_control.selected_repo()

    # ── search ───────────────────────────────────────────────────────────────

    def _search_prefix_text(self) -> FormattedText:
        if self._search_active:
            return FormattedText([("class:search-prefix", " / ")])
        if self._search_filtering and self._search_bar.text:
            return FormattedText([
                ("class:search-prefix", " / "),
                ("class:search-keyword", self._search_bar.text),
            ])
        return FormattedText([("class:search-prefix", " /")])

    # ── status text ─────────────────────────────────────────────────────────

    def _status_text(self) -> FormattedText:
        if self._detail_panel is not None and self._detail_panel.is_editing:
            mode = self._detail_panel.edit_mode
            if mode == "alias" and self._detail_panel.alias_buffer:
                return FormattedText([
                    ("class:status-label", " Alias: "),
                    ("class:status-value", self._detail_panel.alias_buffer.text),
                ])
            if mode == "description" and self._detail_panel.desc_buffer:
                return FormattedText([
                    ("class:status-label", " Desc: "),
                    ("class:status-value", self._detail_panel.desc_buffer.text),
                ])
            if mode == "tags" and self._detail_panel.tag_buffer:
                return FormattedText([
                    ("class:status-label", " Tag: "),
                    ("class:status-value", self._detail_panel.tag_buffer.text),
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
        if self._scan_status:
            return FormattedText([
                ("class:status-accent", f" {self._scan_status}"),
            ])
        repo = self._repo_control.selected_repo()
        if repo:
            if repo.description:
                return FormattedText([
                    ("class:status-value", f" {repo.description}"),
                    ("class:status-dim", f"  {repo.path}"),
                ])
            return FormattedText([
                ("class:status-value", f" {repo.path}"),
            ])
        return FormattedText([])

    # ── footer text ─────────────────────────────────────────────────────────

    def _footer_text(self) -> FormattedText:
        if self._ctrl_c_quit_hint:
            return FormattedText([
                ("class:status-accent", " Press Ctrl+C again to quit"),
            ])
        if self._search_active:
            return self._styled_footer_hints([
                ("Enter", "confirm"), ("Esc/Ctrl+C", "cancel"),
            ])
        highlighted = time.monotonic() < self._footer_highlight_until
        style_key = "class:footer-key" if highlighted else "class:footer-dim-key"
        style_dim = "class:footer-highlight" if highlighted else "class:footer-dim"
        hints = [
            ("Enter", "detail"), ("/", "search"),
            ("Shift+V", "code"), ("Shift+U", "cursor"), ("Shift+A", "antigrav"),
            ("Shift+O", "open"), ("Shift+P", "path"), ("Shift+R", "rescan"),
        ]
        parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
        for i, (key, desc) in enumerate(hints):
            if i > 0:
                parts.append(("class:footer-dim", "  "))
            parts.append((style_key, key))
            parts.append((style_dim, f":{desc}"))
        return FormattedText(parts)

    def _styled_footer_hints(self, hints: list[tuple[str, str]]) -> FormattedText:
        parts: list[tuple[str, str]] = [("class:footer-dim", " ")]
        for i, (key, desc) in enumerate(hints):
            if i > 0:
                parts.append(("class:footer-dim", "  "))
            parts.append(("class:footer-key", key))
            parts.append(("class:footer-dim", f":{desc}"))
        return FormattedText(parts)

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

    # ── view switching ──────────────────────────────────────────────────────

    def _show_detail_view(self, repo: Repo) -> None:
        self._detail_panel = DetailPanel(
            repo=repo,
            store=self._store,
            editors=self._editors,
            on_back=self._show_list_view,
            on_alias_change=lambda alias: self._refresh_repo_alias(repo, alias),
            on_tags_change=lambda: self._refresh_repo_tags(repo),
            on_status_message=self._set_scan_status,
        )
        self._mode = "detail"
        self._app.layout = self._build_detail_layout()
        self._app.invalidate()

    def _show_list_view(self) -> None:
        self._detail_panel = None
        self._mode = "list"
        self._app.layout = self._list_layout
        self._app.invalidate()

    def _refresh_repo_alias(self, repo: Repo, alias: str) -> None:
        self._load_repos()

    def _refresh_repo_tags(self, repo: Repo) -> None:
        self._load_repos()

    # ── repo loading ────────────────────────────────────────────────────────

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

    def _set_scan_status(self, msg: str) -> None:
        self._scan_status = msg
        self._app.invalidate()
        threading.Timer(3.0, self._clear_scan_status).start()

    def _clear_scan_status(self) -> None:
        self._scan_status = ""
        self._app.invalidate()

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