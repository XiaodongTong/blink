# Review 功能流程图

AI Code Review 的完整执行流程，涵盖 CLI 和 TUI 两条入口路径。

## 入口分支

```
┌─────────────────────────────────────────────────────────┐
│                      用户触发 Review                      │
├──────────────────────────┬──────────────────────────────┤
│       CLI 入口            │         TUI 入口              │
│  blink review <branch>   │   快捷键触发 (R 键)            │
│  blink review -l         │   ReviewOrchestrator          │
│  blink review -i         │   .start_branch_select()      │
│  (cmd_review.handle)     │   (app_review.py)             │
│                          │   始终启用 lint/test/context/verify
└──────────┬───────────────┴──────────────┬───────────────┘
           │                              │
           │                   ┌──────────▼──────────┐
           │                   │ 后台线程获取最近分支   │
           │                   │ git_ops              │
           │                   │ .get_recent_branches │
           │                   └──────────┬──────────┘
           │                              │
           │                   ┌──────────▼──────────┐
           │                   │ 用户选择目标分支      │
           │                   │ (上下键 + Enter)     │
           │                   │ .confirm_branch()    │
           │                   └──────────┬──────────┘
           │                              │
           ▼                              ▼
┌──────────────────────────────────────────────────────────┐
│                 共享核心 Review 流程                       │
│  TUI 额外状态显示: collecting → merging → reviewing → verifying
└──────────────────────────┬───────────────────────────────┘
```

## 核心 Review 流程

```
1. 收集基础上下文 (collect_context)
   ├─ git diff <base>..<branch>          → 获取 diff（截断上限 100KB）
   ├─ git log --oneline <base>..<branch> → 获取提交日志
   ├─ git_ops.get_diff_stat()            → 获取变更统计
   ├─ 读取 docs/blink/review-rules.md    → 项目自定义规则
   │
   └─ diff 为空时 → 直接返回，不继续后续步骤
          │
          ▼
2. 创建临时 Review 分支 (setup_review_branch)
   │  仅非 --diff-only 模式执行
   │
   ├─ 检查工作树是否干净
   │   └─ 脏工作树 → git stash --include-untracked
   │
   ├─ checkout <base>
   ├─ checkout -b review/<branch>-<date>
   │
   ├─ git merge <colleague_branch> --no-edit
   │   ├─ 合并成功 → 继续后续步骤
   │   └─ 合并失败 → 检测冲突类型
   │       ├─ 有 CONFLICT → 立即生成 DENY 报告并返回
   │       └─ 其他错误    → 降级为 diff-only 模式
   │
   ▼
3. 在正确代码上增强上下文 (enrich after merge)
   │  此时工作树已在合并后的临时分支上
   │  diff-only 模式：通过 git show <branch>:<file> 读取目标分支文件
   │
   ├─ 代码上下文增强 (_enrich_context)
   │   ├─ 从 diff 提取变更文件和 hunk 位置
   │   ├─ 读取每个文件 ±20 行上下文代码
   │   ├─ 总量上限 50KB (CONTEXT_SIZE_LIMIT)
   │   └─ CLI: --no-context 跳过 / TUI: 始终执行
   │
   ├─ 静态分析 (review_analyzer.run_static_analysis)
   │   ├─ 按文件扩展名检测语言 (Python/Node/Go/Rust/Java)
   │   ├─ 运行可用 linter（ruff → flake8 → mypy / eslint / go vet 等）
   │   ├─ 过滤输出仅保留 diff 涉及的文件
   │   └─ CLI: --no-lint 跳过 / TUI: 始终执行
   │
   └─ 测试执行 (review_tester.run_tests)
       ├─ 自动检测测试框架（pytest/npm test/go test/cargo test 等）
       ├─ 运行测试，截取最后 2000 字符
       └─ CLI: --no-test 跳过 / TUI: 始终执行
          │
          ▼
4. 构建 Prompt (build_review_prompt)
   │
   ├─ 固定指令在前（提升缓存命中率）: 审查范围、维度、置信度门控、输出格式
   ├─ 变量内容在后:
   │   ├─ <rules>         → review-rules（无则占位提示）
   │   ├─ <commit_log>    → 提交日志
   │   ├─ <diff_stat>     → 变更统计
   │   ├─ <diff>          → 完整 diff（超限则标记 TRUNCATED）
   │   ├─ <code_context>  → 上下文增强代码片段
   │   ├─ <lint_result>   → 静态分析结果
   │   └─ <test_result>   → 测试执行结果
   │
   └─ 组装为结构化 REVIEW_PROMPT
      │
      ▼
5. 调用 Claude AI (run_claude_text)
   │
   ├─ 模型选择：CLI 用 config 中 review 默认值（--model 可覆盖） / TUI 用 config.model_review
   ├─ 输入 prompt → Claude → 输出 review 结果
   │
   ▼
6. 验证步骤 (review_verifier.verify_findings)
   │  CLI: --no-verify 跳过 / TUI: 始终执行
   │
   ├─ 将初始审核结果、原始 diff、lint 结果传入验证 prompt
   ├─ 逐条验证: 代码证据、逻辑正确性、严重度校准、lint 交叉验证
   ├─ 每条发现标记 VERIFIED / DISPUTED / UNCERTAIN
   └─ 基于验证结果重新输出 VERDICT（过滤误报）
   │  验证输出无 VERDICT 时，fallback 到初始审查的 VERDICT
   │
   ▼
7. 解析结果 (parse_verdict)
   │
   ├─ 严格正则匹配 VERDICT（行首），宽松匹配作 fallback
   ├─ 从最终输出（验证后或初始）提取 VERDICT:
   │   ├─ APPROVE             → ✓ 通过
   │   ├─ APPROVE_WITH_NOTES  → ⚠ 有建议
   │   └─ DENY                → ✗ 需修改
   │
   ├─ Strict 模式 (--strict):
   │   ├─ APPROVE_WITH_NOTES + 有 CRITICAL → 升级为 DENY
   │   └─ APPROVE_WITH_NOTES + 有 MAJOR    → 升级为 DENY
   │
   ▼
8. 保存报告 (save_report)
   │
   ├─ 路径: docs/blink/code-review/<branch>-<date>-<HHMMSS>.md
   ├─ 同名文件碰撞时自动追加序号
   ├─ 自动添加元数据头部（分支、基准、日期、结论）
   ├─ 如有验证结果，追加「验证结果」章节
   └─ 返回报告文件路径
   │
   ▼
9. 恢复工作区 (cleanup_review_branch)
   │  finally 块中执行，确保必定运行
   │
   ├─ checkout 回原始分支
   ├─ git stash pop（如之前 stash 了）
   ├─ 默认删除 review/* 临时分支（--keep-branch 保留）
   └─ 任何步骤失败时记录警告日志
```

