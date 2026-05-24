from __future__ import annotations

import threading
import time
import webbrowser
from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, VSplit, Layout, Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl, UIContent, UIControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.styles import Style

from blink.models import Repo, RepoStatus
from blink.config import Config
from blink.store import Store
from blink.scanner import Scanner, ScanResult, StatusFetcher, check_pull_prereqs, parse_pull_output
from blink.tui.repo_list import RepoListControl, RepoListWindow
from blink.tui.search import SearchBar
from blink.tui.actions import EditorInfo, IDE_CHOICES, copy_path, detect_editors, open_in_editor
from blink.tui.detail import DetailPanel, _remote_to_https

_COMMIT_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_NARROW_THRESHOLD = 80


class _EditStatusControl(UIControl):
    def __init__(self, get_text, get_cursor_col):
        self._get_text = get_text
        self._get_cursor_col = get_cursor_col

    def is_focusable(self) -> bool:
        return True

    def create_content(self, width: int, height: int) -> UIContent:
        ft = self._get_text()
        show_cursor = False
        cursor_position = None
        col = self._get_cursor_col()
        if col is not None:
            show_cursor = True
            cursor_position = Point(x=col, y=0)

        def get_line(i: int):
            if i == 0:
                return ft
            return FormattedText([("", "")])

        return UIContent(
            get_line=get_line,
            line_count=1,
            show_cursor=show_cursor,
            cursor_position=cursor_position,
        )


