"""blink review — AI-assisted code review of colleague branches."""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from blink import logger
from blink.loop import git_ops
from blink.loop.claude_runner import run_claude_text

DIFF_SIZE_LIMIT = 100 * 1024  # 100KB

REVIEW_PROMPT = """\
你正在对 git 仓库中的代码变更进行结构化 code review。

<rules>
{rules}
</rules>

<commit_log>
{log}
</commit_log>

<diff_stat>
{stat}
</diff_stat>

<diff>
{diff}
</diff>

请审查以上变更，生成一份中文报告，结构如下：

VERDICT: <APPROVE|APPROVE_WITH_NOTES|REQUEST_CHANGES>

## 总结
<2-3 句话的整体质量评估>

## 问题
<对发现的每个问题，按以下格式输出：>
### [CRITICAL|MAJOR|MINOR] <文件:行号> — <标题>
<问题描述>
建议：<具体的修改建议或代码示例>

## 必须修改
<仅当 VERDICT 为 REQUEST_CHANGES 时 — 列出可操作的修改项，附带修改前后的代码示例>

## 改进建议
<仅当 VERDICT 为 APPROVE_WITH_NOTES 时 — 后续改进建议>

VERDICT 规则：
- 存在任何 CRITICAL 问题 → REQUEST_CHANGES
- 存在 MAJOR 但无 CRITICAL → APPROVE_WITH_NOTES
- 仅 MINOR 或无问题 → APPROVE

如果没有发现问题：
VERDICT: APPROVE
## 总结
<总结>
## 问题
未发现问题。
"""


def ensure_review_dir(dir_path):
    review_dir = Path(dir_path) / "docs" / "blink" / "code-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    return review_dir


def collect_context(dir_path, branch, base):
    diff_result = git_ops._git(dir_path, "diff", f"{base}..{branch}")
    diff = diff_result.stdout.strip() if diff_result.returncode == 0 else ""
    truncated = False
    if len(diff) > DIFF_SIZE_LIMIT:
        diff = diff[:DIFF_SIZE_LIMIT]
        truncated = True

    log_result = git_ops._git(dir_path, "log", "--oneline", f"{base}..{branch}")
    log = log_result.stdout.strip() if log_result.returncode == 0 else ""

    stat = git_ops.get_diff_stat(dir_path, base, branch)

    rules_path = Path(dir_path) / "docs" / "blink" / "review-rules.md"
    rules = ""
    if rules_path.exists():
        rules = rules_path.read_text()

    return {
        "diff": diff,
        "log": log,
        "stat": stat,
        "rules": rules,
        "truncated": truncated,
    }


def build_review_prompt(context):
    rules_block = context["rules"] if context["rules"] else "(No project-specific review rules defined)"
    diff_content = context["diff"]
    if context["truncated"]:
        diff_content += "\n\n... [DIFF TRUNCATED AT 100KB — original diff exceeds the limit]"

    return REVIEW_PROMPT.format(
        rules=rules_block,
        log=context["log"] or "(no commits in range)",
        stat=context["stat"] or "(no changes)",
        diff=diff_content or "(no diff)",
    )


def setup_review_branch(dir_path, branch, base):
    current = git_ops.get_current_branch(dir_path)
    review_name, saved_ref, stashed = git_ops.create_review_branch(dir_path, branch, base)
    if review_name is None:
        return None, current, stashed
    return review_name, current, stashed


def cleanup_review_branch(dir_path, original_branch, review_branch, stashed=False, base="main"):
    if review_branch and git_ops.branch_exists(dir_path, review_branch):
        if original_branch:
            git_ops._git(dir_path, "checkout", original_branch, "--quiet")
        else:
            git_ops._git(dir_path, "checkout", base, "--quiet")
        git_ops.delete_branch(dir_path, review_branch)
    if stashed:
        git_ops._git(dir_path, "stash", "pop", "--quiet")


