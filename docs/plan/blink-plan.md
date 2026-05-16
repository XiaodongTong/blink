# Blink - 项目仓库管理 TUI 工具方案

## Context

程序员设备上散落大量代码仓库，每次查找需要在目录中翻找。Blink 是一个轻量级 TUI 工具，将设备中所有代码仓库汇总为可搜索、可操作的菜单，通过 `blink` 命令启动。

目标平台：macOS only | 语言：Python | 核心要求：低内存、低 CPU

---

## 技术选型

### TUI 框架：prompt-toolkit

| 对比项 | prompt-toolkit | Textual | curses (stdlib) |
|--------|---------------|---------|-----------------|
| 依赖大小 | ~1MB, 1个依赖 | ~15MB+, rich等大量依赖 | 0 依赖 |
| 内存占用 | ~5-10MB | ~20-30MB | ~3-5MB |
| 搜索/过滤 | 内置, 开箱即用 | 需要自己写 | 需要自己写 |
| 开发效率 | 高 | 最高 | 最低 |
| 学习曲线 | 低 | 中 | 高 |

**选择 prompt-toolkit 的理由**：
- 内存/CPU 占用极小，符合核心要求
- 内置搜索、补全、快捷键支持，正好覆盖搜索过滤需求
- IPython 同款框架，成熟稳定
- 简单的列表菜单场景不需要 Textual 的 CSS 布局能力

### 数据存储：SQLite

存储路径 `~/.blink/blink.db`，理由：
- 单文件，零配置
- 全文搜索效率高
- Python 标准库自带 sqlite3 模块，零依赖
- 支持事务，数据一致性好

### 仓库扫描：os.scandir + subprocess

- 使用 `os.scandir` 递归遍历目录（比 `os.walk` 更高效）
- 检测 `.git` 目录判定为仓库
- 通过 `subprocess` 调用 `git remote -v` 获取远程地址
- 通过 `git config` 获取项目描述（`description` 文件）
- 跳过 `.Trash`、`node_modules`、`.cache`、`Library` 等无用目录
- 多线程扫描加快速度

### 编辑器打开：subprocess + which

- 使用 `which code` / `which cursor` 检测编辑器是否安装
- `subprocess.Popen` 异步打开，不阻塞 TUI
- Antigravity 支持：`open -a Antigravity <path>`

---

## 数据模型

```sql
-- 仓库表
CREATE TABLE repos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,           -- 目录名
    alias       TEXT,                    -- 用户自定义别名
    description TEXT,                    -- 项目描述
    path        TEXT UNIQUE NOT NULL,    -- 绝对路径
    last_synced TEXT NOT NULL,           -- 最后同步时间 ISO8601
    created_at  TEXT NOT NULL
);

-- 远程地址表（一个仓库可有多个 remote）
CREATE TABLE remotes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id   INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,             -- origin, upstream 等
    url       TEXT NOT NULL,
    UNIQUE(repo_id, name)
);

-- 标签表
CREATE TABLE tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

-- 仓库-标签关联表
CREATE TABLE repo_tags (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (repo_id, tag_id)
);

-- 工作区表
CREATE TABLE workspaces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);

-- 工作区-仓库关联表
CREATE TABLE workspace_repos (
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    repo_id      INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    PRIMARY KEY (workspace_id, repo_id)
);
```

---

## 项目结构

```
blink/
├── pyproject.toml          # 项目配置 & 构建入口
├── README.md
├── LICENSE
├── docs/
│   └── plan/
│       └── blink-plan.md
└── src/
    └── blink/
        ├── __init__.py
        ├── __main__.py     # python -m blink 入口
        ├── cli.py          # CLI 参数解析（click）
        ├── scanner.py      # 仓库扫描 & 同步
        ├── store.py        # SQLite 数据层
        ├── models.py       # 数据模型 dataclass
        ├── tui/
        │   ├── __init__.py
        │   ├── app.py      # TUI 主循环 & 布局
        │   ├── repo_list.py # 仓库列表控件
        │   ├── search.py   # 搜索过滤控件
        │   ├── detail.py   # 项目详情面板
        │   └── actions.py  # 编辑器打开/复制路径等操作
        └── config.py       # 配置管理 (~/.blink/config.json)
```

---

## 功能详细设计

### 1. 扫描与同步

**首次扫描流程**：
1. 读取 `~/.blink/config.json` 中的扫描路径配置（默认 `~`）
2. 递归遍历，遇到 `.git` 目录即判定为仓库
3. 跳过黑名单目录：`.Trash`, `.cache`, `Library`, `node_modules`, `.npm`, `.venv`, `__pycache__`, `.tox`
4. 对每个仓库并行获取 remote URL
5. 写入 SQLite，建立 path 唯一索引

**增量同步策略**：
- 每次启动，快速校验已缓存仓库的 path 是否仍存在（stat 调用，很快）
- 不存在的标记为已删除
- 用户可手动触发全量扫描（快捷键 `r`）
- 支持配置自动扫描间隔（默认关闭）

**同项目多地址合并**：
- 以 `path` 为唯一键，同一目录下的多个 remote 自动关联到一个仓库记录
- UI 展示时列出所有 remote 地址

### 2. 项目信息

