"""Verification pass for code review findings — filters false positives."""

from blink.loop.claude_runner import run_claude_text

VERIFY_PROMPT = """\
你是一名代码审查验证专家。你的任务是对另一名审查员的发现进行逐条验证，过滤误报。

## 验证规则

对初始审查中报告的每个问题，逐一验证：

1. **代码证据**：该问题是否能从 <diff> 中的实际代码得到支撑？如果审查员引用的代码行在 diff 中不存在，标记为 DISPUTED。
2. **逻辑正确性**：审查员对问题的描述是否在逻辑上成立？是否存在误读代码的情况？
3. **严重度校准**：严重度是否合理？如果一个 MEDIUM_CONFIDENCE 的问题缺乏具体触发场景，降级或标记为 DISPUTED。
4. **lint 交叉验证**：如果 <lint_result> 中有相关发现，可提升置信度；如果 lint 没有报告且你也不确定，降低置信度。

## 输出格式

对每个问题，输出验证结果：

### 验证结果

| # | 问题摘要 | 验证状态 | 说明 |
|---|---------|---------|------|
| 1 | <摘要> | VERIFIED / DISPUTED / UNCERTAIN | <简要说明> |
| 2 | ... | ... | ... |

### 最终判定

基于验证后的发现，重新生成最终判定：

VERDICT: <APPROVE|APPROVE_WITH_NOTES|DENY>

判定规则：
- 仅当存在 VERIFIED 的 CRITICAL 问题时 → DENY
- 存在 VERIFIED 的 MAJOR 问题但无 CRITICAL → APPROVE_WITH_NOTES
- 仅有 DISPUTED/UNCERTAIN 问题或 MINOR → APPROVE
- 所有问题均被 DISPUTED → APPROVE

--- 以下为待验证内容 ---

<diff>
{diff}
</diff>

<lint_result>
{lint_result}
</lint_result>

## 待验证的发现

以下是初始审查员的完整输出：

<initial_review>
{initial_review}
</initial_review>
"""


def verify_findings(dir_path, initial_output, diff, lint_result, model="opus", quiet=False):
    """Run a verification pass on initial review findings."""
    prompt = VERIFY_PROMPT.format(
        diff=diff,
        lint_result=lint_result,
        initial_review=initial_output,
    )

    return run_claude_text(
        prompt,
        cwd=str(dir_path),
        model=model,
        quiet=quiet,
    )
