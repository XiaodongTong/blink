"""Review context collection and prompt building."""

import re
import subprocess
from pathlib import Path

from blink import logger
from blink.loop import git_ops

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