class BlinkApp:
    def __init__(self, store: Store, scanner: Scanner, config: Config, is_first_run: bool = False) -> None:
        self._store = store
        self._scanner = scanner
        self._config = config
        self._editors: Dict[str, EditorInfo] = detect_editors()
        self._scanning = False
        self._scan_status = ""
        self._status_fetcher = StatusFetcher()
        self._fetching_status = False

        self._repo_control = RepoListControl(nerd_fonts=self._config.nerd_fonts)
        self._search_bar = SearchBar(
            on_change=self._on_search_change,
            focusable=Condition(lambda: self._search_active),
        )

        self._status_control = FormattedTextControl(text=self._status_text)
        self._footer_control = FormattedTextControl(text=self._footer_text)

        self._repo_list_window: Optional[RepoListWindow] = None
        self._detail_panel: Optional[DetailPanel] = None
        self._detail_window: Optional[Window] = None
        self._edit_status_window: Optional[Window] = None

        self._focus_pane: str = "list"  # "list" / "detail" / "edit"
        self._search_active: bool = False
        self._search_filtering: bool = False
        self._footer_highlight_until: float = 0.0

        self._last_ctrl_c: float = 0.0
        self._ctrl_c_quit_hint: bool = False

        self._ide_selecting: bool = False
        self._ide_select_cursor: int = 0
        self._ide_pending_repo: Optional[Repo] = None

        self._committing: bool = False
        self._commit_spinner_index: int = 0
        self._commit_spinner_timer: Optional[threading.Timer] = None

        self._pulling: bool = False
        self._pull_spinner_index: int = 0
        self._pull_spinner_timer: Optional[threading.Timer] = None

        self._load_repos()
        self._init_detail_panel()

        layout = self._build_layout()
        self._app = Application(
            layout=layout,
            key_bindings=self._build_key_bindings(),
            style=self._build_style(),
            full_screen=True,
            mouse_support=False,
        )

        # Focus the repo list after app is created
        if self._repo_list_window is not None:
            try:
                layout.focus(self._repo_list_window)
            except Exception:
                pass

        self._start_background_status_fetch()

    # ── edit mode helpers ────────────────────────────────────────────────────

    def _in_edit_mode(self) -> bool:
        if self._detail_panel is not None:
            return self._detail_panel.is_editing
        return False

    def _in_tag_mode(self) -> bool:
        if self._detail_panel is not None:
            return self._detail_panel.edit_mode == "tags"
        return False

    # ── IDE helpers ───────────────────────────────────────────────────────

    def _ide_options(self) -> List[tuple[str, str]]:
        return list(IDE_CHOICES)

    def _trigger_open_ide(self, repo: Repo) -> None:
        preferred = self._config.preferred_ide
        if preferred:
            open_in_editor(repo.path, preferred, self._editors)
        else:
            self._ide_pending_repo = repo
            self._ide_selecting = True
            self._ide_select_cursor = 0
            self._app.invalidate()

    def _edit_cursor_col(self) -> int | None:
        panel = self._detail_panel
        if panel is None or not panel.is_editing:
            return None
        mode = panel.edit_mode
        if mode == "alias" and panel.alias_buffer:
            return len(" Alias: ") + len(panel.alias_buffer.text)
        if mode == "description" and panel.desc_buffer:
            return len(" Desc: ") + len(panel.desc_buffer.text)
        if mode == "tags" and panel.tag_buffer:
            return len(" Tag: ") + len(panel.tag_buffer.text)
        return None

    # ── terminal width ────────────────────────────────────────────────────

    def _is_wide_enough(self) -> bool:
        try:
            cols = self._app.output.get_size().columns
            return cols >= _NARROW_THRESHOLD
        except Exception:
            return True

    # ── detail panel init & sync ───────────────────────────────────────────

    def _init_detail_panel(self) -> None:
        repo = self._repo_control.selected_repo()
        if repo is None:
            self._detail_panel = None
            return
        self._detail_panel = DetailPanel(
            repo=repo,
            store=self._store,
            editors=self._editors,
            on_back=lambda: None,
            on_alias_change=lambda alias: self._refresh_repo_alias(),
            on_tags_change=lambda: self._refresh_repo_tags(),
            on_status_message=self._set_scan_status,
            on_pin_change=lambda: self._refresh_repo_pin(),
            on_open_ide=lambda: self._trigger_open_ide(self._get_active_repo()),
            on_commit=lambda: self._run_commit(self._get_active_repo()),
            on_pull=lambda: self._run_pull(self._get_active_repo()),
            on_action=lambda: self._increment_view_count(),
            on_copy_path=lambda: self._copy_repo_path(),
            on_open_finder=lambda: self._open_finder(),
            on_open_git=lambda: self._open_git_in_browser(),
            on_add_task=lambda: self._run_add_task(),
        )

    def _sync_detail_panel(self) -> None:
        repo = self._repo_control.selected_repo()
        if repo is None:
            self._detail_panel = None
            return
        if self._detail_panel is None:
            self._init_detail_panel()
            return
        self._detail_panel.set_repo(repo)

    def _increment_view_count(self) -> None:
        repo = self._get_active_repo()
        if repo and repo.id is not None:
            self._store.increment_view_count(repo.id)
            repo.view_count += 1

    def _copy_repo_path(self) -> None:
        repo = self._get_active_repo()
        if repo:
            copy_path(repo.path)
            self._scan_status = f"Copied: {repo.path}"
            self._app.invalidate()
            self._start_timer(3.0, self._clear_scan_status)

    def _open_finder(self) -> None:
        repo = self._get_active_repo()
        if repo:
            open_in_editor(repo.path, "o", self._editors)

    def _open_git_in_browser(self) -> None:
        repo = self._get_active_repo()
        if not repo:
            return
        if not repo.remotes:
            self._set_scan_status("No remote URL")
            return
        https = _remote_to_https(repo.remotes[0].url)
        if not https:
            self._set_scan_status("Cannot convert remote URL to HTTPS")
            return
        webbrowser.open(https)
        self._set_scan_status(f"Opened: {https}")

    def _run_add_task(self) -> None:
        repo = self._get_active_repo()
        if not repo:
            return

        def do_add_task():
            try:
                from blink.loop.cmd_edit import _add_task
                msg = _add_task(repo.path)
                status = f"✓ {msg}" if msg else "✓ Task 已更新"
                self._start_timer(0.1, lambda: self._set_scan_status(status, timeout=5.0))
            except Exception:
                self._start_timer(0.1, lambda: self._set_scan_status("✗ Task 添加失败", timeout=5.0))

        t = threading.Thread(target=do_add_task, daemon=True)
        t.start()

    # ── layouts ─────────────────────────────────────────────────────────────

    def _left_border_style(self) -> str:
        return "class:border-focus" if self._focus_pane == "list" else "class:border"

    def _right_border_style(self) -> str:
        return "class:border-focus" if self._focus_pane == "detail" else "class:border"

    def _build_layout(self) -> Layout:
        self._repo_list_window = RepoListWindow(self._repo_control)
        self._detail_window = Window(
            content=self._detail_panel,
            style="class:detail-panel",
            height=D(min=1),
        )
        self._edit_status_window = Window(
            content=_EditStatusControl(self._status_text, self._edit_cursor_col),
            height=D.exact(1),
            style="class:status",
        )

        # Left panel: repo list with borders
        left_panel = HSplit([
            Window(height=D.exact(1), char="─", style=self._left_border_style),
            self._repo_list_window,
            Window(height=D.exact(1), char="─", style=self._left_border_style),
        ], width=D(min=20, preferred=40, max=60))

        # Right panel: detail with borders
        right_panel = ConditionalContainer(
            HSplit([
                Window(height=D.exact(1), char="─", style=self._right_border_style),
                self._detail_window,
                Window(height=D.exact(1), char="─", style=self._right_border_style),
            ]),
            filter=Condition(lambda: self._detail_panel is not None and self._is_wide_enough()),
        )

        # Vertical separator
        v_sep = Window(char="│", style="class:border", width=D.exact(1))
        v_sep_cond = ConditionalContainer(
            v_sep,
            filter=Condition(lambda: self._detail_panel is not None and self._is_wide_enough()),
        )

        main_area = VSplit([left_panel, v_sep_cond, right_panel])

        # Edit status overlay
        edit_status = ConditionalContainer(
            self._edit_status_window,
            filter=Condition(lambda: self._in_edit_mode()),
        )
        regular_status = ConditionalContainer(
            Window(content=self._status_control, height=D.exact(1), style="class:status"),
            filter=Condition(lambda: not self._in_edit_mode()),
        )

        return Layout(
            HSplit([
                # Search area
                ConditionalContainer(
                    Window(
                        content=FormattedTextControl(text=self._search_prefix_text),
                        height=D.exact(1),
                        style="class:search-bar",
                    ),
                    filter=Condition(lambda: self._search_filtering and not self._search_active),
                ),
                ConditionalContainer(
                    HSplit([
                        Window(height=D.exact(1), char="─", style="class:search-border"),
                        self._search_bar.window,
                        Window(height=D.exact(1), char="─", style="class:search-border"),
                    ]),
                    filter=Condition(lambda: self._search_active),
                ),
                # Main content
                main_area,
                # Status bar
                edit_status,
                regular_status,
                # Footer
                Window(content=self._footer_control, height=D.exact(1), style="class:footer"),
            ])
        )

    # ── styles ───────────────────────────────────────────────────────────────

    def _build_style(self) -> Style:
        return Style.from_dict({
            "search-bar": "fg:#c9d1d9",
            "search-input": "fg:#c9d1d9",
            "search-border": "fg:#58a6ff",
            "search-prefix": "fg:#58a6ff",
            "repo-list": "",
            "normal": "fg:#e6edf3 bold",
            "repo-name": "fg:#e6edf3 bold",
            "dim": "fg:#484f58",
            "alias": "fg:#8b949e",
            "path": "fg:#484f58",
            "repo-path-dim": "fg:#484f58",
            "tag": "fg:#3fb950",
            "tag-bracket": "fg:#238636",
            "indicator": "fg:#58a6ff bold bg:#264f78",
            "repo-selected": "fg:#f0f6fc bg:#264f78",
            "selected-dim": "fg:#8db9e2 bg:#264f78",
            "selected-tag": "fg:#7ee787 bg:#264f78",
            "selected-tag-bracket": "fg:#3fb950 bg:#264f78",
            "empty": "fg:#484f58 italic",
            "border": "fg:#30363d",
            "border-focus": "fg:#58a6ff",
            "status": "",
            "status-label": "fg:#8b949e",
            "status-value": "fg:#c9d1d9",
            "status-accent": "fg:#58a6ff",
            "status-dim": "fg:#6e7681",
            "footer": "",
            "footer-key": "bold fg:#79c0ff",
            "footer-dim": "fg:#8b949e",
            "footer-dim-key": "bold fg:#58a6ff",
            "footer-highlight": "fg:#f0f6fc",
            "search-keyword": "fg:#8b949e",
            "detail-panel": "fg:#c9d1d9",
            "label": "bold fg:#58a6ff",
            "detail-label-sel": "bold fg:#58a6ff bg:#264f78",
            "detail-sep": "fg:#30363d",
            "detail-selected": "fg:#f0f6fc bg:#264f78",
            "detail-indicator": "fg:#58a6ff bold bg:#264f78",
            "detail-tag": "fg:#3fb950",
            "detail-tag-bracket": "fg:#238636",
            "status-clean": "fg:#3fb950",
            "status-dirty": "fg:#f0883e",
            "status-ahead-behind": "fg:#d29922",
            "status-loading": "fg:#484f58",
            "status-clean-sel": "fg:#3fb950 bg:#264f78",
            "status-dirty-sel": "fg:#f0883e bg:#264f78",
            "status-ahead-behind-sel": "fg:#d29922 bg:#264f78",
            "status-loading-sel": "fg:#484f58 bg:#264f78",
            "detail-shortcut-key": "bold fg:#79c0ff",
            "detail-shortcut-dim": "fg:#8b949e",
        })

    # ── key bindings ─────────────────────────────────────────────────────────

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        # ── IDE selection mode (highest priority) ───────────────────────────
        @kb.add("left", filter=Condition(lambda: self._ide_selecting))
        def _(event):
            self._ide_select_cursor = max(0, self._ide_select_cursor - 1)
            self._app.invalidate()

        @kb.add("right", filter=Condition(lambda: self._ide_selecting))
        def _(event):
            opts = self._ide_options()
            self._ide_select_cursor = min(len(opts) - 1, self._ide_select_cursor + 1)
            self._app.invalidate()

        @kb.add("enter", eager=True, filter=Condition(lambda: self._ide_selecting))
        def _(event):
            opts = self._ide_options()
            if opts and 0 <= self._ide_select_cursor < len(opts):
                key, name = opts[self._ide_select_cursor]
                self._config.set("preferred_ide", key)
                self._ide_selecting = False
                repo = self._ide_pending_repo
                self._ide_pending_repo = None
                if repo:
                    open_in_editor(repo.path, key, self._editors)
                    self._set_scan_status(f"正在打开 {name}...")
                else:
                    self._app.invalidate()
            return

        @kb.add("escape", eager=True, filter=Condition(lambda: self._ide_selecting))
        def _(event):
            self._ide_selecting = False
            self._ide_pending_repo = None
            self._app.invalidate()
            return

        @kb.add("c-c", eager=True, filter=Condition(lambda: self._ide_selecting))
        def _(event):
            self._ide_selecting = False
            self._ide_pending_repo = None
            self._app.invalidate()
            return

        # ── Ctrl+C ──────────────────────────────────────────────────────────
        @kb.add("c-c")
        def _(event):
            if self._ide_selecting:
                return
            # Priority: edit mode → search → double-quit
            if self._in_edit_mode():
                self._cancel_edit()
                return
            if self._search_active:
                self._cancel_search()
                return
            if self._search_filtering:
                self._cancel_search()
                return
            # Double Ctrl+C to quit
            now = time.monotonic()
            if self._ctrl_c_quit_hint and (now - self._last_ctrl_c) < 2.0:
                event.app.exit()
                return
            self._last_ctrl_c = now
            self._ctrl_c_quit_hint = True
            self._app.invalidate()
            self._start_timer(2.0, self._reset_ctrl_c_hint)

        # ── Escape ───────────────────────────────────────────────────────────
        @kb.add("escape")
        def _(event):
            if self._ide_selecting:
                return
            if self._in_edit_mode():
                self._cancel_edit()
                return
            if self._search_active:
                self._cancel_search()
                return
            if self._search_filtering:
                self._cancel_search()
                return
            # If focus is on detail, return to list
            if self._focus_pane == "detail":
                self._focus_pane = "list"
                self._app.layout.focus(self._repo_list_window)
                self._app.invalidate()

        # ── Focus switching: Tab/→ → detail, ← → list ────────────────────
        @kb.add(Keys.Tab, filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            if self._detail_panel is not None and self._focus_pane == "list":
                self._focus_pane = "detail"
                self._detail_panel.set_repo(self._repo_control.selected_repo())
                self._app.layout.focus(self._detail_window)
                self._app.invalidate()

        @kb.add("right", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting and self._focus_pane == "list"))
        def _(event):
            if self._detail_panel is not None:
                self._focus_pane = "detail"
                self._detail_panel.set_repo(self._repo_control.selected_repo())
                self._app.layout.focus(self._detail_window)
                self._app.invalidate()

        @kb.add("left", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting and self._focus_pane == "detail"))
        def _(event):
            self._focus_pane = "list"
            self._app.layout.focus(self._repo_list_window)
            self._app.invalidate()

        # ── Arrow keys — confirm search on down ────────────────────────────
        @kb.add("down", filter=Condition(lambda: self._search_active))
        @kb.add("s-down", filter=Condition(lambda: self._search_active))
        def _(event):
            self._search_active = False
            if self._search_bar.text:
                self._search_filtering = True
            self._focus_pane = "list"
            self._app.layout.focus(self._repo_list_window)
            self._app.invalidate()
            return

        # ── Arrow keys — list view navigation ───────────────────────────────
        @kb.add("down", filter=Condition(lambda: not self._search_active and self._focus_pane == "list" and not self._ide_selecting))
        @kb.add("s-down", filter=Condition(lambda: not self._search_active and self._focus_pane == "list" and not self._ide_selecting))
        def _(event):
            self._repo_control.move_down()
            self._sync_detail_panel()
            self._app.invalidate()

        @kb.add("up", filter=Condition(lambda: not self._search_active and self._focus_pane == "list" and not self._ide_selecting))
        @kb.add("s-up", filter=Condition(lambda: not self._search_active and self._focus_pane == "list" and not self._ide_selecting))
        def _(event):
            self._repo_control.move_up()
            self._sync_detail_panel()
            self._app.invalidate()

        # ── Arrow keys — detail view line navigation ──────────────────────────
        @kb.add("down", filter=Condition(lambda: self._focus_pane == "detail" and not self._search_active and not self._ide_selecting and not self._in_edit_mode()))
        def _(event):
            if self._detail_panel:
                self._detail_panel.cursor_down()
                self._app.invalidate()

        @kb.add("up", filter=Condition(lambda: self._focus_pane == "detail" and not self._search_active and not self._ide_selecting and not self._in_edit_mode()))
        def _(event):
            if self._detail_panel:
                self._detail_panel.cursor_up()
                self._app.invalidate()

        # ── Search (available from both panes) ───────────────────────────────
        @kb.add("/", filter=Condition(lambda: not self._search_active and not self._in_edit_mode()))
        def _(event):
            self._search_active = True
            self._search_filtering = False
            self._search_bar.clear()
            self._search_bar.focus(event.app)
            self._app.invalidate()

        # ── Shift+I — open with preferred IDE ──────────────────────────────
        @kb.add("I", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                self._trigger_open_ide(repo)

        # ── Shift+O — open with system default ─────────────────────────────
        @kb.add("O", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                open_in_editor(repo.path, "o", self._editors)

        @kb.add("P", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                copy_path(repo.path)
                self._scan_status = f"Copied: {repo.path}"
                self._app.invalidate()
                self._start_timer(5.0, self._clear_scan_status)

        @kb.add("R", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            if not self._scanning:
                self._start_background_scan()

        @kb.add("C", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                self._run_commit(repo)

        @kb.add("U", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            repo = self._get_active_repo()
            if repo:
                self._run_pull(repo)

        # ── Shift+G — open in browser ────────────────────────────────────
        @kb.add("G", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            self._open_git_in_browser()

        # ── Shift+T — add todo task ──────────────────────────────────────
        @kb.add("T", filter=Condition(lambda: not self._search_active and not self._in_edit_mode() and not self._ide_selecting))
        def _(event):
            self._trigger_footer_highlight()
            self._run_add_task()

        # ── Enter ────────────────────────────────────────────────────────────
        @kb.add("enter")
        def _(event):
            if self._ide_selecting:
                return
            if self._search_active:
                self._search_active = False
                if self._search_bar.text:
                    self._search_filtering = True
                self._focus_pane = "list"
                self._app.layout.focus(self._repo_list_window)
                self._app.invalidate()
                return
            if self._focus_pane in ("detail", "edit") and self._detail_panel is not None:
                self._detail_panel.handle_enter()
                if self._detail_panel.is_editing:
                    self._focus_pane = "edit"
                    self._app.layout.focus(self._edit_status_window)
                else:
                    self._focus_pane = "detail"
                    self._app.layout.focus(self._detail_window)
                self._app.invalidate()
                return
            # List pane Enter = open IDE (same as Shift+I)
            if self._focus_pane == "list":
                repo = self._repo_control.selected_repo()
                if repo:
                    self._trigger_open_ide(repo)

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

    def _cancel_edit(self) -> None:
        if self._detail_panel is not None:
            self._detail_panel._edit_mode = None
            self._detail_panel._alias_buffer = None
            self._detail_panel._desc_buffer = None
            self._detail_panel._tag_buffer = None
            self._focus_pane = "detail"
            self._app.layout.focus(self._detail_window)
            self._app.invalidate()

    def _cancel_search(self) -> None:
        self._search_bar.clear()
        self._search_active = False
        self._search_filtering = False
        self._load_repos()
        self._sync_detail_panel()
        self._focus_pane = "list"
        self._app.layout.focus(self._repo_list_window)
        self._app.invalidate()

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
        return self._repo_control.selected_repo()

    # ── search ───────────────────────────────────────────────────────────────

    def _search_prefix_text(self) -> FormattedText:
        if self._search_filtering and self._search_bar.text:
            return FormattedText([
                ("class:search-prefix", " / "),
                ("class:search-keyword", self._search_bar.text),
            ])
        return FormattedText([("class:search-prefix", " /")])

    # ── status text ─────────────────────────────────────────────────────────

    def _status_text(self) -> FormattedText:
        if self._ide_selecting:
            opts = self._ide_options()
            parts: list[tuple[str, str]] = [("class:status-label", " Select IDE:  ")]
            for i, (key, name) in enumerate(opts):
                if i > 0:
                    parts.append(("class:status-dim", "  "))
                if i == self._ide_select_cursor:
                    parts.append(("class:status-accent", f"▸ {name}"))
                else:
                    parts.append(("class:status-dim", f"  {name}"))
            parts.append(("class:status-dim", "    "))
            parts.append(("class:footer-dim", "←→:选择  Enter:确认  Esc:取消"))
            return FormattedText(parts)
        if self._pulling:
            frame = _COMMIT_SPINNER_FRAMES[self._pull_spinner_index]
            return FormattedText([
                ("class:status-accent", f" {frame} "),
                ("class:status-label", "正在拉取..."),
            ])
        if self._committing:
            frame = _COMMIT_SPINNER_FRAMES[self._commit_spinner_index]
            return FormattedText([
                ("class:status-accent", f" {frame} "),
                ("class:status-label", "正在提交..."),
            ])
        if self._detail_panel is not None and self._detail_panel.is_editing:
            mode = self._detail_panel.edit_mode
            if mode == "alias" and self._detail_panel.alias_buffer:
                return FormattedText([
                    ("class:status-label", " Alias: "),
                    ("class:status-value", self._detail_panel.alias_buffer.text),
                    ("", " "),
                ])
            if mode == "description" and self._detail_panel.desc_buffer:
                return FormattedText([
                    ("class:status-label", " Desc: "),
                    ("class:status-value", self._detail_panel.desc_buffer.text),
                    ("", " "),
                ])
            if mode == "tags" and self._detail_panel.tag_buffer:
                return FormattedText([
                    ("class:status-label", " Tag: "),
                    ("class:status-value", self._detail_panel.tag_buffer.text),
                    ("", " "),
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
        if self._fetching_status:
            return FormattedText([
                ("class:status-accent", " ⟳ "),
                ("class:status-label", "Loading status…"),
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
        if self._ide_selecting:
            return self._styled_footer_hints([
                ("←→", "选择"), ("Enter", "确认"), ("Esc", "取消"),
            ])
        highlighted = time.monotonic() < self._footer_highlight_until
        style_key = "class:footer-key" if highlighted else "class:footer-dim-key"
        style_dim = "class:footer-highlight" if highlighted else "class:footer-dim"
        hints = [
            ("Enter", "ide"), ("/", "search"),
            ("Tab", "focus"),
            ("Shift+R", "rescan"), ("Shift+G", "browser"),
            ("Shift+T", "task"), ("Shift+U", "pull"),
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

    def _start_timer(self, interval: float, func: object) -> None:
        t = threading.Timer(interval, func)
        t.daemon = True
        t.start()

    def _reset_footer_highlight(self) -> None:
        self._footer_highlight_until = 0.0
        self._app.invalidate()

    def _trigger_footer_highlight(self) -> None:
        self._footer_highlight_until = time.monotonic() + 2.0
        self._app.invalidate()
        self._start_timer(2.0, self._reset_footer_highlight)

    def _tick_commit_spinner(self) -> None:
        if not self._committing:
            return
        self._commit_spinner_index = (self._commit_spinner_index + 1) % len(_COMMIT_SPINNER_FRAMES)
        self._app.invalidate()
        self._commit_spinner_timer = threading.Timer(0.12, self._tick_commit_spinner)
        self._commit_spinner_timer.daemon = True
        self._commit_spinner_timer.start()

    def _stop_commit_spinner(self) -> None:
        if self._commit_spinner_timer:
            self._commit_spinner_timer.cancel()
            self._commit_spinner_timer = None
        self._committing = False
        self._commit_spinner_index = 0

    def _run_pull(self, repo: Repo) -> None:
        import subprocess as sp
        if self._pulling:
            return
        ok, msg = check_pull_prereqs(repo)
        if not ok:
            self._scan_status = msg
            self._app.invalidate()
            self._start_timer(3.0, self._clear_scan_status)
            return
        self._pulling = True
        self._pull_spinner_index = 0
        self._tick_pull_spinner()

        def do_pull() -> None:
            try:
                result = sp.run(
                    ["git", "pull"],
                    cwd=repo.path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                success, message = parse_pull_output(result.stdout, result.returncode, result.stderr)
            except sp.TimeoutExpired:
                success, message = False, "✗ Pull timed out"
            except Exception as exc:
                success, message = False, f"✗ Pull failed: {exc}"

            def on_done():
                self._stop_pull_spinner()
                if success:
                    self._refresh_repo_status(repo)
                self._scan_status = message
                self._app.invalidate()
                self._start_timer(3.0, self._clear_scan_status)

            self._start_timer(0.1, on_done)

        t = threading.Thread(target=do_pull, daemon=True)
        t.start()

    def _tick_pull_spinner(self) -> None:
        if not self._pulling:
            return
        self._pull_spinner_index = (self._pull_spinner_index + 1) % len(_COMMIT_SPINNER_FRAMES)
        self._app.invalidate()
        self._pull_spinner_timer = threading.Timer(0.12, self._tick_pull_spinner)
        self._pull_spinner_timer.daemon = True
        self._pull_spinner_timer.start()

    def _stop_pull_spinner(self) -> None:
        if self._pull_spinner_timer:
            self._pull_spinner_timer.cancel()
            self._pull_spinner_timer = None
        self._pulling = False
        self._pull_spinner_index = 0

    # ── repo refresh helpers ────────────────────────────────────────────────

    def _refresh_repo_alias(self) -> None:
        self._load_repos()
        self._sync_detail_panel()

    def _refresh_repo_tags(self) -> None:
        self._load_repos()
        self._sync_detail_panel()

    def _refresh_repo_pin(self) -> None:
        self._load_repos()
        self._sync_detail_panel()

    # ── repo loading ────────────────────────────────────────────────────────

    def _on_search_change(self, text: str) -> None:
        repos = self._store.search_repos(text)
        self._repo_control.set_repos(repos)
        self._sync_detail_panel()
        self._app.invalidate()

    def _load_repos(self) -> None:
        repos = self._store.search_repos(self._search_bar.text)
        self._repo_control.set_repos(repos, reset_selection=False)

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
            self._sync_detail_panel()

        def done(results: List[ScanResult]) -> None:
            self._scanning = False
            self._scan_status = f"Scan complete — {len(results)} repos found"
            self._app.invalidate()
            self._start_background_status_fetch()

        def run() -> None:
            results = self._scanner.run_scan(blocking=True, on_result=on_result)
            done(results)

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _set_scan_status(self, msg: str, timeout: float = 3.0) -> None:
        self._scan_status = msg
        self._app.invalidate()
        self._start_timer(timeout, self._clear_scan_status)

    def _run_commit(self, repo: Repo) -> None:
        if self._committing:
            return
        self._committing = True
        self._commit_spinner_index = 0
        self._tick_commit_spinner()

        def do_commit():
            try:
                from blink.loop.git_ops import is_git_repo, is_git_clean, ensure_clean_git
                if not is_git_repo(repo.path):
                    return False, "✗ 不是 Git 仓库"
                if is_git_clean(repo.path):
                    return True, "✓ 工作树已干净"
                success = ensure_clean_git(repo.path, "manual commit", model="haiku")
                if success:
                    return True, "✓ 提交完成"
                return False, "✗ 提交失败"
            except FileNotFoundError:
                return False, "✗ claude CLI 未安装"
            except Exception as exc:
                return False, f"✗ 提交失败: {exc}"

        def on_done():
            success, message = do_commit()
            self._stop_commit_spinner()
            if success:
                self._refresh_repo_status(repo)
            self._scan_status = message
            self._app.invalidate()
            self._start_timer(3.0, self._clear_scan_status)

        t = threading.Thread(target=on_done, daemon=True)
        t.start()

    def _refresh_repo_status(self, repo: Repo) -> None:
        if repo.id is None:
            return
        fetcher = StatusFetcher()
        fetcher.run_fetch(
            repos=[(repo.id, repo.path)],
            blocking=True,
            on_status=lambda rid, status: self._store.upsert_status(rid, status),
            on_error=lambda rid: None,
            on_done=lambda: None,
        )
        self._load_repos()
        self._sync_detail_panel()
        self._scan_status = ""
        self._app.invalidate()

    def _clear_scan_status(self) -> None:
        self._scan_status = ""
        self._app.invalidate()

    def _start_background_status_fetch(self) -> None:
        repos = self._store.get_all_repos()
        if not repos:
            return
        repo_items = [(r.id, r.path) for r in repos if r.id is not None]
        if not repo_items:
            return

        self._fetching_status = True
        self._repo_control.error_repo_ids.clear()
        self._app.invalidate()

        def on_status(repo_id: int, status: RepoStatus) -> None:
            self._store.upsert_status(repo_id, status)
            self._load_repos()
            self._sync_detail_panel()
            self._app.invalidate()

        def on_error(repo_id: int) -> None:
            self._repo_control.error_repo_ids.add(repo_id)
            self._app.invalidate()

        def on_done() -> None:
            self._fetching_status = False
            self._app.invalidate()

        self._status_fetcher.run_fetch(
            repos=repo_items,
            blocking=False,
            on_status=on_status,
            on_error=on_error,
            on_done=on_done,
        )

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
