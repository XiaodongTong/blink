"""blink review — AI-assisted code review of colleague branches."""

import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from blink import logger
from blink.loop import git_ops
from blink.loop.claude_runner import run_claude_text

DIFF_SIZE_LIMIT = 100 * 1024  # 100KB
CONTEXT_SIZE_LIMIT = 50 * 1024  # 50KB for enriched context

# Static instructions FIRST for prompt caching, then variable sections after
REVIEW_PROMPT = """\
你是一名资深软件工程师，正在对代码变更进行严格的 code review。你只基于下方提供的实际代码内容进行审查。

## 审查范围

你只能审查 <diff> 中实际出现的代码变更。绝对禁止：
- 评论 <diff> 中未涉及的文件或函数
- 推测未展示代码的行为
- 猜测不存在的文件路径或行号

## 审查维度

只关注影响正确性、安全性、性能的问题，不评论代码风格、命名偏好、注释缺失等不影响行为的问题：
1. **Bugs**: 逻辑错误、off-by-one、空值处理、类型错误、条件判断错误
2. **Security**: 注入漏洞、凭据暴露、不安全的输入处理、权限缺失
3. **Error handling**: 缺失的错误处理、异常吞没、资源泄漏（未关闭的连接/文件）
4. **Concurrency**: 竞态条件、死锁风险、线程安全问题
5. **Performance**: 明显的性能问题（N+1 查询、不必要的全量复制、阻塞操作）

## 置信度门控

对每个发现的问题，必须评估置信度：
- **HIGH**: 你确信这是真实 bug，能给出具体的触发场景
- **MEDIUM**: 有合理的怀疑依据，但无法 100% 确认
- **LOW**: 仅基于推测，缺乏具体证据

规则：
- HIGH 置信度的问题正常报告
- MEDIUM 置信度的问题标记 [MEDIUM_CONFIDENCE]，严重度降一级
- LOW 置信度的问题**不报告**（宁可漏报也不误报）
- 如果 lint 工具已报告某问题且你同意，置信度自动提升为 HIGH

## 反推测规则

禁止以下行为：
- 推测变更"可能"影响未展示的代码，除非你能指出具体的受影响文件和函数
- 对仅涉及风格、命名、注释的问题报 CRITICAL 或 MAJOR
- 基于"如果输入是 X 就会出错"的模糊假设，除非能给出具体的触发输入
- 将 lint 工具已覆盖的风格/格式问题重复报告

## 输出格式

VERDICT: <APPROVE|APPROVE_WITH_NOTES|DENY>

## 总结
<2-3 句话的整体质量评估，包括 lint 和测试结果的综合判断>

## 问题
<对每个确认的问题，严格按以下格式输出：>
### [CRITICAL|MAJOR|MINOR] [HIGH|MEDIUM_CONFIDENCE] <文件:行号> — <标题>
**依据**：引用 diff 中触发该问题的具体代码片段（用 `行内代码` 包裹）
**问题**：描述该代码为何有缺陷
**建议**：给出具体的修改方式或代码示例

如果没有发现问题：
## 问题
未发现问题。

## 必须修改
<仅当 VERDICT 为 DENY 时 — 列出可操作的修改项>

## 改进建议
<仅当 VERDICT 为 APPROVE_WITH_NOTES 时 — 后续改进建议>
<如果变更涉及核心逻辑，建议需要补充的测试场景>

## VERDICT 判定规则
- 任何 HIGH 置信度的 CRITICAL → DENY
- HIGH 置信度的 MAJOR 但无 CRITICAL → APPROVE_WITH_NOTES
- 仅 MEDIUM 置信度问题或 MINOR → APPROVE_WITH_NOTES
- 仅无问题或所有问题置信度为 LOW → APPROVE
- lint 工具报错但你认为无害 → APPROVE_WITH_NOTES（附说明）

--- 以下为变更内容 ---

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

<code_context>
{code_context}
</code_context>

<lint_result>
{lint_result}
</lint_result>

<test_result>
{test_result}
</test_result>
"""


@dataclass
class ReviewResult:
    success: bool
    verdict: str = ""
    report_path: str = ""
    error: str = ""
    info: str = ""


def ensure_review_dir(dir_path):
    review_dir = Path(dir_path) / "docs" / "blink" / "code-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    return review_dir


def _extract_diff_files(diff_text):
    """Extract changed file paths from a unified diff."""
    files = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+?)$", diff_text, re.MULTILINE):
        files.append(match.group(2))
    return files


