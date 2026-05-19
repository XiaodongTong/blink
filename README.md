# Blink

轻量级终端 TUI 工具，用于扫描、搜索和管理本地 git 仓库。

## 功能

- 自动发现配置目录下的所有 git 仓库
- 两行式列表展示：项目名 + 标签，路径（灰色）
- 置顶常用项目（★ 标记），置顶项目始终排在前面
- 按查看次数自动排序，常用项目靠前
- 按名称、别名、路径、描述、远程 URL 或标签实时搜索
- 别名编辑、标签管理（添加 / 按序号移除）
- 详情面板查看仓库完整信息并执行操作
- 一键用 VSCode / Cursor / Antigravity / 系统默认方式打开仓库
- 复制仓库路径到剪贴板
- 后台重新扫描，无需退出 TUI

## 安装

```bash
pip install blink-repo
```

## 使用

```bash
blink          # 启动 TUI
blink --rescan # 强制重新扫描后启动
```

### 首次运行

首次启动时，Blink 会扫描主目录下的 git 仓库并在终端显示进度。扫描完成后自动打开 TUI，展示所有已发现的仓库。

后续启动会直接使用缓存数据打开 TUI，同时自动清理磁盘上已不存在的失效条目。

### 列表视图快捷键

列表视图下，裸按键不触发任何操作，所有破坏性操作需要 `Shift` 前缀。`j`/`k` 已移除，不再作为导航键。

| 按键 | 功能 | 需要Shift |
|------|------|:----------:|
| `↑` / `↓` | 向上/向下移动 | ✗ |
| `Enter` | 查看仓库详情 | ✗ |
| `/` | 进入搜索 | ✗ |
| `Shift+V` | 用 VSCode 打开 | ✓ |
| `Shift+U` | 用 Cursor 打开 | ✓ |
| `Shift+A` | 用 Antigravity 打开 | ✓ |
| `Shift+O` | 用系统默认方式打开（Finder） | ✓ |
| `Shift+P` | 复制仓库路径到剪贴板 | ✓ |
| `Shift+R` | 重新扫描文件系统 | ✓ |
| `Ctrl+C` ×2 | 退出程序（2 秒内按两次，超时需重新双击） | ✗ |

### 详情面板

按 `Enter` 进入详情面板，显示名称、别名、路径、描述、Git 地址、标签、置顶状态等 12 行。`↑`/`↓` 切换选中行（高亮背景 `#264f78`），按 Enter 执行当前行操作：Name/Path 行复制内容并在状态栏提示，Git 行将 SSH 协议地址转换为 HTTPS 地址并在浏览器打开，Alias/Description/Tags 行进入编辑态，Pinned 行切换置顶状态（状态栏提示"已置顶"/"已取消置顶"），Open with Antigravity/Cursor/VSCode/Finder 行执行打开，Loop Task 行执行 `tloop edit`（未安装时状态栏提示"未安装 tloop"）。编辑态下 `↑`/`↓` 被屏蔽，Enter 保存，Esc/Ctrl+C 取消，支持中文等非 ASCII 输入，编辑时面板底部渲染编辑输入行并显示光标。详情面板无 footer 快捷键栏。按 `Ctrl+C` 或 `Esc` 返回列表。进入详情视图时自动累计查看次数，影响列表排序。

### 搜索

默认状态下搜索区域完全隐藏。按 `/` 展开带亮色边框的搜索输入框，输入内容即可实时过滤仓库。搜索范围涵盖名称、别名、描述、路径、远程 URL 和标签，大小写不敏感。

- 按 `Enter` 或 `↓` 隐藏输入框，保留过滤结果（顶部显示当前关键词）
- 按 `Esc` 或 `Ctrl+C` 清空搜索，恢复全部仓库
- 过滤状态下再按 `/` 恢复输入框，可继续编辑搜索词
- 搜索输入态下，所有其他快捷键被屏蔽

### 退出程序

- 按 `q` 无任何效果
- `Esc` 仅用于取消操作（退出搜索、返回列表），不会退出程序
- 连续按两次 `Ctrl+C`（2 秒窗口）退出程序。第一次会在状态栏显示提示，提示显示后 2 秒内再按一次才能退出，超时则需重新双击

## 配置

首次运行时，Blink 会在 `~/.blink/config.json` 创建默认配置：

```json
{
  "scan_paths": ["~"],
  "exclude_dirs": [".Trash", ".cache", ".npm", ".docker", ".vscode", "Library", "Applications", "node_modules", "__pycache__"],
  "editor": "code",
  "auto_sync_days": 0
}
```

| 字段 | 说明 |
|------|------|
| `scan_paths` | 扫描 git 仓库的根目录列表 |
| `exclude_dirs` | 扫描时跳过的目录名 |
| `editor` | 默认编辑器命令 |
| `auto_sync_days` | 自动重新扫描间隔天数（`0` 为禁用） |

所有数据存储在 `~/.blink/` 目录下：

- `config.json` — 用户配置
- `blink.db` — SQLite 数据库，存储仓库和远程信息

## 开发

### 环境要求

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)
- [git](https://git-scm.com/)

### 初始化

```bash
git clone <repo-url> blink && cd blink
uv sync
```

### 运行

```bash
uv run blink          # 启动 TUI
uv run blink --rescan # 强制重新扫描
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
