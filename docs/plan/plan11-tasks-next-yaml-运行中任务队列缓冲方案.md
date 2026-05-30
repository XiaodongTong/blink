# tasks-next.yaml — 运行中任务队列缓冲方案

## 背景

当前 `blink run` 在启动时一次性加载 `tasks.yaml` 到内存，运行期间不再回读文件。若用户在任务执行过程中通过 `blink edit --add PATH` 或 TUI "Add todo task" 新增任务，新任务会直接写入 `tasks.yaml`，但这些修改不会影响当前运行批次（已加载到内存），且会在 `archive_completed_tasks()` 时被覆盖或导致状态索引错乱。

需要一个缓冲机制：运行中的任务批次不被打扰，新增任务排队等待下一轮执行。

## 方案

### 核心思路

引入 `~/.blink/loop/tasks-next.yaml` 作为待执行队列文件。当检测到有任务正在运行时，新增任务写入 `tasks-next.yaml` 而非 `tasks.yaml`；当前批次全部完成后，自动将 `tasks-next.yaml` 中的任务迁移到 `tasks.yaml` 并触发新一轮 `blink run`。

### 1. 检测运行中任务

新增辅助函数（放在 `state.py` 或 `config.py`）：

```python
def has_running_tasks() -> bool:
    """检查 state.json 中是否存在 status == 'running' 的任务。"""
    state = load_state()
    return any(
        ts.get("status") == "running"
        for ts in state.get("tasks", {}).values()
    )
```

### 2. 新增常量

在 `config.py` 中增加：

```python
NEXT_TASKS_FILE = TLOOP_HOME / "tasks-next.yaml"
```

### 3. 修改 `blink edit --add PATH`（`cmd_edit.py`）

`_add_task()` 函数增加目标文件参数：

```python
def _add_task(path, target_file=None):
    """Append a guided task entry. target_file 默认为 TASKS_FILE，可指定 NEXT_TASKS_FILE。"""
    target = target_file or config.TASKS_FILE
    # ... 后续读写操作将 TASKS_FILE 替换为 target
```

`handle()` 中调用时判断：

```python
if add_path:
    from blink.loop.state import has_running_tasks
    target = config.NEXT_TASKS_FILE if has_running_tasks() else None
    msg = _add_task(add_path, target_file=target)
    if target:
        msg += " → tasks-next.yaml (有任务运行中，排队等待)"
```

### 4. 修改 TUI Add todo task（`app_actions.py`）

`_run_add_task()` 中同样判断：

```python
from blink.loop.state import has_running_tasks
target = config.NEXT_TASKS_FILE if has_running_tasks() else None
msg = _add_task(repo.path, target_file=target)
```

状态栏提示区分写入目标。

### 5. 修改 `blink run` 完成后迁移逻辑（`cmd_run.py`）

在 `handle()` 末尾，`archive_completed_tasks()` 之后增加：

```python
archive_completed_tasks(cfg, state)

# 检查 tasks-next.yaml
if config.NEXT_TASKS_FILE.exists():
    next_data = yaml.safe_load(config.NEXT_TASKS_FILE.read_text()) or {}
    next_tasks = next_data.get("tasks", [])
    if next_tasks:
        # 读取当前 tasks.yaml（归档后可能为空）
        cur_data = load_config()
        cur_tasks = cur_data.get("tasks", [])
        cur_tasks.extend(next_tasks)
        cur_data["tasks"] = cur_tasks
        content = yaml.dump(cur_data, default_flow_style=False, allow_unicode=True)
        config.TASKS_FILE.write_text(config.TASKS_YAML_HEADER + content)
        config.NEXT_TASKS_FILE.unlink()
        print(f"{config.GREEN}Migrated {len(next_tasks)} task(s) from tasks-next.yaml{config.RESET}")

        # 递归调用自身，执行迁移过来的任务
        return handle(args)
```

注意：递归调用前需要确保 `state` 已重置（`archive_completed_tasks` 已经调用了 `save_state({"tasks": {}, "version": 1})`），所以是安全的。

### 6. `blink run --status` 展示队列信息

在 `show_status()` 末尾增加：

```python
if config.NEXT_TASKS_FILE.exists():
    next_data = yaml.safe_load(config.NEXT_TASKS_FILE.read_text()) or {}
    next_tasks = next_data.get("tasks", [])
    if next_tasks:
        print(f"\n  📋 {len(next_tasks)} task(s) queued in tasks-next.yaml")
```

### 文件格式

`tasks-next.yaml` 与 `tasks.yaml` 格式完全一致：

```yaml
tasks:
  - name: Task N
    dir: ~/projects/my-project
    prompt: |
      ...
```

## 影响范围

| 文件 | 改动类型 |
|------|----------|
| `src/loop/config.py` | 新增 `NEXT_TASKS_FILE` 常量 |
| `src/loop/state.py` | 新增 `has_running_tasks()` 函数 |
| `src/loop/cmd_edit.py` | `_add_task()` 增加 `target_file` 参数；`handle()` 增加运行检测 |
| `src/loop/cmd_run.py` | `handle()` 末尾增加 `tasks-next.yaml` 迁移 + 递归执行 |
| `src/tui/app_actions.py` | `_run_add_task()` 增加运行检测 |
| `src/loop/state.py` | `show_status()` 增加队列提示 |

## 待定

- **并发安全**：`has_running_tasks()` 读 `state.json` 与 `blink run` 写 `state.json` 之间无锁，极端时序可能读到过时状态。实际场景中窗口极短（用户手动操作 vs 任务状态更新），可接受。若需严格保证，可引入文件锁。
- **tasks-next.yaml 中的 `--add` 累积**：多次 `edit --add` 会追加到 `tasks-next.yaml`，需确保 YAML 追加逻辑与首次创建一致（当前 `_add_task` 已处理 `tasks: []` 和追加两种情况）。
- **是否需要 `blink edit` 直接编辑 `tasks-next.yaml`**：用户可能希望编辑排队中的任务，可后续增加 `blink edit --next` 参数。
- **`--reset` 与 `tasks-next.yaml` 的交互**：`blink run --reset` 是否应同时清除 `tasks-next.yaml`？建议是。
