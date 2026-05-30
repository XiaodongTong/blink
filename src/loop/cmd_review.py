"""blink review — AI-assisted code review of colleague branches."""

import re
import sys
from pathlib import Path
from typing import Optional

from blink import logger
from blink.loop import git_ops
from blink.loop.claude_runner import run_claude_text
from blink.loop.review_context import (
    DIFF_SIZE_LIMIT, REVIEW_PROMPT,
    collect_context, build_review_prompt, _enrich_context,
)
from blink.loop.review_report import (
    ReviewResult, ensure_review_dir, parse_verdict, save_report,
)


def setup_review_branch(dir_path, branch, base):
    current = git_ops.get_current_branch(dir_path)
    review_name, saved_ref, stashed, error = git_ops.create_review_branch(dir_path, branch, base)
    if error is not None:
        return None, current, stashed, error
    return review_name, current, stashed, None


def cleanup_review_branch(dir_path, original_branch, review_branch, stashed=False, base="main", keep_branch=False):
    """Restore original branch and optionally delete the review branch.

    Returns True on success, False if any step failed.
    """
    success = True

    if review_branch and git_ops.branch_exists(dir_path, review_branch):
        target = original_branch or base
        result = git_ops._git(dir_path, "checkout", target, "--quiet")
        if result.returncode != 0:
            logger.log("review", f"Warning: failed to checkout {target}: {result.stderr.strip()}")
            success = False

    if stashed:
        result = git_ops._git(dir_path, "stash", "pop", "--quiet")
        if result.returncode != 0:
            logger.log("review", f"Warning: stash pop failed, run 'git stash pop' manually")
            success = False

    if not keep_branch and review_branch and git_ops.branch_exists(dir_path, review_branch):
        git_ops._git(dir_path, "branch", "-D", review_branch)

    return success


