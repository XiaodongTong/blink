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
└──────────────────────────┬───────────────────────────────┘
```

## 核心 Review 流程

```
1. 收集上下文 (collect_context)
   ├─ git diff <base>..<branch>          → 获取 diff（截断上限 100KB）
   ├─ git log --oneline <base>..<branch> → 获取提交日志
   ├─ git_ops.get_diff_stat()            → 获取变更统计
   └─ 读取 docs/blink/review-rules.md    → 项目自定义规则
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
   │       └─ 其他错误    → 回退 stash，降级为 diff-only 模式
   │
   ▼
3. 构建 Prompt (build_review_prompt)
   │
   ├─ 注入 review-rules（如有）
   ├─ 注入 commit log
   ├─ 注入 diff stat
   ├─ 注入完整 diff（超限则标记 TRUNCATED）
   └─ 组装为结构化 REVIEW_PROMPT
      │
      ▼
4. 调用 Claude AI (run_claude_text)
   │
   ├─ 模型选择：CLI 默认 opus / TUI 用 config.model_review
   ├─ 输入 prompt → Claude → 输出 review 结果
   │
   ▼
5. 解析结果 (parse_verdict)
   │
   ├─ 从输出提取 VERDICT:
   │   ├─ APPROVE             → ✓ 通过
   │   ├─ APPROVE_WITH_NOTES  → ⚠ 有建议
   │   └─ DENY                → ✗ 需修改
   │
   ▼
6. 保存报告 (save_report)
   │
   ├─ 路径: docs/blink/code-review/<branch>-<date>.md
   ├─ 自动添加元数据头部（分支、基准、日期、结论）
   └─ 返回报告文件路径
   │
   ▼
7. 保留临时分支，恢复工作区
   │  finally 块中执行，确保必定运行
   │
   ├─ checkout 回原始分支
   └─ git stash pop（如之前 stash 了）
   │
   └─ review/* 临时分支保留不删除，供用户手动验证
```

## 辅助功能

```
review -l  →  列出历史报告 (docs/blink/code-review/*.md)
                读取每个文件提取 VERDICT 并彩色显示

review -i  →  初始化 review-rules.md 模板
                路径: docs/blink/review-rules.md
                包含：必查项 / 历史教训 / 代码风格

review -d  →  diff-only 模式，跳过临时分支创建和合并
review -a  →  指定 base 分支（默认自动检测 main/master）
```

## TaskReview（任务后自审）

Loop 任务执行后的自动代码自审，独立于主 Review 流程。

```
Loop 任务完成
    │
    ▼
run_task_review (task_review.py)
    ├─ 对比 base_commit..HEAD 的 diff
    ├─ 读取 docs/blink/constitution.md（如有）
    ├─ 调用 Claude CLI 进行自审
    │   ├─ 发现问题 → 自动修复，输出 <promise>COMPLETE</promise>
    │   └─ 无问题   → 输出 NO_ISSUES_FOUND
    └─ 不影响任务成败（non-blocking）
```

## 关键源文件

| 文件 | 职责 |
|------|------|
| `src/loop/cmd_review.py` | CLI review 入口 + 核心逻辑（收集上下文、构建 prompt、解析结果、保存报告） |
| `src/tui/app_review.py` | TUI review 编排（分支选择 UI、后台线程执行） |
| `src/loop/task_review.py` | TaskReview 自审（Loop 任务后自动触发） |
| `src/loop/git_ops.py` | Git 操作（创建/清理 review 分支、合并、冲突检测） |
| `src/loop/claude_runner.py` | Claude CLI 调用封装 |
