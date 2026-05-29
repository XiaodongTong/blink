from __future__ import annotations

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
from blink.scanner import Scanner, ScanResult, StatusFetcher, check_pull_prereqs, parse_pull_output
from blink.tui.repo_list import RepoListControl
from blink.tui.search import SearchBar
from blink.tui.actions import EditorInfo, IDE_CHOICES, detect_editors, open_in_editor, open_terminal
from blink.tui.detail import DetailPanel, _remote_to_https
from blink.tui.styles import build_style
from blink.tui.layout import build_layout, EditStatusControl
from blink.tui.key_bindings import build_key_bindings
from blink.tui.status_bar import build_status_text, build_search_prefix_text, build_footer_text
from blink.tui.app_review import ReviewOrchestrator


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
        self._ide_pending_path: Optional[str] = None
        self._committing_paths: set[str] = set()
        self._pulling_paths: set[str] = set()

        self._review = ReviewOrchestrator(self)

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
        if self._detail_panel is not None:
            self._detail_panel.set_focused(pane in ("detail", "edit"))

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
        preferred = self._config.preferred_ide
        if preferred:
            info = self._editors.get(preferred)
            if info and info.available:
                open_in_editor(path, preferred, self._editors)
            else:
                self._config.set("preferred_ide", None)
                self._ide_pending_path = path
                self._ide_selecting = True
                self._ide_select_cursor = 0
                self._app.invalidate()
        else:
            self._ide_pending_path = path
            self._ide_selecting = True
            self._ide_select_cursor = 0
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

    # ── add task ────────────────────────────────────────────────────────

    def _run_add_task(self) -> None:
        repo = self._get_active_repo()
        if not repo:
            return

        def do_add_task():
            try:
                from blink.loop.cmd_edit import _add_task
                from blink.loop.config import TASKS_FILE
                logger.log("task", f"添加任务: path={repo.path}")
                msg = _add_task(repo.path)
                if msg:
                    logger.log("task", f"任务添加成功: {msg}")
                    task_file = str(TASKS_FILE)
                    self._start_timer(0.1, lambda: (
                        self._set_scan_status(f"✓ {msg}", timeout=2.0),
                        self._open_with_ide(task_file),
                    ))
                else:
                    self._start_timer(0.1, lambda: self._set_scan_status("✗ Task 添加失败", timeout=5.0))
            except Exception:
                self._start_timer(0.1, lambda: self._set_scan_status("✗ Task 添加失败", timeout=5.0))

        threading.Thread(target=do_add_task, daemon=True).start()

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

    # ── background scan ─────────────────────────────────────────────────

    def _start_background_scan(self) -> None:
        self._scanning = True
        self._scan_status = "Scanning..."
        logger.log("scanner", "开始后台扫描")
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
            logger.log("scanner", f"扫描完成: {len(results)} repos")
            self._app.invalidate()
            self._start_background_status_fetch()

        def run() -> None:
            results = self._scanner.run_scan(blocking=True, on_result=on_result)
            done(results)

        threading.Thread(target=run, daemon=True).start()

    # ── pull ────────────────────────────────────────────────────────────

    def _run_pull(self, repo: Repo) -> None:
        if repo.path in self._pulling_paths:
            return
        ok, msg = check_pull_prereqs(repo)
        if not ok:
            self._scan_status = msg
            self._app.invalidate()
            self._start_timer(3.0, self._clear_scan_status)
            return
        self._pulling_paths.add(repo.path)
        self._app.invalidate()

        def do_pull() -> None:
            try:
                logger.log("pull", f"开始拉取: path={repo.path}")
                result = sp.run(["git", "pull"], cwd=repo.path, capture_output=True, text=True, timeout=30)
                success, message = parse_pull_output(result.stdout, result.returncode, result.stderr)
                logger.log("pull", f"拉取{'成功' if success else '失败'}: path={repo.path}, msg={message}")
            except sp.TimeoutExpired:
                success, message = False, "✗ Pull timed out"
            except Exception as exc:
                success, message = False, f"✗ Pull failed: {exc}"

            self._start_timer(0.1, lambda: self._finish_pull(repo, success, message))

        threading.Thread(target=do_pull, daemon=True).start()

    def _finish_pull(self, repo: Repo, success: bool, message: str) -> None:
        self._pulling_paths.discard(repo.path)
        if success:
            self._refresh_repo_status(repo)
        self._scan_status = message
        self._app.invalidate()
        self._start_timer(3.0, self._clear_scan_status)

    # ── commit ──────────────────────────────────────────────────────────

    def _run_commit(self, repo: Repo) -> None:
        if repo.path in self._committing_paths:
            return
        self._committing_paths.add(repo.path)
        self._app.invalidate()

        def do_commit():
            try:
                from blink.loop.git_ops import is_git_repo, is_git_clean, ensure_clean_git
                logger.log("commit", f"开始自动提交: path={repo.path}")
                if not is_git_repo(repo.path):
                    return False, "✗ 不是 Git 仓库"
                if is_git_clean(repo.path):
                    return True, "✓ 工作树已干净"
                success = ensure_clean_git(repo.path, "manual commit", model=self._config.model_commit, quiet=True)
                return (True, "✓ 提交完成") if success else (False, "✗ 提交失败")
            except FileNotFoundError:
                return False, "✗ claude CLI 未安装"
            except Exception as exc:
                return False, f"✗ 提交失败: {exc}"

        def on_done():
            success, message = do_commit()
            self._committing_paths.discard(repo.path)
            if success:
                self._refresh_repo_status(repo)
            self._scan_status = message
            self._app.invalidate()
            self._start_timer(3.0, self._clear_scan_status)

        threading.Thread(target=on_done, daemon=True).start()

    # ── refresh & status fetch ──────────────────────────────────────────

    def _refresh_repo_status(self, repo: Repo) -> None:
        if repo.id is None:
            return
        fetcher = StatusFetcher()
        fetcher.run_fetch(
            repos=[(repo.id, repo.path)], blocking=True,
            on_status=lambda rid, status: self._store.upsert_status(rid, status),
            on_error=lambda rid: None, on_done=lambda: None,
        )
        self._load_repos()
        self._sync_detail_panel()
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
            repos=repo_items, blocking=False,
            on_status=on_status, on_error=on_error, on_done=on_done,
        )

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