def run_review(
    dir_path, branch, base,
    *,
    model="opus",
    diff_only=False,
    no_verify=False,
    no_lint=False,
    no_test=False,
    no_context=False,
    strict=False,
    keep_branch=False,
    stage_fn=None,
):
    """Core review pipeline — shared by CLI and TUI.

    Args:
        dir_path: Project directory.
        branch: Branch to review.
        base: Base branch to diff against.
        model: Claude model to use.
        diff_only: Skip branch creation (no merge, no lint/test/context on merged code).
        no_verify: Skip verification pass.
        no_lint: Skip static analysis.
        no_test: Skip test execution.
        no_context: Skip code context enrichment.
        strict: Strict mode — upgrade APPROVE_WITH_NOTES with MAJOR to DENY.
        keep_branch: Keep the temporary review branch after cleanup.
        stage_fn: Optional callback(stage_name) for progress reporting.

    Returns:
        ReviewResult with success status, verdict, report path, or error.
    """
    dir_path = Path(dir_path).resolve()

    if stage_fn:
        stage_fn("collecting")

    # 1. Collect basic context (diff, log, stat, rules)
    context = collect_context(dir_path, branch, base)

    # 2. Early return if no changes
    if not context["diff"]:
        return ReviewResult(False, error="No changes between branches")

    # 3. Setup review branch (or diff-only)
    review_branch = None
    original_branch = None
    stashed = False

    if not diff_only:
        if stage_fn:
            stage_fn("merging")
        review_branch, original_branch, stashed, merge_error = setup_review_branch(
            dir_path, branch, base,
        )
        if merge_error is not None:
            error_type, error_msg = merge_error
            if error_type == "conflict":
                logger.log("review", f"合并冲突: {error_msg}")
                conflict_report = (
                    f"## 合并冲突\n\n"
                    f"分支 `{branch}` 无法合并到 `{base}`，存在合并冲突。\n"
                    f"必须先解决冲突后才能继续。\n\n"
                    f"```\n{error_msg}\n```\n"
                )
                report_path = save_report(dir_path, branch, base, "DENY", conflict_report)
                logger.log("review", f"Review 完成(冲突): verdict=DENY, report={report_path}")
                return ReviewResult(
                    True, verdict="DENY", report_path=report_path,
                    info=f"Merge conflict detected between {base} and {branch}.",
                )
            else:
                logger.log("review", f"合并失败(非冲突): {error_msg}，回退到 diff-only 模式")
                diff_only = True

    # 4. Enrich context and run analysis on the correct code
    source_branch = branch if diff_only else None

    if not no_context and context["diff"]:
        context["code_context"] = _enrich_context(
            dir_path, context["diff"], source_branch=source_branch,
        ) or "(no additional context)"

    if not no_lint and context["diff"]:
        from blink.loop.review_analyzer import run_static_analysis
        context["lint_result"] = run_static_analysis(dir_path, context["diff"])

    if not no_test:
        from blink.loop.review_tester import run_tests
        test_name, passed, output = run_tests(dir_path)
        if test_name:
            status = "PASSED" if passed else "FAILED"
            context["test_result"] = f"[{test_name}] {status}\n{output}"
        else:
            context["test_result"] = output

    # 5. Build prompt and run AI
    try:
        prompt = build_review_prompt(context)

        if stage_fn:
            stage_fn("reviewing")
        logger.log("review", f"AI 输入 prompt ({len(prompt):,} chars)")
        logger.log_lines("review.input", prompt)

        output = run_claude_text(
            prompt,
            cwd=str(dir_path),
            model=model,
            quiet=True,
        )

        if not output:
            logger.log("review", "AI 返回空结果")
            return ReviewResult(False, error="Claude returned no output")

        logger.log("review", f"AI 输出 ({len(output):,} chars)")
        logger.log_lines("review.output", output)

        # 6. Verification pass
        verified_output = None
        if not no_verify:
            if stage_fn:
                stage_fn("verifying")
            from blink.loop.review_verifier import verify_findings
            verified_output = verify_findings(
                dir_path, output, context["diff"], context["lint_result"],
                model=model, quiet=True,
            )
            if verified_output:
                logger.log("review", f"验证输出 ({len(verified_output):,} chars)")
                logger.log_lines("review.verify_output", verified_output)

        final_output = verified_output if verified_output else output
        verdict, _ = parse_verdict(final_output)

        # If verification produced output but no verdict, fallback to initial verdict
        if verified_output and not re.search(r"^VERDICT:", final_output, re.MULTILINE):
            initial_verdict, _ = parse_verdict(output)
            verdict = initial_verdict

        if strict and verdict == "APPROVE_WITH_NOTES":
            if re.search(r"\[CRITICAL\]", final_output):
                verdict = "DENY"
            elif re.search(r"\[MAJOR\]", final_output):
                verdict = "DENY"

        extra_sections = []
        if verified_output:
            extra_sections.append(("验证结果", verified_output + "\n"))

        report_path = save_report(dir_path, branch, base, verdict, final_output, extra_sections)
        logger.log("review", f"Review 完成: verdict={verdict}, report={report_path}")

        return ReviewResult(True, verdict=verdict, report_path=report_path)

    except FileNotFoundError:
        return ReviewResult(False, error="claude CLI 未安装")
    except Exception as exc:
        logger.log("review", f"Review 异常: {exc}")
        return ReviewResult(False, error=f"Review failed: {exc}")
    finally:
        if review_branch:
            cleanup_ok = cleanup_review_branch(
                dir_path, original_branch, review_branch, stashed,
                base=base, keep_branch=keep_branch,
            )
            if not cleanup_ok:
                logger.log("review", f"Warning: cleanup may have issues for branch {review_branch}")
            logger.log("review", f"临时分支已清理: {review_branch}")


