# Blink

轻量级终端 TUI 工具，用于扫描、搜索和管理本地 git 仓库。

## 功能

- 自动发现配置目录下的所有 git 仓库
- 双栏联动布局：左侧列表（~40%）+ 右侧详情面板（~60%）
- 两行式列表展示：项目名 + 标签，路径（左）+ Git 状态徽标（右）
- Git 状态徽标显示分支、变更、领先/落后：`main ●`（干净）、`feature ○ +3`（有变更）、`fix ● ↓2`（落后远程）；加载中显示 `···`，获取失败显示 `⚠`
- 置顶常用项目（★ 标记），置顶项目始终排在前面
- 按查看次数自动排序，常用项目靠前
- 按名称、别名、路径、描述、远程 URL 或标签实时搜索
- 别名编辑、标签管理（添加 / 按序号移除）、描述编辑
- 一键用首选 IDE / 系统默认方式打开仓库
- 复制仓库路径到剪贴板
- 后台重新扫描，无需退出 TUI
- Nerd Font 图标支持（通过配置开关启用）
- 窄终端（< 80 列）自动降级为单栏列表模式

## 安装

```bash
pip install blink-repo
```

## 使用

```bash
blink              # 启动 TUI
blink -R           # 强制重新扫描后启动（--rescan 的简写）
blink -v           # 显示版本号（--version 的简写）
blink run          # 执行 tasks.yaml 中定义的任务
blink run -s       # 查看任务状态（--status 的简写）
blink edit [path]  # 编辑任务文件，可选添加指定目录的任务
blink config-task -a [path]  # 添加任务配置到 tasks.yaml（--add 的简写）
blink commit -p .  # 自动提交当前目录的变更
blink log [N]      # 查看任务日志
blink review <branch>          # AI code review（自动检测 main/master 作为 base 分支）
blink review <branch> -d       # 仅 diff 模式（不创建临时分支）
blink review -l                # 列出现有 review 报告
blink review <branch> -a develop  # 指定目标分支
blink review <branch> -m opus  # 指定 Claude 模型（haiku/sonnet/opus，默认 sonnet）
blink review <branch> -p ~/proj  # 指定项目目录（默认当前目录）
blink review -i                # 创建 review-rules.md 模板
```

> Review 报告保存至 `<project>/docs/blink/code-review/<branch>-<date>.md`，结论为 APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES。可通过 `-i` 创建 `docs/blink/review-rules.md` 定义项目特定的 review 规则。

> 自动提交功能（`blink commit` 和 TUI Shift+C）以及 Code Review 功能（`blink review` 和 TUI Shift+V）需要已安装 [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)（`claude` 命令）。

### 首次运行

首次启动时，Blink 会扫描主目录下的 git 仓库并在终端显示进度。扫描完成后自动打开 TUI，展示所有已发现的仓库。

后续启动会直接使用缓存数据打开 TUI，同时自动清理磁盘上已不存在的失效条目。

### 布局

Blink 采用双栏联动布局：左侧为仓库列表，右侧为详情面板。左侧光标移动时右侧实时更新。

右侧详情面板分三个区域：
- **基础信息**（只读）：Name、Path、Git、Status
- **操作区**（可选中，Enter 执行）：IDE、Git（在浏览器中打开）、Commit、Task（添加 Todo 任务）、Finder、Review（AI Code Review）、Path。聚焦时选中行显示 `[Enter]`，未聚焦时显示对应快捷键徽标
- **本地标记**（可编辑）：Pinned、Alias、Tags、Description。仅在聚焦时显示选中效果

当终端宽度不足 80 列时，自动降级为仅显示左侧列表。

### 快捷键

