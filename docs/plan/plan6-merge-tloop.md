# Plan 6: Blink 与 T-Loop 项目融合

## 目标

将 t-loop (`~/workingspace/t-loop/`) 的全部功能内嵌到 blink 中，用户无需单独安装 t-loop。blink 既作为 TUI 交互工具，也作为 t-loop 命令行入口。

## 设计原则

1. **tloop 逻辑独立性**：将 t-loop 源码整体复制到 `src/blink/loop/` 包下，保持模块间依赖关系不变，仅修改 import 路径
2. **尽量只添加，少修改**：blink 现有模块（cli、tui、models 等）改动最小化
3. **内部引用代替子进程调用**：TUI 中的 commit 和 task 操作不再 `shutil.which("tloop")` + `subprocess.Popen`，改为直接调用 tloop 包内的 Python 函数

## 架构

```
src/blink/
├── cli.py                # 修改：click group，添加 run/edit/commit/log 子命令
├── loop/                 # 新增：从 t-loop/src 整体迁入，改 import 路径
│   ├── __init__.py
│   ├── config.py         # tloop 配置常量（~/.blink/loop、颜色等）
│   ├── state.py          # state.json 管理
│   ├── task.py           # 单任务执行逻辑
│   ├── git_ops.py        # git 操作（auto-commit、branch）
│   ├── claude_runner.py  # Claude CLI runner（retry + verify）
│   ├── review.py         # Post-task code review
│   ├── cmd_run.py        # run 子命令 handler
│   ├── cmd_edit.py       # edit 子命令 handler
│   ├── cmd_commit.py     # commit 子命令 handler
│   ├── cmd_log.py        # log 子命令 handler
│   └── runner/           # 执行器后端
│       ├── __init__.py
│       ├── claude.py      # ClaudeRunner
│       └── cybervisor.py  # CybervisorRunner
├── config.py             # 不变：blink 配置
├── models.py             # 不变
├── scanner.py            # 不变
├── store.py              # 不变
└── tui/                  # 修改：commit/task 操作改为内部调用
    ├── app.py            # _run_commit / _run_add_task 改为调 tloop 内部函数
    ├── detail.py         # Commit 文案改为 "Auto Commit Changes"
    └── ...
```

## 变更详情

### 1. 新增 `src/blink/loop/` 包

从 `/Users/russell/workingspace/t-loop/src/` 将以下文件复制到 `src/blink/loop/`：

| 原文件 | 目标路径 | 修改内容 |
|--------|---------|---------|
| `config.py` | `src/blink/loop/config.py` | 修改内部 import：`import yaml` 等第三方库保持不变 |
| `state.py` | `src/blink/loop/state.py` | `import config` → `from blink.loop import config`；`import yaml` 保持 |
| `task.py` | `src/blink/loop/task.py` | 同上，所有 `import config` / `import git_ops` 等改为 `from blink.loop import ...` |
| `git_ops.py` | `src/blink/loop/git_ops.py` | `from claude_runner import ...` → `from blink.loop.claude_runner import ...` |
| `claude_runner.py` | `src/blink/loop/claude_runner.py` | 无 import 变更 |
| `review.py` | `src/blink/loop/review.py` | 无 import 变更 |
| `cmd_run.py` | `src/blink/loop/cmd_run.py` | 改 import 路径 |
| `cmd_edit.py` | `src/blink/loop/cmd_edit.py` | 改 import 路径 |
| `cmd_commit.py` | `src/blink/loop/cmd_commit.py` | 改 import 路径 |
| `cmd_log.py` | `src/blink/loop/cmd_log.py` | 改 import 路径 |
| `runner/__init__.py` | `src/blink/loop/runner/__init__.py` | 不变 |
| `runner/claude.py` | `src/blink/loop/runner/claude.py` | `from runner import Runner` → `from blink.loop.runner import Runner` |
| `runner/cybervisor.py` | `src/blink/loop/runner/cybervisor.py` | 同上 |

