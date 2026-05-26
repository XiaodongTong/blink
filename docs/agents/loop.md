# Loop 模块文档

Blink Loop 是 AI 任务编排引擎，通过 `tasks.yaml` 定义待执行任务，按顺序调用 AI Runner 自动完成代码编写、提交、审查等流程。

## 产品能力

Loop 提供三组 CLI 命令，覆盖 AI 任务的全生命周期：

| 命令 | 功能 |
|------|------|
| `blink run` | 按 tasks.yaml 顺序执行任务 |
| `blink edit` | 编辑任务文件，支持 `--add` 快速添加 |
| `blink commit` | AI 自动提交（独立于任务系统，可单独使用） |
| `blink log` | 查看任务执行日志 |
| `blink review` | AI Code Review — 同事分支合并审查（独立于任务系统） |

其中 `commit` 和 `review` 可在 TUI 中通过快捷键（Shift+C / Shift+V）触发，也可作为 CLI 命令独立使用。`run --task-review` 用于任务执行后的自审。

## 架构概览

```
tasks.yaml (用户定义)
    │
    ▼
cmd_run.py ── 加载配置 + 状态
    │
    ▼
task.py ── 逐任务编排
    │
    ├── git_ops.py ─── ensure_clean_git() → claude_runner.py (auto-commit)
    ├── git_ops.py ─── create_task_branch()
    ├── runner/ ────── ClaudeRunner 或 CybervisorRunner 执行 AI 任务
    └── task_review.py ─ TaskReview：post-task 自审（可选）
    │
    ▼
state.py ─── 更新状态 + 归档已完成任务
```

数据目录结构：

```
~/.blink/loop/
  tasks.yaml     — 任务定义
  state.json     — 运行时状态（任务执行结果）
  logs/          — 结构化执行日志（YYYYMMDD-HHMMSS-任务名.log）
  archive/       — 已完成任务的归档（run-YYYYMMDD-HHMMSS.yaml）
```

## 任务配置（tasks.yaml）

任务定义在 `~/.blink/loop/tasks.yaml`，首次运行 `blink run` 时自动创建模板。

```yaml
tasks:
  - name: 实现用户认证
    dir: ~/projects/my-app
    prompt: |
      添加基于 JWT 的用户认证模块，
      包含登录、注册、token 刷新接口。
    # 或者使用外部 prompt 文件：
    # prompt_file: ./prompts/auth-task.md
    branch: true           # true=自动创建 feature 分支
    task_review: true      # 任务完成后执行 TaskReview 自审
    use: claude            # claude 或 cybervisor（默认）
    max_rounds: 5          # ClaudeRunner 最大循环轮数
    commit-model: haiku    # auto-commit 使用的模型
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 任务名称（用于日志和状态显示） |
| `dir` | 是 | 任务执行目录（支持 `~` 和环境变量） |
| `prompt` | 二选一 | 内联 prompt 文本 |
| `prompt_file` | 二选一 | 外部 prompt 文件路径（优先级：绝对路径 → `~/.blink/loop/` 相对 → `dir` 相对） |
| `branch` | 否 | 分支策略：`true` 自动创建 `feature-YYYYMMDD-N`、字符串指定分支名、`false` 跳过 |
| `task_review` | 否 | `true` 任务完成后自动执行 TaskReview 代码自审 |
| `use` | 否 | Runner 选择：`cybervisor`（默认）或 `claude` |
| `max_rounds` | 否 | ClaudeRunner 最大循环轮数（默认 5） |
| `commit-model` | 否 | auto-commit 使用的 Claude 模型（默认 `haiku`） |

### 项目级 AI 指令

在项目目录下放置 `docs/blink/constitution.md`，ClaudeRunner 执行时会自动加载为 constitution 约束。CybervisorRunner 不使用此文件。

## Runner 系统

Loop 通过 Runner ABC 抽象不同的 AI 执行后端，位于 `src/loop/runner/`。

### CybervisorRunner（默认）

- 调用 `cybervisor run` 命令
- 通过 stdin 传入 prompt（如果指定了 prompt_file 则直接作为文件句柄）
- 单次执行，返回进程退出码
- 适合简单的一次性任务

### ClaudeRunner

- 调用 `claude -p --dangerously-skip-permissions --model opus`
- 多轮循环执行：每轮将 prompt + constitution（如果存在）通过 stdin 传入
- 通过 `<promise>COMPLETE</promise>` 信号检测完成
- 达到 `max_rounds` 仍未收到完成信号则视为失败
- 适合需要多步迭代的复杂任务

### 共同接口

```python
class Runner(ABC):
    @abstractmethod
    def run(self, prompt, cwd, log_file=None):
        """Run a task. Returns exit code (0=success)."""
