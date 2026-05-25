# 关键开发模式

## Store 懒连接

- `_connect()` 首次访问时建立连接
- `check_same_thread=False` 支持后台扫描线程

## 扫描与状态获取

- `Scanner.run_scan(blocking=True/False)` 同步/线程切换
- `StatusFetcher.run_fetch(repos, blocking, on_status, on_error, on_done)` 同模式
  - 单仓库失败调 `on_error(repo_id)` 保留缓存状态
  - TUI 通过 `RepoListControl.error_repo_ids` 显示 `⚠`
  - 启动时和 Shift+R rescan 完成后触发

## TUI 渲染

- `app.invalidate()` 触发重绘
- 样式类名避开 prompt_toolkit 内置名（如 `repo-selected` 而非 `selected`）

## Config 回退

- 文件缺失或损坏时回退默认值并重写
- `nerd_fonts` 键（默认 `false`）控制图标渲染

## 详情面板同步

- `set_repo(repo)` 实时同步列表选择
- 光标覆盖 Actions（0-6）+ Local Markers（7-10），Metadata 只读
- `set_focused(bool)` 控制选中高亮
- `_wrap_value()` CJK 感知宽度计算

## 焦点管理

- 单一 VSplit 布局，`_focus_pane` 三态（`"list"` / `"detail"` / `"edit"`）
- 焦点切换动态更新边框样式，无布局替换
- 按键绑定用 `Condition` 过滤器实现焦点依赖行为
- `←`/`→` 同时处理 IDE 选择（优先）和焦点切换

## IDE 选择

- `_ide_selecting` 是状态栏临时覆盖层
- `_open_with_ide(path)` 通用 IDE 打开（仓库或文件）
- 先检查 `Config.preferred_ide`，未设置则进入选择模式

## 提交与拉取

- TUI commit（`_run_commit`）直接调用 `blink.loop.git_ops.ensure_clean_git()` 后台线程
- `quiet=True`，无子进程，无 PATH 依赖，无 stdout 污染
- 状态栏显示静态"正在提交..."/"正在拉取..."

## 任务操作

- TUI Shift+T 调用 `blink.loop.cmd_edit._add_task()` 返回消息字符串
- 然后通过 `_open_with_ide()` 打开 tasks.yaml
- CLI `blink edit --add PATH` 同样调用 `_add_task()` 后打开 IDE

## 数据目录

- 循环任务数据：`~/.blink/loop/`（含 `tasks.yaml`、`state.json`、`logs/`、`archive/`）
- 应用日志：`~/.blink/logs/blink-YYYY-MM-DD.log`
- SQLite 数据库：`~/.blink/blink.db`
- 配置：`~/.blink/config.json`

## 测试

- 测试通过 subprocess 在 `tmp_path` fixture 中创建真实 git 仓库
- 运行：`uv run pytest`，单文件：`uv run pytest tests/test_scanner.py`，单测试：`uv run pytest -k test_name`

## CLI 结构

- `click.group(invoke_without_command=True)`
- `--rescan` 挂在 group 上
- 子命令使用懒加载避免加载 loop 模块
- 调试：在源码插入 `breakpoint()`，运行 `uv run blink` 进入 pdb
