# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Constitutional Rules

**文档同步规范**：任何代码修改，都必须同步更新所有相关文档——包括 `CLAUDE.md`、`README.md`、以及这两个文件中引用到的本地 md 文件。涉及新增/删除/重命名模块、修改公开接口、变更快捷键或 UI 布局、更改配置项、调整架构或数据流等影响用户或开发者认知的变更，必须在提交前完成文档更新。纯格式调整、注释增删不影响行为的修改可豁免。

## Project Overview

Blink is a lightweight terminal TUI tool for scanning, searching, and managing local git repositories. Written in Python, it uses `prompt-toolkit` for the TUI and `click` for CLI. Data is stored in SQLite under `~/.blink/`.

## Commands

```bash
uv sync                    # Install dependencies
uv run blink               # Launch the TUI
uv run blink --rescan      # Force full rescan before TUI
uv run pytest              # Run all tests
uv run pytest tests/test_scanner.py  # Run a single test file
uv run pytest -k test_scan_paths_finds_git_repos  # Run a single test
uv build                   # Build distributable packages
```

Insert `breakpoint()` in source code and run `uv run blink` for pdb debugging.

## Architecture

**Entry point**: `src/blink/cli.py` — click command that wires together Config, Store, Scanner, and BlinkApp.

**Core modules** (all in `src/blink/`):

- `models.py` — `Repo` and `Remote` dataclasses
- `config.py` — JSON config loader (`~/.blink/config.json`), with defaults for scan paths, excludes, editor
- `scanner.py` — `Scanner` class that walks filesystem to find `.git` dirs, then fetches remotes/description via git subprocess. Uses `ThreadPoolExecutor` for parallel processing. Supports both blocking and background (threaded) scan modes.
- `store.py` — SQLite persistence layer (WAL mode). Tables: `repos`, `remotes`, `schema_version`. Upsert-based writes. Full-text search across name/alias/description/path/remote URL.

**TUI** (`src/blink/tui/`):

- `app.py` — Main `BlinkApp` class. Composes full-screen layout (search bar → repo list → status → footer). All key bindings, edit-mode input routing, layout switching (list ↔ detail), and background scan orchestration live here. Styles are defined in `_build_style()` using GitHub dark theme colors.
- `repo_list.py` — Custom `UIControl`/`Window` for the two-line repo list. Each repo renders as: line 1 = indicator + name/alias + tags, line 2 = path. Selected items pad lines to full width for consistent background fill.
- `search.py` — `SearchBar` wrapping a `prompt_toolkit.Buffer`
- `actions.py` — Editor detection and launch (VSCode, Cursor, Antigravity, system open), clipboard via `pbcopy`
- `detail.py` — `DetailPanel` class rendering full repo info (alias, name, path, description, remotes, tags, actions). Supports inline alias edit and tag management popovers.

**Data flow**: Scanner finds git dirs → creates `ScanResult(repo, remotes)` → Store upserts into SQLite → TUI loads from Store for display/search.

## UI Terminology

The TUI has two views: **列表视图**（list view）and **详情视图**（detail view）.

### 列表视图（List View）

```
┌─────────────────────────────────────────────────┐
│ /                                 ← 搜索前缀     │
│ [search input]                    ← 搜索输入框   │
│─────────────────────────────────────────────────│
│   ▸ alias (name) [tag]  ┐        ┐              │
│     /path/to/repo       ┘ 列表项 ┘ ← 项目列表   │
│─────────────────────────────────────────────────│
│ 42 repos                           ← 状态栏      │
│ j/k:nav  Enter:detail  /:search … ← 快捷键栏    │
└─────────────────────────────────────────────────┘
```

- **搜索栏**（search bar）— 包含搜索前缀 `/` 和搜索输入框，按 `/` 聚焦
- **项目列表**（repo list）— 两行式列表，`j/k` 或方向键导航
  - **列表项**（list item）— 每项占两行：
    - 第一行 = 指示符（`▸` 选中态 / 空格 普通态）+ 名称/别名 + 标签
    - 第二行 = 路径
  - 选中项以高亮背景区分（`#264f78`）
  - 无项目时显示空状态提示
- **状态栏**（status bar）— 显示项目计数或扫描状态；编辑模式下显示输入内容
- **快捷键栏**（footer）— 显示当前可用快捷键，随视图/编辑模式切换

### 详情视图（Detail View）

```
┌─────────────────────────────────────────────────┐
│   Alias     (none)                               │
│   Name      repo-name              ┐             │
│   Path      /path/to/repo          │             │
│   Desc      description            │ 详情面板    │
│                                  ┌─┘             │
│   Remotes                      ←─┘               │
│   Tags      [tag1] [tag2]                         │
│   Scanned   2025-01-01                           │
│   Actions: e:edit alias  t:manage tags …          │
│─────────────────────────────────────────────────│
│ 42 repos                           ← 状态栏      │
│ e:edit alias  t:manage tags …     ← 快捷键栏    │
└─────────────────────────────────────────────────┘
```

- **详情面板**（detail panel）— 展示项目完整信息：别名、名称、路径、描述、远程仓库、标签、扫描时间、可用操作
  - **标签管理浮层**（tag popover）— 按 `t` 弹出，列出已有标签（可按数字键删除）和添加输入框

### 编辑模式（Edit Modes）

列表视图和详情视图各有独立的编辑模式，进入后状态栏变为输入行，快捷键栏切换为编辑提示：

- **别名编辑模式**（alias edit）— 按 `e` 进入，Enter 保存，Esc 取消
- **标签管理模式**（tag edit）— 按 `t` 进入，1-9 删除标签，输入+Enter 添加，Esc 退出

## Key Patterns

- Store uses lazy SQLite connection (`_connect()` on first access) with `check_same_thread=False` for background scan support
- Scanner's `run_scan(blocking=True/False)` toggles between synchronous and threaded execution
- TUI uses `app.invalidate()` to trigger re-renders after state changes
- Config falls back to defaults if the file is missing or corrupted, and rewrites it
- Edit modes (alias/tag) are routed manually: key bindings check `_in_edit_mode()` and delegate printable/backspace to the active buffer via `_route_printable`/`_route_backspace`
- Layout switching replaces `app.layout` entirely (list layout vs detail layout), stored in `_list_layout` for reuse
- Style class names avoid prompt_toolkit built-in names (e.g. `repo-selected` instead of `selected`) to prevent style conflicts
- Tests create real git repos via subprocess in `tmp_path` fixtures
