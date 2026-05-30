"""BlinkApp action methods — background scan, status fetch, pull, commit, add-task."""

from __future__ import annotations

import subprocess as sp
import threading

from typing import List

from blink import logger
from blink.models import Repo, RepoStatus
from blink.scanner import ScanResult, StatusFetcher, check_pull_prereqs, parse_pull_output
from blink.store import Store


class AppActionsMixin:
    _store: Store
    _config: object
    _app: object
    _pulling_paths: set[str]
    _committing_paths: set[str]
    _fetching_status: bool
    _scanning: bool
    _scan_status: str
    _repo_control: object
    _status_fetcher: StatusFetcher

    # Implemented in BlinkApp
    def _load_repos(self) -> None: ...
    def _sync_detail_panel(self) -> None: ...
    def _set_scan_status(self, msg: str, timeout: float = 3.0) -> None: ...
    def _clear_scan_status(self) -> None: ...
    def _start_timer(self, interval: float, func: object) -> None: ...
    def _open_with_ide(self, path: str) -> None: ...

    # ── background scan ────────────────────────────────────────────────────

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

    # ── status fetch ───────────────────────────────────────────────────────

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

    # ── pull ───────────────────────────────────────────────────────────────

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

    # ── commit ─────────────────────────────────────────────────────────────

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

    # ── add task ───────────────────────────────────────────────────────────

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
