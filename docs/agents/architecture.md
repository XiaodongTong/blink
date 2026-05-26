# 架构与数据流

## 入口点

`src/blink/cli.py` — click group，`invoke_without_command=True`。无子命令时启动 TUI。

子命令（`run` / `edit` / `commit` / `log` / `review`）通过 argparse.Namespace shim 委托给 `blink.loop` 处理函数。`--rescan` 挂在 group 上。子命令使用懒加载避免 TUI 启动时加载 loop 模块。

## 核心模块

所有模块位于 `src/blink/`。

### models.py
- `Repo` 数据类：含 `pinned`、`view_count`、`status` 字段
- `Remote`、`RepoStatus` 数据类
- `display_width()`：CJK 字符宽度计算工具

### logger.py
- 按天轮转日志，写入 `~/.blink/logs/blink-YYYY-MM-DD.log`
- 格式：`[HH:MM:SS]-[module] message`
- 线程安全（lock）
- `log(module, message)` 单行，`log_lines(module, content)` 多行
- 集成于：review（AI prompt + 输出）、claude_runner（调用跟踪）、TUI（commit/pull/scan/task）

### config.py
- JSON 配置加载器（`~/.blink/config.json`）
- 默认值：scan_paths、excludes、editor、`nerd_fonts`
- 文件缺失或损坏时回退默认值并重写

### scanner.py
- `Scanner`：遍历文件系统查找 `.git` 目录，通过 git 子进程获取 remotes/description
- `StatusFetcher`：并行获取 git status（分支、dirty 数、ahead/behind）
  - 使用 `git status --porcelain=v2 --branch`
  - `ThreadPoolExecutor` 并行处理
  - 支持阻塞和后台（线程）模式
- `parse_status_v2()`：解析 porcelain v2 输出
- `parse_pull_output()`：解析 `git pull` 输出为 `(success, message)`
- `check_pull_prereqs(repo)`：验证仓库是否符合 pull 条件

### store.py
- SQLite 持久化层（WAL 模式）
- 表：`repos`、`remotes`、`repo_status`、`schema_version`
- Upsert 写入，全文搜索（name/alias/description/path/remote URL）
- Schema 迁移：v1→v2 加 `pinned`/`view_count`；v2→v3 加 `repo_status` 表
- `get_all_repos()` / `search_repos()` LEFT JOIN `repo_status` 填充 `Repo.status`
- 排序：`pinned DESC, view_count DESC, name ASC`

## 数据流

```
Scanner 发现 git 目录
  → 创建 ScanResult(repo, remotes)
  → Store upsert 到 SQLite
  → TUI 从 Store 加载展示/搜索

StatusFetcher 获取 git status
  → Store upsert 到 repo_status
  → TUI 重载 repos（LEFT JOIN status）显示徽标

列表导航 → _sync_detail_panel() → detail.set_repo(repo) 实时更新右面板
TUI Shift+C → blink.loop.git_ops.ensure_clean_git() 后台线程
TUI Shift+T → blink.loop.cmd_edit._add_task() → _open_with_ide()
CLI blink edit --add PATH → _add_task() → 打开 IDE
```

## 循环任务包（Loop）

> 详细文档见 [Loop 模块文档](loop.md)。

`src/blink/loop/` 目录，数据存储在 `~/.blink/loop/`。模块速查：

| 模块 | 职责 |
|------|------|
| `config.py` | 常量（目录路径、ANSI 颜色、YAML 头）、`ensure_tloop_home()`、`load_config()` |
| `state.py` | JSON 状态文件管理（`state.json`），任务状态追踪与归档 |
| `git_ops.py` | Git 安全检查、auto-commit（`ensure_clean_git`）、分支创建 |
| `log_format.py` | 结构化日志格式化（标签行格式 `[HH:MM:SS]-[phase]-[tag]`） |
| `claude_runner.py` | `run_claude()` / `run_claude_text()` 封装 Claude CLI |
| `review.py` | Post-task 代码自审：diff → Claude 自评 |
| `task.py` | `run_task()`：auto-commit → 分支 → runner 选择 → 状态更新 |
| `cmd_*.py` | CLI 子命令处理（run/edit/commit/log/review） |
| `runner/` | `Runner` ABC + `ClaudeRunner`/`CybervisorRunner` 实现 |

## Code Review 详细规则

- 三层上下文：diff + 临时合并分支 + 项目规则（`docs/blink/review-rules.md`）
- 报告中文输出（`REVIEW_PROMPT`），VERDICT 关键词保留英文供 `parse_verdict()` 正则匹配
- Anti-hallucination 设计：限定 diff 范围、要求证据引用（`**依据**`）、`[疑似]` 标签降级、排除风格/命名/注释
- 报告头使用中文标签（分支/基准/日期/结论）
- 保存路径：`<project>/docs/blink/code-review/<branch-slug>-<date>.md`
- `create_review_branch()` 返回 4 元组 `(review_name, original_branch, stashed, error)`
  - `error` 为 `None` 表示成功，`("conflict", msg)` 为真正冲突（生成 DENY 报告），`("error", msg)` 为其他失败（回退 diff-only）
- `detect_main_branch()` 依次检查 `main`、`master`
- Branch slug：`/` 替换为 `-`，连续 `-` 合并