```

## 任务执行流程

单个任务（`task.run_task()`）的完整流程：

```
1. 解析 dir（~ 展开、环境变量展开）
2. 解析 prompt / prompt_file
3. ensure_clean_git()
   ├── 检测工作树是否干净
   ├── 有 staged changes → Claude auto-commit（带敏感文件检查）
   └── 有 unstaged changes → git add -A → Claude auto-commit
4. create_task_branch()
   ├── branch=false → 跳过
   ├── branch=true → feature-YYYYMMDD-N（自增序号）
   └── branch="name" → 使用指定名称或自增
5. 选择 Runner 并执行
   ├── use=cybervisor → CybervisorRunner.run()
   └── use=claude → ClaudeRunner.run()（多轮循环）
6. 更新 state.json（running → done/failed）
7. 如果 task_review=true → task_review.run_task_review()
   └── 对比 base_commit 与当前 HEAD 的 diff → Claude 自审
```

### 状态机

每个任务的状态流转：`pending` → `running` → `done` / `failed`

状态持久化在 `state.json`，以任务索引为 key：

```json
{
  "tasks": {
    "0": {"status": "done", "started_at": "...", "finished_at": "..."},
    "1": {"status": "failed", "error": "..."}
  },
  "version": 1
}
```

### 归档机制

每次 `blink run` 结束后自动归档：
1. 已完成任务从 tasks.yaml 移除，移入 `archive/run-YYYYMMDD-HHMMSS.yaml`
2. state.json 重置
3. 失败和 pending 任务保留在 tasks.yaml 中

## Git 安全机制

### Auto-commit（`git_ops.ensure_clean_git()`）

任务执行前确保工作树干净：

1. 检查是否有 staged changes → 用 Claude 生成 commit message 提交
2. 检查是否有 unstaged changes → `git add -A` → 用 Claude 提交
3. 提交时自动排除敏感文件（`.env`、凭据、密钥等）
4. 最多重试 3 次，带验证（`verify_fn=is_git_clean`）

实现层在 `claude_runner.py` 的 `run_claude()`：
- 调用 `claude --dangerously-skip-permissions --print`
- 支持 `verify_fn` 验证结果
- 支持 `max_retries`（默认 3）+ 递增式提示
- 超时 300 秒

### 分支管理（`git_ops.create_task_branch()`）

- 检测 detached HEAD 状态，拒绝在 detached HEAD 创建分支
- `branch: true` → `feature-YYYYMMDD-001`（序号自增到可用）
- `branch: "custom-name"` → 使用指定名称，已存在则追加 `-N`
- 分支创建失败则任务标记为 failed

### 独立 commit 命令

`blink commit -p <path> -m <model>` 可独立使用，同样走 `ensure_clean_git()` 流程。

## Code Review

Loop 提供两种 review 能力：

### TaskReview（`task_review.py`）

任务完成后可选执行，对比任务前后 diff，让 Claude 自行检查代码质量：
- 检查维度：Bugs、Security、Error handling、Edge cases
- 发现问题则自动修复，无问题输出 `NO_ISSUES_FOUND`
- 通过任务配置 `task_review: true` 或 `blink run --task-review` 启用

### 同事分支 Review（`cmd_review.py`）

独立的 AI Code Review 命令，对指定分支进行结构化审查（`blink review`）：

```bash
blink review <branch>          # 完整模式：创建临时分支 + 合并 + review
blink review <branch> -d       # diff-only 模式：不创建临时分支
blink review <branch> -a main  # 指定 base 分支
blink review <branch> -m opus  # 指定模型
blink review -l                # 列出历史报告
blink review -i                # 创建 review-rules.md 模板
```

完整模式流程：
1. 收集上下文：diff、commit log、stat、项目规则
2. 创建临时 review 分支（`review/<branch-slug>-YYYYMMDD`）
3. 合并目标分支到 base 分支
4. 如有冲突 → 生成 DENY 报告
5. 调用 `run_claude_text()` 执行 review
6. 解析 VERDICT（`APPROVE` / `APPROVE_WITH_NOTES` / `DENY`）
7. 保存报告到 `docs/blink/code-review/<branch-slug>-YYYYMMDD.md`
8. 清理临时分支

### Review 规则

项目可在 `docs/blink/review-rules.md` 定义项目特定的 review 规则（通过 `blink review -i` 创建模板）。

### Anti-hallucination 设计

Review prompt 采用多层防护避免幻觉：
- 限定只能审查 diff 中实际出现的代码变更
- 要求引用具体代码片段作为依据（`**依据**`）
- 不确定问题标记为 `[疑似]` 并降级严重程度
- 排除代码风格/命名/注释等非行为性问题

## 日志系统

任务日志保存在 `~/.blink/loop/logs/`，文件名格式 `YYYYMMDD-HHMMSS-任务名.log`。

日志格式（`log_format.py`）：

```
Task:       实现用户认证
Directory:  ~/projects/my-app
Runner:     ClaudeRunner (max_rounds=5)
Command:    claude -p --dangerously-skip-permissions --model opus
Started:    2026-05-26 14:30:00