def parse_verdict(output):
    if not output:
        return "APPROVE_WITH_NOTES", output
    matches = re.findall(r"VERDICT:\s*(APPROVE_WITH_NOTES|REQUEST_CHANGES|APPROVE)", output)
    if matches:
        return matches[-1], output
    return "APPROVE_WITH_NOTES", output


def _branch_slug(branch):
    slug = branch.replace("/", "-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def save_report(dir_path, branch, base, verdict, content):
    review_dir = ensure_review_dir(dir_path)
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    slug = _branch_slug(branch)
    filename = f"{slug}-{date_str}.md"
    report_path = review_dir / filename

    verdict_labels = {
        "APPROVE": "✓ 通过",
        "APPROVE_WITH_NOTES": "⚠ 有建议",
        "REQUEST_CHANGES": "✗ 需修改",
    }
    header = (
        f"# Code Review: {branch}\n"
        f"\n"
        f"- **分支**: `{branch}`\n"
        f"- **基准**: `{base}`\n"
        f"- **日期**: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"- **结论**: {verdict_labels.get(verdict, verdict)}\n"
        f"\n"
        f"---\n"
        f"\n"
    )
    report_path.write_text(header + content)
    return str(report_path)


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
    model = getattr(args, "model", "sonnet")

    logger.log("review", f"开始 review: branch={branch}, base={base}, dir={dir_path}, model={model}, diff_only={diff_only}")

    print(f"Collecting context: {base}..{branch}")
    context = collect_context(dir_path, branch, base)

    review_branch = None
    original_branch = None
    stashed = False

    if not diff_only:
        print("Creating temporary review branch...")
        review_branch, original_branch, stashed = setup_review_branch(dir_path, branch, base)
        if review_branch is None:
            print("\033[93mWarning: merge conflict detected. Falling back to diff-only mode.\033[0m")
            diff_only = True
            logger.log("review", "合并冲突，回退到 diff-only 模式")
        else:
            print(f"Review branch created: {review_branch}")
            logger.log("review", f"临时分支创建: {review_branch}")

    try:
        prompt = build_review_prompt(context)
        print(f"Running Claude review (model={model})...")

        logger.log("review", f"AI 输入 prompt ({len(prompt):,} chars)")
        logger.log_lines("review.input", prompt)

        output = run_claude_text(
            prompt,
            cwd=str(dir_path),
            model=model,
            quiet=False,
        )

        if not output:
            print("\033[91mError: Claude returned no output.\033[0m", file=sys.stderr)
            logger.log("review", "AI 返回空结果")
            return

        logger.log("review", f"AI 输出 ({len(output):,} chars)")
        logger.log_lines("review.output", output)

        verdict, full_output = parse_verdict(output)
        report_path = save_report(dir_path, branch, base, verdict, full_output)

        verdict_colors = {
            "APPROVE": "\033[92m",
            "APPROVE_WITH_NOTES": "\033[93m",
            "REQUEST_CHANGES": "\033[91m",
        }
        color = verdict_colors.get(verdict, "")
        reset = "\033[0m"

        print(f"\n{color}Verdict: {verdict}{reset}")
        print(f"Report saved: {report_path}")

        logger.log("review", f"Review 完成: verdict={verdict}, report={report_path}")

    finally:
        if review_branch:
            print("Cleaning up review branch...")
            cleanup_review_branch(dir_path, original_branch, review_branch, stashed, base=base)
            print("Cleanup complete.")
            logger.log("review", f"临时分支已清理: {review_branch}")


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
        matches = re.findall(r"VERDICT:\s*(APPROVE|APPROVE_WITH_NOTES|REQUEST_CHANGES)", content)
        verdict = matches[-1] if matches else "UNKNOWN"
        badges = {
            "APPROVE": "\033[92m✓ APPROVE\033[0m",
            "APPROVE_WITH_NOTES": "\033[93m⚠ APPROVE_WITH_NOTES\033[0m",
            "REQUEST_CHANGES": "\033[91m✗ REQUEST_CHANGES\033[0m",
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
