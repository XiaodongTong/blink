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

- `app.py` — Main `BlinkApp` class. Composes full-screen layout (search prefix → repo list → status → footer). All key bindings, search state machine, exit mechanism, edit-mode input routing, layout switching (list ↔ detail), and background scan orchestration live here. Styles are defined in `_build_style()` using GitHub dark theme colors.
- `repo_list.py` — Custom `UIControl`/`Window` for the two-line repo list. Each repo renders as: line 1 = indicator + name/alias + tags, line 2 = path. Selected items pad lines to full width for consistent background fill.
- `search.py` — `SearchBar` wrapping a `prompt_toolkit.Buffer`. Visibility controlled by `ConditionalContainer` in app layout.
- `actions.py` — Editor detection and launch (VSCode, Cursor, Antigravity, system open), clipboard via `pbcopy`
- `detail.py` — `DetailPanel` class rendering full repo info (alias, name, path, description, remotes, tags, actions). Supports inline alias edit and tag management popovers.

**Data flow**: Scanner finds git dirs → creates `ScanResult(repo, remotes)` → Store upserts into SQLite → TUI loads from Store for display/search.

## UI Terminology

The TUI has two views: **列表视图**（list view）and **详情视图**（detail view）.

### 列表视图（List View）

```
┌─────────────────────────────────────────────────────────────────────┐
│   ▸ name (alias) [tag]  ┐        ┐                                 │
│     /path/to/repo       ┘ 列表项 ┘ ← 项目列表                      │
│─────────────────────────────────────────────────────────────────────│
│ description  /path/to/repo                            ← 状态栏      │
│ Enter:detail  /:search  Shift+V:code …               ← 快捷键栏  │
└─────────────────────────────────────────────────────────────────────┘
```

- **搜索栏**（search bar）— 默认完全隐藏。按 `/` 展开带亮色边框的搜索输入框进入搜索输入态。Enter 确认后输入框隐藏，顶部显示当前搜索词（只读）。Esc/Ctrl+C 清空搜索恢复全部。
- **项目列表**（repo list）— 两行式列表，`↑/↓` 方向键或 `Shift+↑/↓` 导航
  - **列表项**（list item）— 每项占两行：
    - 第一行 = 指示符（`▸` 选中态 / 空格 普通态）+ 名称/别名 + 标签
    - 第二行 = 路径
  - 选中项以高亮背景区分（`#264f78`）
  - 无项目时显示空状态提示
- **状态栏**（status bar）— 显示选中项目的描述和路径（无描述时仅显示路径）；过滤态下显示搜索词和结果数
- **快捷键栏**（footer）— 使用暗淡样式（`fg:#30363d`），按 Shift+操作键时短暂高亮 2 秒

### 列表视图快捷键

| 按键 | 功能 | 需要Shift |
|------|------|:---------:|
| `↑` / `↓` | 导航 | ✗ |
| `Enter` | 进入详情视图 | ✗ |
| `/` | 进入搜索 | ✗ |
| `Shift+V` | 用 VSCode 打开 | ✓ |
| `Shift+U` | 用 Cursor 打开 | ✓ |
| `Shift+A` | 用 Antigravity 打开 | ✓ |
| `Shift+O` | 用系统默认方式打开 | ✓ |
| `Shift+P` | 复制仓库路径到剪贴板 | ✓ |
| `Shift+R` | 重新扫描文件系统 | ✓ |
| `Ctrl+C` ×2 | 退出程序（2秒内按两次） | ✗ |

- 列表视图下裸按键（`v`/`u`/`a`/`o`/`p`/`r`/`j`/`k`/`q`）不触发任何操作
- `Esc` 不退出程序，仅用于清空搜索

### 搜索状态

搜索有三个状态：
1. **inactive** — 默认状态，搜索区域完全隐藏
2. **active** — 按 `/` 进入，搜索输入框展开（带亮色边框），实时过滤。仅可打印字符、Backspace、Enter、Esc/Ctrl+C 生效
3. **filtering** — Enter 确认后进入，输入框隐藏，顶部显示搜索词（只读）。再按 `/` 恢复输入框继续编辑

### 退出机制