[14:30:01]-[branch] 创建分支: feature-20260526-001

[14:30:02]-[implement]-[input] ...
[14:30:15]-[implement]-[output] ...
[14:30:20]-[implement] Completion signal detected

════════════════════════════════════════════════════════════
[14:35:00]-[finished] 2026-05-26 14:35:00 | Duration: 5m 0s | ✅ done
════════════════════════════════════════════════════════════
```

每个日志记录包含：
- Header：任务名、目录、Runner 信息、启动时间
- Branch：分支创建记录
- Implement：AI 输入/输出（ClaudeRunner 按轮次记录）
- TaskReview：post-task 自审记录（如果启用）
- Auto-commit：自动提交记录
- Footer：完成时间、耗时、状态

## CLI 子命令参考

### `blink run` — 执行任务

```bash
blink run              # 执行所有 pending 任务
blink run -s           # 查看任务状态
blink run -e           # 重置所有任务为 pending
blink run -o 2         # 仅执行第 2 个任务
blink run -c           # 任务失败后继续执行
blink run -r           # 每个任务完成后执行 TaskReview
```

### `blink edit` — 编辑任务

```bash
blink edit             # 打开 tasks.yaml 编辑器
blink edit --add .     # 为当前目录添加任务条目后打开编辑器
```

### `blink commit` — AI 自动提交

```bash
blink commit           # 提交当前目录的变更
blink commit -p ~/proj # 提交指定目录的变更
blink commit -m opus   # 使用 opus 模型
```

### `blink log` — 查看日志

```bash
blink log              # 列出所有日志文件
blink log 2            # 查看第 2 个任务的日志
```

### `blink review` — AI Code Review

```bash
blink review feat/login         # review feat/login 分支
blink review feat/login -d      # diff-only 模式
blink review feat/login -a dev  # 指定 base 分支为 dev
blink review feat/login -m opus # 使用 opus 模型
blink review -l                 # 列出历史报告
blink review -i                 # 创建 review-rules.md 模板
```