新增 `src/blink/loop/__init__.py`（可为空文件）。

**import 路径统一规则**：所有 t-loop 模块内部互相引用，一律改为 `from blink.loop.xxx import ...`。

### 2. 依赖变更：`pyproject.toml`

在 blink 的 `dependencies` 中添加 `pyyaml`：

```toml
dependencies = [
    "prompt-toolkit>=3.0,<4.0",
    "click>=8.0,<9.0",
    "pyyaml>=6.0",
]
```

### 3. CLI 入口变更：`src/blink/cli.py`

将 `@click.command()` 改为 `@click.group(invoke_without_command=True)`，使 blink 支持子命令，同时 `blink`（无子命令）仍进入 TUI。

```python
@click.group(invoke_without_command=True)
@click.option("--rescan", is_flag=True, default=False, help="Force a full rescan before launching TUI.")
@click.pass_context
def main(ctx, rescan: bool) -> None:
    """Blink — lightweight TUI for managing local git repositories."""
    if ctx.invoked_subcommand is not None:
        return
    # 原有 TUI 启动逻辑不变
    ...

# 子命令
@main.command()
@click.option("--status", "-s", is_flag=True, help="Show task status")
@click.option("--reset", is_flag=True, help="Reset all tasks to pending")
@click.option("--only", type=int, help="Run only task #N (1-based)")
@click.option("--continue", "-c", "continue_on_fail", is_flag=True, help="Continue even if a task fails")
@click.option("--review", "-r", is_flag=True, help="Run post-task code review")
def run(status, reset, only, continue_on_fail, review) -> None:
    """Run tasks defined in ~/.blink/loop/tasks.yaml."""
    from blink.loop.cmd_run import handle
    handle(argparse.Namespace(status=status, reset=reset, only=only, continue_on_fail=continue_on_fail, review=review))

@main.command("edit")
@click.argument("path", required=False)
@click.option("--editor", help="Override editor command for this session")
def edit_cmd(path, editor) -> None:
    """Open ~/.blink/loop/tasks.yaml in editor."""
    from blink.loop.cmd_edit import handle
    handle(argparse.Namespace(path=path, editor=editor))

@main.command()
@click.option("-p", "--path", default=".", help="Path to the git repository (default: current directory)")
@click.option("-m", "--model", type=click.Choice(["haiku", "sonnet", "opus"]), default="haiku", help="Claude model to use (default: haiku)")
def commit(path, model) -> None:
    """Auto-commit changes in the working tree."""
    from blink.loop.cmd_commit import handle
    handle(argparse.Namespace(path=path, model=model))

@main.command()
@click.argument("task_number", required=False, type=int)
def log(task_number) -> None:
    """View task logs."""
    from blink.loop.cmd_log import handle
    handle(argparse.Namespace(task_number=task_number))
```

**注意**：`--help` 和 `-h` 由 click 自动生成，无需额外处理。

### 4. TUI 内部调用变更

#### 4a. `src/blink/tui/app.py` — `_run_commit`

**变更前**（子进程调用）：
```python
if not shutil.which("tloop"):
    self._scan_status = "未安装 tloop"
    ...
proc = subprocess.Popen(["tloop", "commit", repo.path], ...)
```

**变更后**（内部函数调用）：
```python
def _run_commit(self, repo: Repo) -> None:
    if self._committing:
        return
    self._committing = True
    self._commit_spinner_index = 0
    self._tick_commit_spinner()

    def do_commit():
        from blink.loop.git_ops import is_git_repo, is_git_clean, ensure_clean_git
        dir_path = repo.path
        if not is_git_repo(dir_path) or is_git_clean(dir_path):
            return True
        return ensure_clean_git(dir_path, "manual commit", model="haiku")

    def on_done(success: bool):
        self._stop_commit_spinner()
        if success:
            self._refresh_repo_status(repo)
            self._scan_status = "✓ 提交完成"
        else:
            self._scan_status = "✗ 提交失败"
        self._app.invalidate()
        self._start_timer(3.0, self._clear_scan_status)

    t = threading.Thread(target=lambda: on_done(do_commit()), daemon=True)
    t.start()
```