## CLI 参数

```
blink review <branch>             审查指定分支
review -l, --list                 列出历史报告 (docs/blink/code-review/*.md)
                                     读取每个文件提取 VERDICT 并彩色显示
review -i, --init-rules           初始化 review-rules.md 模板
                                     路径: docs/blink/review-rules.md
                                     包含：必查项 / 历史教训 / 代码风格
review -d, --diff-only            diff-only 模式，跳过临时分支创建和合并
                                     注意：lint/test/context 在此模式下从目标分支读取
review -a, --against <branch>     指定 base 分支（默认自动检测 main/master）
review -m, --model <model>        指定 Claude 模型
review    --no-verify             跳过验证步骤（更快）
review    --no-lint               跳过静态分析
review    --no-test               跳过测试执行
review    --no-context            跳过代码上下文增强
review    --strict                严格模式：APPROVE_WITH_NOTES + MAJOR → DENY
review    --keep-branch           保留临时 review 分支（默认自动删除）
review -p, --dir <path>           项目目录（默认当前目录）
review -a, --against <branch>     指定 base 分支（默认自动检测 main/master）
review -m, --model <model>        指定 Claude 模型
review    --no-verify             跳过验证步骤（更快）
review    --no-lint               跳过静态分析
review    --no-test               跳过测试执行
review    --no-context            跳过代码上下文增强
review    --strict                严格模式：APPROVE_WITH_NOTES + MAJOR → DENY
review -p, --dir <path>           项目目录（默认当前目录）
```

## TaskReview（任务后自审）

Loop 任务执行后的自动代码自审，独立于主 Review 流程。

```
Loop 任务完成
    │
    ▼
run_task_review (task_review.py)
    ├─ 对比 base_commit..HEAD 的 diff
    ├─ 读取 docs/blink/constitution.md（如有），注入为 <constitution> 区块
    ├─ 调用 Claude CLI 进行自审（模型: config 中 task_review 默认值）
    │   ├─ 发现问题 → 自动修复，输出 <promise>COMPLETE</promise>
    │   └─ 无问题   → 输出 NO_ISSUES_FOUND
    └─ 不影响任务成败（non-blocking）
```

## 关键源文件

| 文件 | 职责 |
|------|------|
| `src/loop/cmd_review.py` | CLI review 入口 + 核心逻辑（收集上下文、构建 prompt、解析结果、保存报告） |
| `src/tui/app_review.py` | TUI review 编排（分支选择 UI、后台线程执行、review_stage 状态显示） |
| `src/loop/task_review.py` | TaskReview 自审（Loop 任务后自动触发） |
| `src/loop/git_ops.py` | Git 操作（创建/清理 review 分支、合并、冲突检测） |
| `src/loop/claude_runner.py` | Claude CLI 调用封装（run_claude_text 用于 review） |
| `src/loop/review_analyzer.py` | 静态分析集成（检测语言 → 运行 linter → 过滤结果） |
| `src/loop/review_verifier.py` | 审核结果验证（二次验证，过滤误报，重新判定 VERDICT） |
| `src/loop/review_tester.py` | 测试执行器（自动检测框架 → 运行测试 → 截取结果） |