def handle(args):
    if getattr(args, "list", False):
        _handle_list(args)
        return

    if getattr(args, "init_rules", False):
        _handle_init_rules(args)
        return

    branch = getattr(args, "branch", None)
    if not branch:
        print("Error: branch name is required", file=sys.stderr)
        return

    dir_path = Path(getattr(args, "dir", ".")).resolve()

    if not dir_path.is_dir():
        print(f"\033[91mError: {dir_path} is not a directory.\033[0m")
        return

    if not git_ops.is_git_repo(dir_path):
        print(f"\033[91mError: {dir_path} is not a git repository.\033[0m")
        return

    if not git_ops.branch_exists(dir_path, branch):
        print(f"\033[91mError: branch '{branch}' does not exist.\033[0m")
        return

    base = getattr(args, "against", None)
    if not base:
        base = git_ops.detect_main_branch(dir_path)
        if not base:
            print("\033[91mError: could not detect main branch. "
                  "Use --against <branch> to specify.\033[0m")
            return

    diff_only = getattr(args, "diff_only", False)
    model = getattr(args, "model", "opus")
    no_verify = getattr(args, "no_verify", False)
    no_lint = getattr(args, "no_lint", False)
    no_test = getattr(args, "no_test", False)
    no_context = getattr(args, "no_context", False)
    strict = getattr(args, "strict", False)
    keep_branch = getattr(args, "keep_branch", False)

    logger.log("review", f"开始 review: branch={branch}, base={base}, dir={dir_path}, "
               f"model={model}, diff_only={diff_only}, verify={not no_verify}, "
               f"lint={not no_lint}, test={not no_test}, context={not no_context}, strict={strict}")

    print(f"Collecting context: {base}..{branch}")

    def print_stage(stage):
        labels = {
            "collecting": "Collecting context...",
            "merging": "Creating temporary review branch...",
            "reviewing": f"Running Claude review (model={model})...",
            "verifying": "Running verification pass...",
        }
        msg = labels.get(stage)
        if msg:
            print(f"  {msg}")

    result = run_review(
        dir_path, branch, base,
        model=model,
        diff_only=diff_only,
        no_verify=no_verify,
        no_lint=no_lint,
        no_test=no_test,
        no_context=no_context,
        strict=strict,
        keep_branch=keep_branch,
        stage_fn=print_stage,
    )

    if not result.success:
        print(f"\033[91m{result.error}\033[0m")
        return

    if result.info:
        print(f"\033[91m{result.info}\033[0m")

    verdict_colors = {
        "APPROVE": "\033[92m",
        "APPROVE_WITH_NOTES": "\033[93m",
        "DENY": "\033[91m",
    }
    color = verdict_colors.get(result.verdict, "")
    reset = "\033[0m"

    print(f"\n{color}Verdict: {result.verdict}{reset}")
    print(f"Report saved: {result.report_path}")


def _handle_list(args):
    dir_path = Path(getattr(args, "dir", ".")).resolve()
    review_dir = dir_path / "docs" / "blink" / "code-review"

    if not review_dir.exists():
        print("No reviews found.")
        return

    reports = sorted(review_dir.glob("*.md"), reverse=True)
    if not reports:
        print("No reviews found.")
        return

    print(f"Code reviews in {dir_path.name}:\n")
    for report in reports:
        content = report.read_text()
        matches = re.findall(r"VERDICT:\s*(APPROVE|APPROVE_WITH_NOTES|DENY)", content)
        verdict = matches[-1] if matches else "UNKNOWN"
        badges = {
            "APPROVE": "\033[92m✓ APPROVE\033[0m",
            "APPROVE_WITH_NOTES": "\033[93m⚠ APPROVE_WITH_NOTES\033[0m",
            "DENY": "\033[91m✗ DENY\033[0m",
            "UNKNOWN": "\033[90m? UNKNOWN\033[0m",
        }
        print(f"  {badges.get(verdict, verdict)}  {report.stem}")


def _handle_init_rules(args):
    dir_path = Path(getattr(args, "dir", ".")).resolve()
    rules_path = dir_path / "docs" / "blink" / "review-rules.md"

    if rules_path.exists():
        print(f"\033[91mError: {rules_path} already exists. "
              "Edit it manually to update your review rules.\033[0m")
        return

    rules_path.parent.mkdir(parents=True, exist_ok=True)

    template = """\
# Review Rules

## 必查项
<!-- 项目必须检查的项目，如：安全漏洞、数据一致性、API 契约 -->

## 历史教训
<!-- 历史问题记录，避免同类问题再次出现 -->

## 代码风格
<!-- 项目特定的代码风格要求，如：命名规范、文件组织、注释要求 -->
"""
    rules_path.write_text(template)
    print(f"\033[92mCreated: {rules_path}\033[0m")
    print("Edit this file to define project-specific review standards.")
