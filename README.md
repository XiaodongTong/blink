# Blink

轻量级终端 TUI 工具，用于扫描、搜索和管理本地 git 仓库。

## 使用

### 安装

```bash
pip install blink-repo
```

### 首次运行

首次启动时，Blink 会扫描主目录下的 git 仓库并在终端显示进度。扫描完成后自动打开 TUI。后续启动直接使用缓存数据，同时自动清理失效条目。

### CLI 命令

```bash
blink              # 启动 TUI
blink -R           # 强制重新扫描后启动
blink -v           # 显示版本号
blink run          # 执行 tasks.yaml 中的任务
blink run -s       # 查看任务状态
blink edit          # 编辑任务文件
blink edit --add [path]  # 添加任务并打开编辑器
blink commit -p .  # 自动提交变更
blink log [N]      # 查看任务日志
blink review <branch>          # AI code review
blink review <branch> -d       # 仅 diff 模式
blink review -l                # 列出 review 报告
blink review <branch> -a develop  # 指定 base 分支
blink review -i                # 创建 review-rules.md 模板
```

> 自动提交和 Code Review 功能需要已安装 [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)。

### 布局

Blink 采用双栏联动布局：左侧仓库列表，右侧详情面板。光标移动时右侧实时更新。

```
┌───────────────────────┬──────────────────────────────────────────┐
│ ── Repos ──────────   │ ── Detail ────────────────────────────── │
│   ▸ ★ name [tag]     │     Name      repo-name                  │
│     /path/to/repo    │     Path      /path/to/repo              │
│                      │     Status    main ●                     │
│                      │ ───────────────────────────────────────── │
│                      │   ▸ IDE       Open with IDE     [Shift+I]│
│                      │     Commit    Auto Commit       [Shift+C]│
│                      │     Review    AI Code Review    [Shift+V]│
│                      │ ───────────────────────────────────────── │
│                      │   ▸ Pinned    No                         │
│                      │     Tags      [python] [api]             │
└───────────────────────┴──────────────────────────────────────────┘
```

### 快捷键

| 按键 | 功能 |
|------|------|
| `↑` / `↓` | 导航 |
| `Enter` | 打开 IDE（列表）/ 执行操作（详情） |
| `/` | 搜索（任何焦点下） |
| `Tab` / `→` | 焦点移至详情面板 |
| `Esc` / `←` | 焦点移回列表 |
| `Shift+I` | 用 IDE 打开 |
| `Shift+O` | 系统默认打开（Finder） |
| `Shift+P` | 复制仓库路径 |
| `Shift+R` | 重新扫描 |
| `Shift+C` | 自动提交（AI 生成 commit message） |
| `Shift+G` | 浏览器打开远程仓库 |
| `Shift+T` | 添加 Todo 任务 |
| `Shift+V` | AI Code Review |
| `Shift+L` | 打开最近 review 报告 |
| `Shift+U` | 拉取最新代码 |
| `Ctrl+C` ×2 | 退出（2秒内按两次） |

### 搜索

按 `/` 展开搜索框，实时过滤仓库（搜索范围：名称、别名、描述、路径、远程 URL、标签）。Enter 隐藏搜索框保留结果，Esc 清空恢复全部。

### 详情面板操作

`Tab` 移至右侧，`↑`/`↓` 选择行，`Enter` 执行：

- **Actions 区**：IDE / Git（浏览器）/ Commit / Task / Finder / Review / Path
- **Local Markers 区**：Pinned（切换置顶）/ Alias（编辑别名）/ Tags（管理标签）/ Description（编辑描述）

### 配置

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
| `scan_paths` | 扫描 git 仓库的根目录列表 |
| `exclude_dirs` | 扫描时跳过的目录名 |
| `editor` | 默认编辑器 |
| `preferred_ide` | 首选 IDE（`v` VSCode / `u` Cursor / `a` Antigravity） |
| `auto_sync_days` | 自动重新扫描间隔（0 禁用） |
| `nerd_fonts` | 启用 Nerd Font 图标 |

数据存储在 `~/.blink/`：`config.json`、`blink.db`（SQLite）、`loop/`（任务数据）、`logs/`（应用日志）。

## 开发调试

### 环境要求

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- [git](https://git-scm.com/)
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)（可选，用于自动提交和 Code Review）

### 初始化

```bash
git clone <repo-url> blink && cd blink
uv sync
```

### 运行

```bash
uv run blink              # 启动 TUI
uv run blink -R           # 强制重新扫描
```

### 测试

```bash
uv run pytest                              # 全部测试
uv run pytest tests/test_scanner.py        # 单文件
uv run pytest -k test_scan_paths_finds_git_repos  # 单测试
```

### 调试

在源码任意位置插入 `breakpoint()`，运行 `uv run blink`，程序会在断点处进入 pdb。

### 构建

```bash
uv build    # 构建分发包
```

## 许可证

MIT
