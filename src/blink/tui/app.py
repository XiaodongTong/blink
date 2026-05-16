from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText

from blink.models import Repo
from blink.store import Store
from blink.scanner import Scanner, ScanResult
from blink.tui.repo_list import RepoListControl, RepoListWindow
from blink.tui.search import SearchBar
from blink.tui.actions import EditorInfo, copy_path, detect_editors, open_in_editor


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

        self._layout = Layout(
            HSplit([
                Window(
                    content=FormattedTextControl(text=lambda: FormattedText([("class:label", " Search: ")])),
                    height=D.exact(1),
                    style="class:label",
                ),
                self._search_bar.window,
                Window(height=D.exact(1), char="─", style="class:border"),
                RepoListWindow(self._repo_control),
                Window(height=D.exact(1), char="─", style="class:border"),
                Window(content=self._status_control, height=D.exact(1), style="class:status"),
                Window(content=self._footer_control, height=D.exact(1), style="class:footer"),
            ])
        )

        self._app = Application(
            layout=self._layout,
            key_bindings=self._build_key_bindings(),
            style=self._build_style(),
            full_screen=True,
            mouse_support=False,
        )

        self._load_repos()

    def _build_style(self) -> Style:
        return Style.from_dict({
            "selected": "reverse",
            "normal": "",
            "search-bar": "",
            "status": "bg:#333333 #cccccc",
            "footer": "bg:#222222 #888888",
            "label": "bold",
            "border": "#555555",
            "repo-list": "",
        })

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("q")
        def _(event):
            event.app.exit()

        @kb.add("escape")
        def _(event):
            if self._search_bar.text:
                self._search_bar.clear()
                self._load_repos()
            else:
                event.app.exit()

        @kb.add("j")
        @kb.add("down")
        def _(event):
            self._repo_control.move_down()
            self._app.invalidate()

        @kb.add("k")
        @kb.add("up")
        def _(event):
            self._repo_control.move_up()
            self._app.invalidate()

        @kb.add("/")
        def _(event):
            self._search_bar.focus(event.app)

        for key in ("v", "u", "a", "o"):
            def make_handler(k):
                def _(event):
                    repo = self._repo_control.selected_repo()
                    if repo:
                        open_in_editor(repo.path, k, self._editors)
                return _
            kb.add(key)(make_handler(key))

        @kb.add("y")
        def _(event):
            repo = self._repo_control.selected_repo()
            if repo:
                copy_path(repo.path)
                self._scan_status = f"Copied: {repo.path}"
                self._app.invalidate()

        @kb.add("r")
        def _(event):
            if not self._scanning:
                self._start_background_scan()

        @kb.add("enter")
        def _(event):
            repo = self._repo_control.selected_repo()
            if repo:
                self._scan_status = f"Detail view coming in P1 — {repo.name}"
                self._app.invalidate()

        return kb

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

    def _status_text(self) -> FormattedText:
        count = len(self._repo_control.repos)
        status = self._scan_status if self._scanning else f"{count} repo{'s' if count != 1 else ''}"
        return FormattedText([("", f" {status}")])

    def _footer_text(self) -> FormattedText:
        parts = ["j/k:nav", "Enter:detail", "/:search", "v:code", "u:cursor", "a:antigravity", "o:open", "y:yank", "r:rescan", "q:quit"]
        return FormattedText([("", " " + "  ".join(parts))])

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
