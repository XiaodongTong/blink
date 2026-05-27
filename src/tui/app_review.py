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
                    self._app._app.layout.focus(self._app._detail_window)
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
        self._app._app.layout.focus(self._app._detail_window)
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
            self._app._app.layout.focus(self._app._detail_window)
            self._app._app.invalidate()
            return
        self._app._set_focus("detail")
        self._app._app.layout.focus(self._app._detail_window)
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
            try:
                from blink.loop.cmd_review import (
                    collect_context, build_review_prompt, parse_verdict,
                    save_report, setup_review_branch, cleanup_review_branch,
                )
                from blink.loop.claude_runner import run_claude_text
                from blink.loop import git_ops
                from blink import logger

                dir_path = repo.path
                base = git_ops.detect_main_branch(dir_path)
                if not base:
                    return False, "✗ 无法检测主分支，请用 CLI --against 指定"

                if not git_ops.branch_exists(dir_path, branch):
                    return False, f"✗ 分支 '{branch}' 不存在"

                logger.log("review", f"TUI review 开始: branch={branch}, base={base}, dir={dir_path}")

                self._set_stage("collecting")
                context = collect_context(
                    dir_path, branch, base,
                    with_lint=True, with_test=True, with_context=True,
                )

                review_branch = None
                original_branch = None
                stashed = False

                self._set_stage("merging")
                review_branch, original_branch, stashed, merge_error = setup_review_branch(dir_path, branch, base)
                if merge_error is not None:
                    error_type, error_msg = merge_error
                    if error_type == "conflict":
                        logger.log("review", f"TUI 合并冲突: {error_msg}")
                        conflict_report = (
                            f"## 合并冲突\n\n"
                            f"分支 `{branch}` 无法合并到 `{base}`，存在合并冲突。\n"
                            f"必须先解决冲突后才能继续。\n\n"
                            f"```\n{error_msg}\n```\n"
                        )
                        report_path = save_report(dir_path, branch, base, "DENY", conflict_report)
                        self.last_report_paths[repo.path] = report_path
                        logger.log("review", f"TUI review 完成(冲突): verdict=DENY, report={report_path}")
                        return True, ("DENY", report_path)
                    else:
                        logger.log("review", f"TUI 合并失败(非冲突): {error_msg}，使用 diff-only 模式")
                else:
                    logger.log("review", f"TUI 临时分支创建: {review_branch}")

                try:
                    prompt = build_review_prompt(context)

                    self._set_stage("reviewing")
                    logger.log("review", f"TUI AI 输入 prompt ({len(prompt):,} chars)")
                    logger.log_lines("review.input", prompt)

                    output = run_claude_text(
                        prompt,
                        cwd=dir_path,
                        model=self._app._config.model_review,
                        quiet=True,
                    )

                    if not output:
                        logger.log("review", "TUI AI 返回空结果")
                        return False, "✗ Claude 返回空结果"

                    logger.log("review", f"TUI AI 输出 ({len(output):,} chars)")
                    logger.log_lines("review.output", output)

                    # Verification pass
                    self._set_stage("verifying")
                    from blink.loop.review_verifier import verify_findings
                    verified_output = verify_findings(
                        dir_path, output, context["diff"], context["lint_result"],
                        model=self._app._config.model_review, quiet=True,
                    )
                    if verified_output:
                        logger.log("review", f"TUI 验证输出 ({len(verified_output):,} chars)")
                        final_output = verified_output
                    else:
                        final_output = output

                    verdict, full_output = parse_verdict(final_output)

                    extra_sections = []
                    if verified_output:
                        extra_sections.append(("验证结果", verified_output + "\n"))

                    report_path = save_report(dir_path, branch, base, verdict, full_output, extra_sections)
                    logger.log("review", f"TUI review 完成: verdict={verdict}, report={report_path}")
                    return True, (verdict, report_path)
                finally:
                    if review_branch:
                        cleanup_review_branch(dir_path, original_branch, review_branch, stashed, base=base)
                        logger.log("review", f"TUI 临时分支已清理: {review_branch}")

            except FileNotFoundError:
                return False, "✗ claude CLI 未安装"
            except Exception as exc:
                return False, f"✗ Review 失败: {exc}"

        def on_done():
            success, result = do_review()
            self.reviewing_paths.discard(repo.path)
            self.review_stage = ""
            if success:
                verdict, report_path = result
                self.last_report_paths[repo.path] = report_path
                badges = {
                    "APPROVE": "✅ APPROVE",
                    "APPROVE_WITH_NOTES": "⚠️ APPROVE_WITH_NOTES",
                    "DENY": "❌ DENY",
                }
                badge = badges.get(verdict, verdict)
                self._app._set_scan_status(f"{badge}  {branch}", timeout=5.0)
            else:
                self._app._set_scan_status(result, timeout=5.0)
            self._app._app.invalidate()

        t = threading.Thread(target=on_done, daemon=True)
        t.start()
