# Blink

轻量级终端 TUI 工具，用于扫描、搜索和管理本地 git 仓库。

## 功能

- 自动发现配置目录下的所有 git 仓库
- 按名称、路径、描述或远程 URL 实时搜索
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

### TUI 快捷键

| 按键 | 功能 |
|------|------|
| `j` / `↓` | 向下移动 |
| `k` / `↑` | 向上移动 |
| `/` | 聚焦搜索栏 |
| `Enter` | 查看仓库详情（开发中） |
| `v` | 用 VSCode 打开 |
| `u` | 用 Cursor 打开 |
| `a` | 用 Antigravity 打开 |
| `o` | 用系统默认方式打开（Finder） |
| `y` | 复制仓库路径到剪贴板 |
| `r` | 重新扫描文件系统 |
| `Esc` | 清空搜索，或搜索为空时退出 |
| `q` | 退出 |

### 搜索

按 `/` 聚焦搜索栏，输入内容即可实时过滤仓库。搜索范围涵盖名称、别名、描述、路径和远程 URL，大小写不敏感。

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
