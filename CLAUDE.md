# CLAUDE.md

AI 协作入口文档。详细内容按渐进式披露原则拆分至 `docs/agents/`。

## 宪法规则

- **文档同步**：代码修改必须同步更新 CLAUDE.md、README.md 及引用的本地 md 文件。涉及模块增删/重命名、公开接口变更、快捷键/UI 布局变更、配置项变更、架构调整，必须在提交前完成文档更新
- **CLI 参数简写**：所有 CLI 参数必须同时提供长参数（`--`）和短参数（`-`）形式
- **测试驱动**：写代码前必须先设计好对应的单元测试用例，写完代码后必须执行 `uv run pytest` 确保全部测试通过后才算完成。测试文件位于 `tests/` 目录，命名规则 `test_*.py`
- **本文件不超过 200 行**：超出时必须将内容拆分至 `docs/agents/`
- **文件行数限制**：单个文件不超过 500 行，超出时必须拆分为多个模块

## 产品定位

Blink 是面向开发者的终端工具集，提供两大核心能力：

### TUI — 仓库管理器

交互式终端界面（`prompt-toolkit`），帮助开发者快速定位和管理本地 git 仓库。

- **仓库发现**：扫描文件系统，自动发现 git 仓库并持久化到 SQLite
- **实时状态**：并行获取分支、dirty 文件数、ahead/behind 等状态
- **快捷工具**：IDE 打开、浏览器跳转远程仓库、路径复制、自动提交、AI Code Review
- **全文搜索**：按名称/路径/远程 URL/标签/描述过滤仓库

### Loop — AI 任务引擎

CLI 任务编排系统，按 `tasks.yaml` 顺序执行 AI 驱动的自动化任务。

- **多 Runner 支持**：CybervisorRunner（默认）和 ClaudeRunner（多轮循环模式）
- **Git 安全**：任务前自动提交脏工作树、自动创建 feature 分支、支持 post-task 自审
- **状态管理**：JSON 状态追踪、已完成任务自动归档
- **AI Code Review**：对同事分支进行自动化 review，支持临时分支合并、项目规则、结构化报告
- **工具命令**：`run`（执行任务）、`edit`（编辑任务）、`commit`（AI 自动提交）、`log`（查看日志）、`review`（AI review）

> 技术细节见 [Loop 模块文档](docs/agents/loop.md)。

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
uv run blink review <branch> --no-verify  # 跳过验证 pass
uv run blink review <branch> --strict     # 严格模式
uv run pytest              # 运行测试
uv build                   # 构建分发包
```

调试：在源码插入 `breakpoint()`，运行 `uv run blink` 进入 pdb。

## 模块索引

### 核心模块（`src/`）

| 模块 | 职责 |
|------|------|
| `cli.py` | 入口，click group，无子命令时启动 TUI |
| `models.py` | `Repo`/`Remote`/`RepoStatus` 数据类 + `display_width()` |
| `logger.py` | 按天轮转日志，线程安全 |
| `config.py` | JSON 配置加载，缺失时回退默认值 |
| `scanner.py` | `Scanner` 仓库扫描 + `StatusFetcher` git 状态并行获取 |
| `store.py` | SQLite 持久化（WAL），全文搜索，schema 迁移 |

### TUI（`src/tui/`）

| 模块 | 职责 |
|------|------|
| `app.py` | 主应用类，初始化协调，焦点管理，后台操作 |
| `styles.py` | 样式定义（GitHub dark 主题色） |
| `layout.py` | 双栏布局构建，`EditStatusControl` |
| `key_bindings.py` | 所有按键绑定注册 |
| `status_bar.py` | 状态栏和页脚文本渲染 |
| `app_review.py` | TUI Review 编排（分支选择 + AI 执行） |
| `app_config.py` | 配置面板 `ConfigPanel(UIControl)` + `ConfigSelectMode` 枚举 |
| `actions.py` | IDE 检测/启动、剪贴板（TUI 和 CLI 共用） |
| `icons.py` | Nerd Font 图标常量 + ASCII 回退 |
| `widgets/` | UI 控件子目录 |
| `widgets/detail.py` | 详情面板（Metadata/Actions/Local Markers 三区） |
| `widgets/detail_edit.py` | 详情面板编辑模式 mixin |
| `widgets/repo_list.py` | 两行式列表控件，状态徽标 |
| `widgets/search.py` | 搜索栏控件 |

### Loop（`src/loop/`）

> 完整文档见 [Loop 模块文档](docs/agents/loop.md)。

## 详细文档

| 文档 | 内容 |
|------|------|
| [Loop 模块文档](docs/agents/loop.md) | Loop 产品定位、架构、任务配置、Runner、状态管理、Code Review |
| [架构与数据流](docs/agents/architecture.md) | 入口点、模块详细职责、完整数据流 |
| [TUI 详细说明](docs/agents/tui.md) | 各 TUI 模块详细职责、焦点管理、编辑模式、退出机制 |
| [UI 术语与快捷键](docs/agents/ui-spec.md) | 布局图、各区域规范、快捷键表、窄终端降级 |
| [关键开发模式](docs/agents/key-patterns.md) | Store 懒连接、扫描模式、IDE 选择、提交/拉取、测试 |
| [Review 流程图](docs/agents/review-flow.md) | AI Code Review 完整流程（CLI/TUI 入口、核心步骤、TaskReview） |

## 数据目录

```
~/.blink/
  config.json     — 用户配置
  blink.db        — SQLite 数据库
  loop/           — 任务系统（tasks.yaml, tasks-next.yaml, state.json, logs/, archive/）
  logs/           — 应用日志（blink-YYYY-MM-DD.log）
```