- `q` 键不绑定，按 `q` 无任何效果
- `Esc` 不退出程序，仅用于取消操作（退出编辑态、退出搜索、返回列表、清空搜索）
- 退出程序需要连续两次 `Ctrl+C`（2 秒窗口），第一次在状态栏显示提示
- `Ctrl+C` 按优先级链消费：编辑态 → 搜索输入态 → 详情视图（返回列表）→ 列表视图（双击退出）

### 详情视图（Detail View）

```
┌─────────────────────────────────────────────────┐
│   ▸ Name      repo-name           ← 选中行     │
│     Alias     (none)                              │
│     Path      /path/to/repo                       │
│     Desc      description                         │
│─────────────────────────────────────────────────│
│     Git       https://github.com/org/repo         │
│     Tags      [python] [api]                      │
│─────────────────────────────────────────────────│
│     Open with Antigravity                        │
│     Open with Cursor                             │
│     Open with Visual Studio Code                 │
│     Open with Finder                             │
└─────────────────────────────────────────────────┘
```

- **详情面板**（detail panel）— 10 行可选中，每行按 Enter 执行对应操作
  - 行 0（Name）— Enter 复制项目名称，状态栏提示
  - 行 1（Alias）— Enter 进入别名编辑态
  - 行 2（Path）— Enter 复制路径，状态栏提示
  - 行 3（Description）— Enter 进入描述编辑态
  - 行 4（Git）— Enter 将 SSH 地址转为 HTTPS 并在浏览器打开
  - 行 5（Tags）— Enter 进入标签编辑态
  - 行 6-9（Open with Antigravity/Cursor/VSCode/Finder）— Enter 执行打开
- `↑`/`↓` 切换选中行（无需 Shift）
- `Esc` / `Ctrl+C` 返回列表视图
- 编辑态（Alias/Description/Tags）下 `↑`/`↓` 被屏蔽，Enter 保存，Esc/Ctrl+C 取消，支持中文等非 ASCII 输入，编辑时面板底部渲染编辑输入行并显示光标
- 无 footer 快捷键栏

### 编辑模式（Edit Modes）

编辑模式仅在详情视图中触发：

- **别名编辑模式**（alias edit）— 选中 Alias 行按 Enter 进入，Enter 保存，Esc/Ctrl+C 取消
- **描述编辑模式**（description edit）— 选中 Description 行按 Enter 进入，Enter 保存，Esc/Ctrl+C 取消
- **标签管理模式**（tag edit）— 选中 Tags 行按 Enter 进入，输入+Enter 添加，`Shift+1`~`Shift+9` 删除，Esc/Ctrl+C 退出

## Key Patterns

- Store uses lazy SQLite connection (`_connect()` on first access) with `check_same_thread=False` for background scan support
- Scanner's `run_scan(blocking=True/False)` toggles between synchronous and threaded execution
- TUI uses `app.invalidate()` to trigger re-renders after state changes
- Config falls back to defaults if the file is missing or corrupted, and rewrites it
- Detail panel manages its own `_cursor_index` and `_edit_mode` state; arrow keys and Enter are delegated to the panel when in detail view. Git row displays SSH→HTTPS converted URL; Enter opens in browser via `webbrowser.open()`. Edit mode appends a separator + input line (e.g. " Alias: <text>") at the bottom of `_build_lines`; `create_content` sets `UIContent.show_cursor=True` with `cursor_position=Point(x=col, y=last_row)` to place the terminal cursor at the end of the input line; `DetailPanel.is_focusable()` returns `True` so the window receives focus for cursor display.
- Layout switching replaces `app.layout` entirely (list layout vs detail layout), stored in `_list_layout` for reuse. Detail view stores `_detail_window` reference and calls `layout.focus()` on it.
- Search area completely hidden by default via `ConditionalContainer` with `_search_filtering and not _search_active` for the prefix and `_search_active` for the bordered input. Search input has no background color; bright border (`fg:#58a6ff`) surrounds it via `Window(char="─")` lines above and below.
- Key bindings use `Condition` filters for view-dependent behavior (e.g. shift-gated `V`/`U`/`A`/`O`/`P`/`R` for list view)
- Footer highlight timer uses `threading.Timer` for 2-second decay
- Style class names avoid prompt_toolkit built-in names (e.g. `repo-selected` instead of `selected`) to prevent style conflicts
- Tests create real git repos via subprocess in `tmp_path` fixtures
