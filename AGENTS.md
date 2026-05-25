# AGENTS.md

AI 协作入口文档。详细内容按渐进式披露原则拆分至 `docs/agents/`。

## 宪法规则

- **文档同步**：代码修改必须同步更新 AGENTS.md、README.md 及引用的本地 md 文件。涉及模块增删/重命名、公开接口变更、快捷键/UI 布局变更、配置项变更、架构调整，必须在提交前完成文档更新
- **CLI 参数简写**：所有 CLI 参数必须同时提供长参数（`--`）和短参数（`-`）形式
- **本文件不超过 200 行**：超出时必须将内容拆分至 `docs/agents/`

## 项目概述

Blink 是轻量级终端 TUI 工具，用于扫描、搜索和管理本地 git 仓库。Python 编写，使用 `prompt-toolkit`（TUI）和 `click`（CLI），数据存储在 SQLite（`~/.blink/`）。

## CLI 命令速查

```bash
uv sync                    # 安装依赖
uv run blink               # 启动 TUI
uv run blink -R            # 强制重新扫描后启动（--rescan 简写）
uv run blink run -s        # 查看任务状态（--status 简写）
uv run blink edit            # 编辑 tasks.yaml
uv run blink edit --add [path]  # 添加任务并打开编辑器
uv run blink commit -p .   # 自动提交变更
uv run blink log [N]       # 查看任务日志
uv run blink review <branch>          # AI code review
uv run blink review <branch> -d       # 仅 diff 模式（不创建临时分支）
uv run blink review -l                # 列出 review 报告
uv run blink review <branch> -a develop  # 指定 base 分支
uv run blink review -i                # 创建 review-rules.md 模板
uv run pytest              # 运行测试
uv build                   # 构建分发包
```

调试：在源码插入 `breakpoint()`，运行 `uv run blink` 进入 pdb。

## 模块索引

### 核心模块（`src/blink/`）

| 模块 | 职责 |
|------|------|
| `cli.py` | 入口，click group，无子命令时启动 TUI |
| `models.py` | `Repo`/`Remote`/`RepoStatus` 数据类 + `display_width()` |
| `logger.py` | 按天轮转日志，线程安全 |
| `config.py` | JSON 配置加载，缺失时回退默认值 |
| `scanner.py` | `Scanner` 仓库扫描 + `StatusFetcher` git 状态并行获取 |
| `store.py` | SQLite 持久化（WAL），全文搜索，schema 迁移 |

### 循环任务（`src/blink/loop/`）

| 模块 | 职责 |
|------|------|
| `config.py` | 常量、目录初始化、`load_config()` |
| `state.py` | JSON 状态管理，任务追踪与归档 |
| `git_ops.py` | Git 安全检查、auto-commit、分支创建 |
| `log_format.py` | 结构化日志格式化 |
| `claude_runner.py` | 封装 Claude CLI 调用 |
| `review.py` | AI code review（diff + 合并分支 + 项目规则） |
| `task.py` | 单任务执行编排 |
| `cmd_*.py` | CLI 子命令处理（run/edit/commit/log） |
| `runner/` | `Runner` ABC + ClaudeRunner/CybervisorRunner |

### TUI（`src/blink/tui/`）

| 模块 | 职责 |
|------|------|
| `app.py` | 主应用，双栏布局，焦点管理，按键绑定，后台操作 |
| `repo_list.py` | 两行式列表控件，状态徽标 |
| `detail.py` | 详情面板（Metadata/Actions/Local Markers 三区） |
| `search.py` | 搜索栏控件 |
| `actions.py` | IDE 检测/启动、剪贴板（TUI 和 CLI 共用） |
| `icons.py` | Nerd Font 图标常量 + ASCII 回退 |

## 详细文档

| 文档 | 内容 |
|------|------|
| [架构与数据流](docs/agents/architecture.md) | 入口点、模块详细职责、完整数据流、code review 规则 |
| [TUI 详细说明](docs/agents/tui.md) | 各 TUI 模块详细职责、焦点管理、编辑模式、退出机制 |
| [UI 术语与快捷键](docs/agents/ui-spec.md) | 布局图、各区域规范、快捷键表、窄终端降级 |
| [关键开发模式](docs/agents/key-patterns.md) | Store 懒连接、扫描模式、IDE 选择、提交/拉取、测试 |

## 数据目录

```
~/.blink/
  config.json     — 用户配置
  blink.db        — SQLite 数据库
  loop/           — 任务系统（tasks.yaml, state.json, logs/, archive/）
  logs/           — 应用日志（blink-YYYY-MM-DD.log）
```
