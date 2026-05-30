from __future__ import annotations

import os
import shlex
import subprocess as sp
import threading
import time
import webbrowser
from typing import Callable, Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.formatted_text import FormattedText

from blink.models import Repo, RepoStatus
from blink import logger
from blink.config import Config
from blink.store import Store
from blink.scanner import Scanner
from blink.tui.widgets.repo_list import RepoListControl
from blink.tui.widgets.search import SearchBar
from blink.tui.actions import EditorInfo, IDE_CHOICES, detect_editors, find_editor_by_name, open_in_editor, open_terminal
from blink.tui.widgets.detail import DetailPanel, _remote_to_https
from blink.tui.styles import build_style
from blink.tui.layout import build_layout, EditStatusControl
from blink.tui.key_bindings import build_key_bindings
from blink.tui.status_bar import build_status_text, build_search_prefix_text, build_footer_text
from blink.tui.app_review import ReviewOrchestrator
from blink.tui.app_actions import AppActionsMixin
from blink.tui.app_config import ConfigPanel, ConfigSelectMode


class BlinkApp(AppActionsMixin):
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

        self._repo_list_window = None
        self._detail_panel: Optional[DetailPanel] = None
        self._detail_window: Optional[Window] = None
        self._edit_status_window: Optional[Window] = None

        self._focus_pane: str = "list"
        self._search_active: bool = False
        self._search_filtering: bool = False
        self._footer_highlight_until: float = 0.0
        self._last_ctrl_c: float = 0.0
        self._ctrl_c_quit_hint: bool = False

        self._ide_selecting: bool = False
        self._ide_select_cursor: int = 0
        self._ide_scroll_offset: int = 0
        self._ide_pending_path: Optional[str] = None
        self._committing_paths: set[str] = set()
        self._pulling_paths: set[str] = set()

        self._review = ReviewOrchestrator(self)

        self._config_panel: Optional[ConfigPanel] = None
        self._config_selecting: bool = False
        self._pre_config_focus: str = "list"

        self._load_repos()
        self._init_detail_panel()
        logger.log("tui", "Blink TUI 启动")

        self._edit_status_window = Window(
            content=EditStatusControl(self._status_text, self._edit_cursor_col),
            height=D.exact(1), style="class:status",
        )
        self._detail_window = Window(
            content=self._detail_panel,
            style="class:detail-panel", height=D(min=1),
        )

        layout = build_layout(self)
        self._app = Application(
            layout=layout,
            key_bindings=build_key_bindings(self),
            style=build_style(),
            full_screen=True, mouse_support=True,
        )

        if self._repo_list_window is not None:
            try:
                layout.focus(self._repo_list_window)
            except Exception:
                pass
        self._start_background_status_fetch()

    # ── focus & edit mode ───────────────────────────────────────────────

    def _set_focus(self, pane: str) -> None:
        self._focus_pane = pane

    def _in_edit_mode(self) -> bool:
        if self._review.selecting or self._review.branch_loading:
            return True
        if self._detail_panel is not None:
            return self._detail_panel.is_editing
        return False

    def _in_tag_mode(self) -> bool:
        if self._detail_panel is not None:
            return self._detail_panel.edit_mode == "tags"
        return False

    # ── IDE helpers ─────────────────────────────────────────────────────

    def _ide_options(self) -> list[tuple[str, str]]:
        return list(IDE_CHOICES)

    def _open_with_ide(self, path: str) -> None:
        preferred = self._config.editor
        if preferred:
            key = find_editor_by_name(preferred, self._editors)
            if key:
                info = self._editors.get(key)
                if info and info.available:
                    open_in_editor(path, key, self._editors)
                else:
                    self._config.set("editor", None)
                    self._ide_pending_path = path
                    self._ide_selecting = True
                    self._ide_select_cursor = 0
                    self._ide_scroll_offset = 0
                    self._app.invalidate()
            else:
                self._config.set("editor", None)
                self._ide_pending_path = path
                self._ide_selecting = True
                self._ide_select_cursor = 0
                self._ide_scroll_offset = 0
                self._app.invalidate()
        else:
            self._ide_pending_path = path
            self._ide_selecting = True
            self._ide_select_cursor = 0
            self._ide_scroll_offset = 0
            self._app.invalidate()

    def _trigger_open_ide(self, repo: Repo) -> None:
        self._open_with_ide(repo.path)

    def _edit_cursor_col(self) -> int | None:
        if self._review.selecting or self._review.branch_loading:
            return None
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

    # ── detail panel ────────────────────────────────────────────────────

    def _init_detail_panel(self) -> None:
        repo = self._repo_control.selected_repo()
        if repo is None:
            self._detail_panel = None
            return
        self._detail_panel = DetailPanel(
            repo=repo, store=self._store, editors=self._editors,
            on_back=lambda: None,
            on_alias_change=lambda _: self._refresh_repo(),
            on_tags_change=lambda: self._refresh_repo(),
            is_focused=lambda: self._focus_pane in ("detail", "edit"),
            on_status_message=self._set_scan_status,
            on_pin_change=lambda: self._refresh_repo(),
            on_open_ide=lambda: self._trigger_open_ide(self._get_active_repo()),
            on_commit=lambda: self._run_commit(self._get_active_repo()),
            on_pull=lambda: self._run_pull(self._get_active_repo()),
            on_action=lambda: self._increment_view_count(),
            on_open_finder=lambda: self._open_finder(),
            on_open_git=lambda: self._open_git_in_browser(),
            on_add_task=lambda: self._run_add_task(),
            on_review=lambda: self._start_review_branch_select(),
            on_open_terminal=lambda: self._open_terminal(),
            on_copy_path=lambda: self._copy_path(),
            on_open_report=lambda: self._open_review_report(),
            last_report_paths=self._review.last_report_paths,
        )

    def _sync_detail_panel(self) -> None:
        repo = self._repo_control.selected_repo()
        if repo is None:
            return
        if self._detail_panel is None:
            self._init_detail_panel()
            if self._detail_window is not None and self._detail_panel is not None:
                self._detail_window.content = self._detail_panel
            return
        self._detail_panel.set_repo(repo)

    def _increment_view_count(self) -> None:
        repo = self._get_active_repo()
        if repo and repo.id is not None:
            self._store.increment_view_count(repo.id)
            repo.view_count += 1

    def _open_finder(self) -> None:
        repo = self._get_active_repo()
        if repo:
            open_in_editor(repo.path, "o", self._editors)

    def _open_review_report(self) -> None:
        repo = self._get_active_repo()
        if repo and repo.path in self._review.last_report_paths:
            self._open_with_ide(self._review.last_report_paths[repo.path])

    def _open_terminal(self) -> None:
        repo = self._get_active_repo()
        if repo:
            if open_terminal(repo.path):
                self._set_scan_status(f"✓ 已打开终端: {repo.path}")
            else:
                self._set_scan_status("✗ 无法打开终端")

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

    def _copy_path(self) -> None:
        repo = self._get_active_repo()
        if not repo:
            return
        try:
            proc = sp.Popen(["pbcopy"], stdin=sp.PIPE)
            proc.communicate(repo.path.encode("utf-8"))
            self._set_scan_status(f"复制了 {repo.path}")
        except Exception:
            self._set_scan_status("复制失败")

    # ── config panel ────────────────────────────────────────────────────

    def _enter_config(self) -> None:
        self._pre_config_focus = self._focus_pane
        self._config_panel = ConfigPanel(self._config, self._editors)
        if self._detail_window is not None:
            self._detail_window.content = self._config_panel
        self._set_focus("config")
        self._config_selecting = False
        try:
            self._app.layout.focus(self._detail_window)
        except Exception:
            pass
        self._app.invalidate()

    def _exit_config(self) -> None:
        self._config_panel = None
        self._config_selecting = False
        self._init_detail_panel()
        if self._detail_window is not None:
            self._detail_window.content = self._detail_panel
        prev = self._pre_config_focus
        self._set_focus(prev)
        if prev == "detail" and self._detail_panel is not None:
            try:
                self._app.layout.focus(self._detail_window)
            except Exception:
                pass
        else:
            try:
                self._app.layout.focus(self._repo_list_window)
            except Exception:
                pass
        self._app.invalidate()

    def _open_config_in_editor(self) -> None:
        editor_cmd = os.environ.get("EDITOR", "vi")
        config_path = str(self._config._path)
        try:
            sp.call(shlex.split(editor_cmd) + [config_path])
        except Exception:
            self._set_scan_status("✗ 无法打开编辑器")
            return
        self._config._load()
        if self._config_panel is not None:
            self._config_panel.reload()
        self._app.invalidate()
        self._set_scan_status("✓ 配置已重新加载")

    # ── review delegation ───────────────────────────────────────────────

    def _start_review_branch_select(self) -> None:
        repo = self._get_active_repo()
        if repo:
            self._review.start_branch_select(repo)

    def _cancel_review(self) -> None: self._review.cancel()
    def _confirm_review_branch(self) -> None: self._review.confirm_branch()

    # ── text rendering delegation ───────────────────────────────────────

    def _status_text(self) -> FormattedText: return build_status_text(self)
    def _search_prefix_text(self) -> FormattedText: return build_search_prefix_text(self)
    def _footer_text(self) -> FormattedText: return build_footer_text(self)

    # ── cancel helpers ──────────────────────────────────────────────────

    def _cancel_edit(self) -> None:
        if self._detail_panel is not None:
            self._detail_panel._edit_mode = None
            self._detail_panel._alias_buffer = None
            self._detail_panel._desc_buffer = None
            self._detail_panel._tag_buffer = None
            self._set_focus("detail")
            self._app.layout.focus(self._detail_window)
            self._app.invalidate()

    def _cancel_search(self) -> None:
        self._search_bar.clear()
        self._search_active = False
        self._search_filtering = False
        self._load_repos()
        self._sync_detail_panel()
        self._set_focus("list")
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

    # ── repo helpers ────────────────────────────────────────────────────

    def _get_active_repo(self) -> Optional[Repo]: return self._repo_control.selected_repo()
    def _refresh_repo(self) -> None: self._load_repos(); self._sync_detail_panel()

    # ── repo loading & search ───────────────────────────────────────────

    def _on_search_change(self, text: str) -> None:
        self._repo_control.set_repos(self._store.search_repos(text))
        self._sync_detail_panel()
        self._app.invalidate()

    def _load_repos(self) -> None:
        repos = self._store.search_repos(self._search_bar.text)
        self._repo_control.set_repos(repos, reset_selection=False)

    # ── timer & status helpers ──────────────────────────────────────────

    def _set_scan_status(self, msg: str, timeout: float = 3.0) -> None:
        self._scan_status = msg
        self._app.invalidate()
        self._start_timer(timeout, self._clear_scan_status)

    def _clear_scan_status(self) -> None: self._scan_status = ""; self._app.invalidate()

    def _start_timer(self, interval: float, func: object) -> None:
        t = threading.Timer(interval, func)
        t.daemon = True
        t.start()

    def _reset_ctrl_c_hint(self) -> None:
        self._ctrl_c_quit_hint = False
        self._app.invalidate()

    def _reset_footer_highlight(self) -> None:
        self._footer_highlight_until = 0.0
        self._app.invalidate()

    def _trigger_footer_highlight(self) -> None:
        self._footer_highlight_until = time.monotonic() + 2.0
        self._app.invalidate()
        self._start_timer(2.0, self._reset_footer_highlight)

    # ── run ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._app.run()

    def _build_key_bindings(self):
        from blink.tui.key_bindings import build_key_bindings
        return build_key_bindings(self)

    def run_scan_blocking(self, on_progress: Optional[Callable[[int], None]] = None) -> None:
        results = self._scanner.run_scan(blocking=True, on_progress=on_progress)
        for sr in results:
            rid = self._store.upsert_repo(sr.repo)
            for remote in sr.remotes:
                remote.repo_id = rid
                self._store.upsert_remote(remote)
        self._load_repos()
