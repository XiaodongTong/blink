from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

from blink.models import Repo

if TYPE_CHECKING:
    from blink.tui.app import BlinkApp


class ReviewOrchestrator:
    def __init__(self, app: BlinkApp) -> None:
        self._app = app
        self.reviewing_paths: set[str] = set()
        self.branch_loading: bool = False
        self.selecting: bool = False
        self.branches: list[str] = []
        self.branch_cursor: int = 0
        self.last_report_paths: dict[str, str] = {}
        self.review_stage: str = ""  # Current review stage for status display

    def start_branch_select(self, repo: Repo) -> None:
        if repo.path in self.reviewing_paths:
            self._app._set_scan_status("✗ 正在 review 中，请等待完成", timeout=3.0)
            return
        self.branch_loading = True
        self._app._set_focus("edit")
        self._app._app.invalidate()

        def fetch_branches():
            from blink.loop import git_ops
            branches = git_ops.get_recent_branches(repo.path)

            def on_done():
                self.branch_loading = False
                if not branches:
                    self._app._set_scan_status("✗ 没有找到可 review 的分支", timeout=3.0)
                    self._app._set_focus("detail")
                    if self._app._detail_window is not None:
                        self._app._focus(self._app._detail_window)
                    self._app._app.invalidate()
                    return
                self.branches = branches
                self.branch_cursor = 0
                self.selecting = True
                self._app._app.invalidate()

            self._app._start_timer(0.1, on_done)

        t = threading.Thread(target=fetch_branches, daemon=True)
        t.start()

    def cancel(self) -> None:
        self.selecting = False
        self.branch_loading = False
        self.branches = []
        self.branch_cursor = 0
        self.review_stage = ""
        self._app._set_focus("detail")
        if self._app._detail_window is not None:
            self._app._focus(self._app._detail_window)
        self._app._app.invalidate()

    def confirm_branch(self) -> None:
        if not self.branches:
            self.cancel()
            return
        branch = self.branches[self.branch_cursor]
        self.selecting = False
        self.branches = []
        self.branch_cursor = 0
        repo = self._app._get_active_repo()
        if not repo:
            self._app._set_focus("detail")
            if self._app._detail_window is not None:
                self._app._focus(self._app._detail_window)
            self._app._app.invalidate()
            return
        self._app._set_focus("detail")
        if self._app._detail_window is not None:
            self._app._focus(self._app._detail_window)
        self._run_review(repo, branch)

    def _set_stage(self, stage: str) -> None:
        """Update the current review stage and refresh the UI."""
        self.review_stage = stage
        self._app._app.invalidate()

    def _run_review(self, repo: Repo, branch: str) -> None:
        if repo.path in self.reviewing_paths:
            return
        self.reviewing_paths.add(repo.path)
        self.review_stage = "collecting"
        self._app._app.invalidate()

        def do_review():
            from blink.loop.review.cmd import run_review
            from blink.loop.review.report import ReviewResult
            from blink.loop import git_ops
            from blink import logger

            dir_path = repo.path
            base = git_ops.detect_main_branch(dir_path)
            if not base:
                return ReviewResult(False, error="✗ 无法检测主分支，请用 CLI --against 指定")

            if not git_ops.branch_exists(dir_path, branch):
                return ReviewResult(False, error=f"✗ 分支 '{branch}' 不存在")

            logger.log("review", f"TUI review 开始: branch={branch}, base={base}, dir={dir_path}")

            result = run_review(
                dir_path, branch, base,
                model=self._app._config.model_review,
                stage_fn=self._set_stage,
            )
            return result

        def on_done():
            result = do_review()
            self.reviewing_paths.discard(repo.path)
            self.review_stage = ""
            if result.success:
                self.last_report_paths[repo.path] = result.report_path
                badges = {
                    "APPROVE": "✅ APPROVE",
                    "APPROVE_WITH_NOTES": "⚠️ APPROVE_WITH_NOTES",
                    "DENY": "❌ DENY",
                }
                badge = badges.get(result.verdict, result.verdict)
                self._app._set_scan_status(f"{badge}  {branch}", timeout=5.0)
            else:
                self._app._set_scan_status(f"{result.error}", timeout=5.0)
            self._app._app.invalidate()

        t = threading.Thread(target=on_done, daemon=True)
        t.start()