**名称**：默认取目录名
**别名**：用户可自定义，搜索时别名也会匹配
**描述**：默认取 `.git/description` 内容，用户可编辑
**标签**：多标签支持，CRUD 操作通过 TUI 内快捷键完成

### 3. 交互设计

**主界面布局**：
```
┌─ Blink ──────────────────────────────────────┐
│ 🔍 [搜索框: 输入关键词过滤...]                 │
├───────────────────────────────────────────────┤
│  ● project-name        /Users/xx/path         │
│    github.com/org/project | Tags: python, api  │
│                                                │
│  ● another-project     /Users/xx/another       │
│    gitlab.com/team/proj  | Tags: go, cli       │
│                                                │
│  ● lib-foo             /Users/xx/lib-foo       │
│    (no remote)           | Tags: rust          │
├───────────────────────────────────────────────┤
│ ↑↓ 导航  Enter 详情  / 搜索  r 刷新  q 退出    │
│ 工作区: [1] All  [2] Frontend  [3] Backend     │
└───────────────────────────────────────────────┘
```

**快捷键**：
| 按键 | 功能 |
|------|------|
| `/` | 聚焦搜索框 |
| `↑` / `↓` / `j` / `k` | 上下移动 |
| `Enter` | 进入项目详情 |
| `o` | 用默认编辑器打开 |
| `v` | VSCode 打开 |
| `u` | Cursor 打开 |
| `a` | Antigravity 打开 |
| `y` | 复制项目路径到剪贴板 |
| `e` | 编辑项目信息（别名/描述/标签） |
| `t` | 管理标签 |
| `w` | 工作区管理 |
| `r` | 重新扫描 |
| `q` / `Esc` | 返回/退出 |

**搜索**：
- 实时过滤，支持模糊匹配
- 匹配范围：名称、别名、描述、标签、路径、remote URL
- 搜索无结果时显示提示

**项目详情面板**：
```
┌─ project-name ───────────────────────────────┐
│ 别名: my-project                              │
│ 路径: /Users/xx/workingspace/project          │
│ 描述: A web API service                       │
│ 远程:                                         │
│   origin  → github.com/org/project.git        │
│   mirror  → gitlab.com/org/project.git        │
│ 标签: python, api, web, backend               │
│ 工作区: Backend, Active                       │
│ 最后同步: 2026-05-16                          │
├───────────────────────────────────────────────┤
│ v=VSCode  u=Cursor  a=Antigravity  y=复制路径  │
│ e=编辑信息  t=标签  Backspace=返回列表         │
└───────────────────────────────────────────────┘
```

### 4. 工作区

- 工作区是一组仓库的集合（如 "前端项目"、"工作项目"）
- 主界面底部显示工作区 tab，可切换过滤
- 默认有 "All" 工作区显示全部
- 支持创建/删除/重命名工作区
- 在项目详情中可添加/移除工作区

---

## 配置文件

`~/.blink/config.json`:
```json
{
  "scan_paths": ["~"],
  "exclude_dirs": [".Trash", ".cache", "Library", "node_modules"],
  "editor": "code",
  "auto_sync_days": 7
}
```

---

## 发布方案

### PyPI（主要）
- 使用 `pyproject.toml` + `hatchling` 构建
- `pip install blink-repo` 安装
- 入口点：`blink = blink.cli:main`

### Homebrew Tap（辅助）
- 创建 `homebrew-blink` tap 仓库
- formula 调用 `pip install blink-repo`
- `brew install yourname/tap/blink`

### 构建配置核心（pyproject.toml）
```toml
[project]
name = "blink-repo"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "prompt-toolkit>=3.0",
    "click>=8.0",
]

[project.scripts]
blink = "blink.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 依赖清单（极简）

| 包 | 用途 | 大小 |
|----|------|------|
| prompt-toolkit | TUI 框架 | ~1MB |
| click | CLI 参数解析 | ~200KB |

其他全部使用标准库：`sqlite3`, `os`, `pathlib`, `subprocess`, `json`, `threading`, `shutil`

---

## 实施阶段

### P0 - MVP（核心可用）
1. 项目初始化：pyproject.toml, 目录结构
2. `store.py`：SQLite 数据层，建表、CRUD
3. `scanner.py`：递归扫描 `.git` 目录，获取 remote URL
4. `tui/app.py` + `tui/repo_list.py`：主列表 + 搜索过滤
5. `tui/actions.py`：打开编辑器、复制路径
6. `cli.py`：`blink` 命令入口

### P1 - 完善
7. 项目详情面板（别名、描述编辑）
8. 标签系统
9. 工作区功能
10. 增量同步 & 启动校验

### P2 - 发布
11. PyPI 发布流程
12. Homebrew Tap 配置
13. README & 文档

---

## 验证方式

1. **扫描测试**：`blink` 首次启动，检查是否正确发现设备上所有 git 仓库
2. **搜索测试**：输入关键词，验证过滤结果是否正确（名称/路径/标签匹配）
3. **编辑器打开**：选中项目后按 `v`/`u`/`a`，验证对应编辑器是否正确打开
4. **复制路径**：按 `y`，验证剪贴板内容是否正确
5. **同步测试**：新建一个 git 仓库后按 `r`，验证是否出现在列表中；删除仓库后验证是否同步移除
6. **资源占用**：`ps aux | grep blink` 确认内存在 15MB 以内