#### 4b. `src/blink/tui/app.py` — `_run_add_task`

**变更前**（子进程调用）：
```python
if not shutil.which("tloop"):
    ...
proc = subprocess.Popen(["tloop", "edit", repo.path], ...)
```

**变更后**（内部函数调用）：
```python
def _run_add_task(self, repo: Repo) -> None:
    from blink.loop.cmd_edit import _add_task
    _add_task(repo.path)
    self._set_scan_status("✓ Task 已更新")
```

#### 4c. `src/blink/tui/detail.py` — Commit 文案

将 "Commit Changes" 改为 "Auto Commit Changes"：

```python
# _SHORTCUT_HINTS 或 Actions 区域中的文案
("Shift+C", "commit"),        # footer 保持简洁
# Actions 行描述
"Auto Commit Changes"          # 替代 "Commit Changes"
```

### 5. Help 文本兼容

blink 子命令的 `--help` / `-h` 由 click 自动处理，效果等同于 tloop 原版 argparse 的 help 输出。关键映射：

| 命令 | blink 调用 | 等效 tloop 调用 |
|------|-----------|----------------|
| `blink run --status` | `handle(status=True, ...)` | `tloop run --status` |
| `blink run --only 2` | `handle(only=2)` | `tloop run --only 2` |
| `blink run --confirm` | 需映射到 `-c`，此处 tloop 原版无 `--confirm` | — |
| `blink edit ~/proj` | `handle(path="~/proj")` | `tloop edit ~/proj` |
| `blink commit -p /path` | `handle(path="/path")` | `tloop commit -p /path` |
| `blink log 3` | `handle(task_number=3)` | `tloop log 3` |
| `blink --help` | click group help | — |
| `blink run --help` | click subcommand help | — |

## 不涉及

- 左侧 Repo List 无变更
- 搜索功能无变更
- Store / Scanner / Blink Config 无变更
- 编辑模式（alias/tags/desc/pinned）行为不变
- `~/.blink/loop/` 数据目录结构不变，tloop 配置文件格式不变
- t-loop 的 `archive` 和 `migrate` 子命令暂不迁入（可后续按需添加）

## 涉及文件

| 文件 | 变更类型 |
|------|---------|
| `src/blink/loop/` 整个目录 | 新增：从 t-loop 迁入 |
| `src/blink/cli.py` | 修改：`click.command` → `click.group` + 4 个子命令 |
| `src/blink/tui/app.py` | 修改：`_run_commit` 和 `_run_add_task` 改内部调用 |
| `src/blink/tui/detail.py` | 修改：Commit 文案改为 "Auto Commit Changes" |
| `pyproject.toml` | 修改：添加 `pyyaml` 依赖 |
| `CLAUDE.md` | 更新：Architecture 章节、Commands 章节 |
| `README.md` | 更新：Commands 章节、子命令说明 |

## 实施步骤

1. 在 blink 中添加 `pyyaml` 依赖，`uv sync` 确认安装
2. 将 t-loop 源码复制到 `src/blink/loop/`，批量修改 import 路径
3. 修改 `cli.py` 为 click group + 子命令
4. 验证 CLI：`blink --help`、`blink run --help`、`blink commit --help` 等
5. 修改 `app.py` 中 `_run_commit` 和 `_run_add_task` 为内部调用
6. 修改 `detail.py` Commit 文案
7. 运行 `uv run blink` 验证 TUI 功能不受影响
8. 运行 `uv run pytest` 确认测试通过
9. 同步更新 `CLAUDE.md` 和 `README.md`
