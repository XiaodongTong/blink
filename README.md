# Blink

**你的终端里，住着一个仓库管家。**

Blink 是一个轻量级的终端工具集，帮助开发者高效管理本地 Git 仓库和编排 AI 自动化任务。双栏交互界面，打开即用，无需离开终端。

---

## 它能做什么？

### 仓库管理器 (TUI)

在一个漂亮的终端界面中，浏览、搜索和管理你所有的 Git 仓库：

- **自动发现** — 扫描指定目录，自动识别所有 Git 仓库，结果持久化到本地数据库
- **实时状态** — 并行获取分支名、脏文件数、ahead/behind 等信息，一目了然
- **全文搜索** — 按名称、路径、远程 URL、标签、描述实时过滤
- **一键操作** — 打开 IDE、在终端中打开、在 Finder 中显示、浏览器跳转远程仓库
- **快捷推送/拉取** — 无需手动输入 git 命令，一键推送或拉取代码
- **个性化标记** — 为仓库设置置顶、别名、标签和描述，快速识别

```
┌───────────────────────┬──────────────────────────────────────────┐
│ ── Repos ──────────   │ ── Detail ────────────────────────────── │
│   ▸ ★ name [tag]     │     Name      repo-name                  │
│     /path/to/repo    │     Path      /path/to/repo              │
│                      │     Repo      https://github.com/...      │
│                      │     Status    main ●                     │
│                      │ ───────────────────────────────────────── │
│                      │   ▸ Terminal  Open in Terminal   [Shift+1]│
│                      │     IDE       Open with IDE      [Shift+2]│
│                      │     Finder    Open in Finder      [Shift+3]│
│                      │ ───────────────────────────────────────── │
│                      │     Git       Open in Browser     [Shift+4]│
│                      │     Push      Push Changes         [Shift+5]│
│                      │     Pull      Pull Changes         [Shift+6]│
│                      │ ───────────────────────────────────────── │
│                      │     Task      Add todo task        [Shift+7]│
│                      │     Review    AI Code Review       [Shift+8]│
└───────────────────────┴──────────────────────────────────────────┘
```

### AI 任务引擎 (Loop)

通过 YAML 配置文件编排 AI 驱动的自动化任务：

- **自动提交** — AI 分析代码变更，生成语义化的 commit message，自动提交
- **任务编排** — 在 `tasks.yaml` 中定义任务，按顺序自动执行代码编写、测试、提交
- **AI Code Review** — 对同事的分支进行结构化审查，输出 APPROVE / DENY 报告
- **Git 安全** — 任务前自动提交脏工作树、自动创建 feature 分支
- **多 Runner** — 支持 Claude CLI 和 Cybervisor 两种 AI 执行后端

---

## 为什么用 Blink？

|  |  |
|---|---|
| **零配置启动** | `pip install` 后直接运行，首次自动扫描，无需任何设置 |
| **不离开终端** | 全部操作在终端内完成，无需切换窗口 |
| **键盘优先** | 所有操作都有快捷键，`Shift+数字` 一键触发 |
| **持久化缓存** | 仓库信息存储在本地 SQLite，二次启动瞬间加载 |
| **AI 原生** | 自动提交、任务编排、代码审查，全部由 AI 驱动 |
| **轻量依赖** | 核心仅依赖 prompt-toolkit、click、pyyaml |

---

## 快速开始

### 安装

```bash
pip install blink-repo
```

### 启动

```bash
blink              # 启动仓库管理器
```

首次启动会扫描主目录下的 Git 仓库，完成后自动打开 TUI 界面。后续启动直接使用缓存，同时自动清理失效条目。

### 常用命令

```bash
blink                          # 启动 TUI
blink -R                       # 强制重新扫描
blink commit -p .              # AI 自动提交当前目录变更
blink review <branch>          # AI Code Review 指定分支
blink review <branch> -d       # 仅 diff 模式（不创建临时分支）
blink review -l                # 列出历史 review 报告
blink run -s                   # 查看任务状态
blink edit                     # 编辑任务文件
blink log                      # 查看任务日志
```

> 自动提交和 Code Review 功能需要安装 [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)。

---

## 快捷键

所有快捷键在列表和详情面板中均可使用：

| 按键 | 功能 |
|------|------|
| `↑` / `↓` | 导航 |
| `Enter` | 打开 IDE（列表）/ 执行操作（详情） |
| `/` | 搜索（任何焦点下） |
| `Tab` / `→` | 切换到详情面板 |
| `Esc` / `←` | 切换回列表 |
| `Shift+1` | 打开终端 |
| `Shift+2` | 用 IDE 打开 |
| `Shift+3` | 在 Finder 中打开 |
| `Shift+4` | 浏览器打开远程仓库 |
| `Shift+5` | 推送变更 |
| `Shift+6` | 拉取最新代码 |
| `Shift+7` | 添加 Todo 任务 |
| `Shift+8` | AI Code Review |
| `Shift+R` | 重新扫描 |
| `Ctrl+C` ×2 | 退出 |

### 搜索

按 `/` 展开搜索框，实时过滤仓库。搜索范围：名称、别名、描述、路径、远程 URL、标签。Enter 隐藏搜索框保留结果，Esc 清空恢复全部。

---

## 配置

首次运行在 `~/.blink/config.json` 创建默认配置：

```json
{
  "scan_paths": ["~"],
  "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", "Library", "node_modules"],
  "editor": "code",
  "preferred_ide": null,
  "auto_sync_days": 0,
  "nerd_fonts": false
}
```

| 字段 | 说明 |
|------|------|
| `scan_paths` | 扫描 Git 仓库的根目录列表 |
| `exclude_dirs` | 扫描时跳过的目录名 |
| `editor` | 默认编辑器 |
| `preferred_ide` | 首选 IDE（`v` VSCode / `u` Cursor / `a` Antigravity） |
| `auto_sync_days` | 自动重新扫描间隔天数（0 禁用） |
| `nerd_fonts` | 启用 Nerd Font 图标 |

所有数据存储在 `~/.blink/` 目录下。

---

## 开发

Blink 使用 Python 3.9+ 和 [uv](https://docs.astral.sh/uv/) 构建。开发环境搭建、测试、调试等详细信息请参阅 [开发指南](docs/development.md)。

快速上手：

```bash
git clone <repo-url> blink && cd blink
uv sync                    # 安装依赖
uv run blink               # 启动 TUI
uv run pytest              # 运行测试
```

---

## 许可证

MIT