def _read_file_lines(dir_path, filepath, source_branch=None):
    """Read file lines from working tree or a specific branch via git show."""
    if source_branch:
        result = subprocess.run(
            ["git", "show", f"{source_branch}:{filepath}"],
            cwd=str(dir_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout.splitlines()
    full_path = Path(dir_path) / filepath
    if not full_path.exists():
        return None
    try:
        return full_path.read_text(errors="replace").splitlines()
    except OSError:
        return None


def _enrich_context(dir_path, diff_text, source_branch=None):
    """Enrich review context with surrounding code for changed files.

    For non-diff-only mode (source_branch=None): reads from working tree,
    which should be on the merged review branch.

    For diff-only mode (source_branch set): reads from the target branch
    via git show.
    """
    diff_files = _extract_diff_files(diff_text)
    if not diff_files:
        return ""

    file_hunks = {}
    current_file = None
    for line in diff_text.splitlines():
        m = re.match(r"^diff --git a/.+ b/(.+)$", line)
        if m:
            current_file = m.group(1)
            file_hunks[current_file] = []
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if m and current_file:
            start = int(m.group(1))
            length = int(m.group(2)) if m.group(2) else 1
            file_hunks[current_file].append((start, length))

    if not file_hunks:
        return ""

    contexts = []
    total_size = 0

    for filepath, hunks in file_hunks.items():
        if total_size >= CONTEXT_SIZE_LIMIT:
            break

        lines = _read_file_lines(dir_path, filepath, source_branch)
        if not lines:
            continue

        ranges = []
        for start, length in hunks:
            lo = max(0, start - 21)
            hi = min(len(lines), start + length + 19)
            ranges.append((lo, hi))

        ranges.sort()
        merged = []
        for lo, hi in ranges:
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))

        file_ctx_parts = []
        for lo, hi in merged:
            snippet = "\n".join(lines[lo:hi])
            file_ctx_parts.append(f"--- {filepath}:{lo+1}-{hi} ---\n{snippet}")

        file_ctx = "\n".join(file_ctx_parts)
        if total_size + len(file_ctx) > CONTEXT_SIZE_LIMIT:
            remaining = CONTEXT_SIZE_LIMIT - total_size
            file_ctx = file_ctx[:remaining] + "\n... (truncated)"

        contexts.append(file_ctx)
        total_size += len(file_ctx)

    return "\n\n".join(contexts)


def collect_context(dir_path, branch, base, with_lint=False, with_test=False, with_context=True):
    """Collect basic review context: diff, log, stat, rules.

    NOTE: lint, test, and context enrichment should be run AFTER branch setup
    via run_review(). The with_lint/with_test/with_context params are kept for
    backward compatibility but do nothing in this function.
    """
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
        "code_context": "(no additional context)",
        "lint_result": "(lint not run)",
        "test_result": "(tests not run)",
    }


def build_review_prompt(context):
    rules_block = context["rules"] if context["rules"] else "(No project-specific review rules defined)"
    diff_content = context["diff"]
    if context["truncated"]:
        diff_content += "\n\n... [DIFF TRUNCATED AT 100KB — original diff exceeds the limit]"

    return REVIEW_PROMPT.format(
        rules=rules_block,
        log=context.get("log") or "(no commits in range)",
        stat=context.get("stat") or "(no changes)",
        diff=diff_content or "(no diff)",
        code_context=context.get("code_context") or "(no additional context)",
        lint_result=context.get("lint_result") or "(lint not run)",
        test_result=context.get("test_result") or "(tests not run)",
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
            logger.log("review", "Warning: stash pop failed, run 'git stash pop' manually")
            success = False

    if not keep_branch and review_branch and git_ops.branch_exists(dir_path, review_branch):
        git_ops._git(dir_path, "branch", "-D", review_branch)

    return success


def parse_verdict(output, fallback="APPROVE_WITH_NOTES"):
    """Parse VERDICT from review output. Returns (verdict, output)."""
    if not output:
        return fallback, output or ""
    # Strict match: VERDICT at start of line
    matches = re.findall(r"^VERDICT:\s*(APPROVE_WITH_NOTES|DENY|APPROVE)\s*$", output, re.MULTILINE)
    if matches:
        return matches[-1], output
    # Less strict fallback
    matches = re.findall(r"VERDICT:\s*(APPROVE_WITH_NOTES|DENY|APPROVE)", output)
    if matches:
        return matches[-1], output
    return fallback, output


def _branch_slug(branch):
    slug = branch.replace("/", "-")
    slug = re.sub(r"-+", "-", slug)
    return slug


def save_report(dir_path, branch, base, verdict, content, extra_sections=None):
    review_dir = ensure_review_dir(dir_path)
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    slug = _branch_slug(branch)
    base_name = f"{slug}-{date_str}-{time_str}"
    report_path = review_dir / f"{base_name}.md"
    # Collision avoidance: append counter if file exists
    if report_path.exists():
        for n in range(2, 100):
            report_path = review_dir / f"{base_name}-{n}.md"
            if not report_path.exists():
                break

    verdict_labels = {
        "APPROVE": "✓ 通过",
        "APPROVE_WITH_NOTES": "⚠ 有建议",
        "DENY": "✗ 需修改",
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

    extra = ""
    if extra_sections:
        for title, body in extra_sections:
            extra += f"## {title}\n\n{body}\n\n---\n\n"

    report_path.write_text(header + extra + content)
    return str(report_path)


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