| 按键 | 功能 |
|------|------|
| `↑` / `↓` | 导航（列表或详情面板） |
| `Enter` | 打开 IDE（列表焦点）/ 执行操作（详情焦点） |
| `/` | 搜索（任何焦点下可用） |
| `Tab` / `→` | 焦点移至右侧详情面板 |
| `Esc` / `←` | 焦点移回左侧列表 |
| `Shift+I` | 用 IDE 打开 |
| `Shift+O` | 用系统默认方式打开（Finder） |
| `Shift+P` | 复制仓库路径到剪贴板 |
| `Shift+R` | 重新扫描文件系统 |
| `Shift+C` | 自动提交代码（AI 生成 commit message） |
| `Shift+G` | 在浏览器中打开远程仓库 |
| `Shift+T` | 添加 Todo 任务（追加到 `~/.blink/loop/tasks.yaml`，完成后自动打开 IDE 编辑） |
| `Shift+V` | AI Code Review（输入同事分支名，自动生成 review 报告） |
| `Shift+L` | 打开最近的 review 报告 |
| `Shift+U` | 拉取最新代码（`git pull`） |
| `Ctrl+C` ×2 | 退出程序（2 秒内按两次） |

### 详情面板操作

使用 `Tab` 或 `→` 将焦点移至右侧面板，`↑`/`↓` 选择行，`Enter` 执行操作：

- **IDE** — 用 IDE 打开仓库
- **Git** — 在浏览器中打开远程仓库
- **Commit** — 自动提交代码（AI 生成 commit message）
- **Task** — 添加 Todo 任务（追加到 `~/.blink/loop/tasks.yaml`，完成后自动打开 IDE 编辑）
- **Finder** — 在 Finder 中打开
- **Review** — AI Code Review（输入同事分支名，自动生成结构化 review 报告）
- **Path** — 复制仓库路径到剪贴板
- **Pinned** — 切换置顶状态
- **Alias** — 编辑别名（Enter 保存，Esc 取消）
- **Tags** — 管理标签（输入+Enter 添加，数字键按序号删除）
- **Description** — 编辑描述（Enter 保存，Esc 取消）

所有操作反馈（如提交完成、路径已复制、任务已添加等）均在状态栏显示，5 秒后自动消失。

### 搜索

按 `/` 展开搜索输入框（任何焦点下可用），输入内容即可实时过滤仓库。搜索范围涵盖名称、别名、描述、路径、远程 URL 和标签。

- 按 `Enter` 或 `↓` 隐藏输入框，保留过滤结果
- 按 `Esc` 或 `Ctrl+C` 清空搜索，恢复全部仓库
- 过滤状态下再按 `/` 清空搜索内容并恢复输入框

### 退出程序

- 按 `q` 无任何效果
- `Esc` 仅用于取消操作（退出编辑、退出搜索、焦点切回列表），不会退出程序
- 连续按两次 `Ctrl+C`（2 秒窗口）退出程序

## 配置

首次运行时，Blink 会在 `~/.blink/config.json` 创建默认配置：

```json
{
  "scan_paths": ["~"],
  "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", ".vscode", "Library", "Applications", "node_modules", "__pycache__"],
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
| `editor` | 默认编辑器命令 |
| `preferred_ide` | 首选 IDE（`"v"` VSCode / `"u"` Cursor / `"a"` Antigravity），首次使用 Shift+I 或 `blink edit` 时自动设置 |
| `auto_sync_days` | 自动重新扫描间隔天数（`0` 为禁用） |
| `nerd_fonts` | 启用 Nerd Font 图标（`true` 启用，`false` 使用 ASCII） |

所有数据存储在 `~/.blink/` 目录下：

- `config.json` — 用户配置
- `blink.db` — SQLite 数据库，存储仓库和远程信息
- `loop/` — 任务运行相关数据（`tasks.yaml`、`state.json`、`logs/`、`archive/`）

## 开发

### 环境要求

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- [git](https://git-scm.com/)
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)（可选，用于自动提交、任务执行和 Code Review）

### 初始化

```bash
git clone <repo-url> blink && cd blink
uv sync
```

### 运行

```bash
uv run blink              # 启动 TUI
uv run blink -R           # 强制重新扫描（--rescan 的简写）
uv run blink -v           # 显示版本号（--version 的简写）
uv run blink run -s       # 查看任务状态（--status 的简写）
uv run blink commit -p .  # 自动提交变更
```

### 测试

```bash
uv run pytest
```

### 调试

在源码任意位置插入 `breakpoint()`，然后执行 `uv run blink`，程序会在断点处暂停并进入 pdb 交互调试。

## 发布

```bash
uv build    # 构建分发包
uv publish  # 发布到 PyPI
```

## 许可证

MIT
