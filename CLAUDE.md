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

- `models.py` — `Repo` (includes `pinned`, `view_count`, and `status` fields), `Remote`, and `RepoStatus` dataclasses. Also provides `display_width()` utility for CJK-aware character width calculation.
- `config.py` — JSON config loader (`~/.blink/config.json`), with defaults for scan paths, excludes, editor, `nerd_fonts`
- `scanner.py` — `Scanner` class that walks filesystem to find `.git` dirs, then fetches remotes/description via git subprocess. `StatusFetcher` class fetches git status (branch, dirty count, ahead/behind) in parallel via `git status --porcelain=v2 --branch`. `parse_status_v2()` parses porcelain v2 output. `parse_pull_output()` parses `git pull` output into (success, message). `check_pull_prereqs(repo)` validates repo eligibility for pull. Both fetcher classes use `ThreadPoolExecutor` for parallel processing and support blocking and background (threaded) modes.
- `store.py` — SQLite persistence layer (WAL mode). Tables: `repos`, `remotes`, `repo_status`, `schema_version`. Upsert-based writes. Full-text search across name/alias/description/path/remote URL. Schema migration v1→v2 adds `pinned` and `view_count` columns; v2→v3 adds `repo_status` table. `get_all_repos()`/`search_repos()` LEFT JOIN `repo_status` to populate `Repo.status`. Repos sorted by `pinned DESC, view_count DESC, name ASC`.

**TUI** (`src/blink/tui/`):

- `app.py` — Main `BlinkApp` class. Composes two-column `VSplit` layout (left repo list ~40% width, right detail panel ~60%). Manages three-state focus pane (`_focus_pane`: `"list"` / `"detail"` / `"edit"`). All key bindings, search state machine, exit mechanism, edit-mode input routing, background scan orchestration, and background status fetching live here. Styles defined in `_build_style()` using GitHub dark theme colors. Narrow terminal (<80 cols) hides right panel via `ConditionalContainer`.
- `repo_list.py` — Custom `UIControl`/`Window` for the two-line repo list. Each repo renders as: line 1 = indicator + `★` (if pinned) + name/alias + tags, line 2 = path + right-aligned status badge (`branch ● +N ↑N ↓N`). Supports Nerd Font icons when `config.nerd_fonts` is True. Selected items pad lines to full width for consistent background fill. Badge uses CJK-aware width calculation via `display_width()`.
- `search.py` — `SearchBar` wrapping a `prompt_toolkit.Buffer`. Visibility controlled by `ConditionalContainer` in app layout.
- `actions.py` — Editor detection and launch (VSCode, Cursor, Antigravity, system open), clipboard via `pbcopy`. `IDE_CHOICES` defines the three IDE options for the unified IDE selection flow.
- `detail.py` — `DetailPanel` class rendering repo info in three sections: Metadata (Name/Path/Git/Status, read-only), Local Markers (Pinned/Alias/Tags/Desc, cursor-navigable), and Shortcuts (static hints). 4 cursor-navigable rows (MAX_LINE=3). Supports `set_repo(repo)` for real-time sync, inline alias/desc edit, tag management, and pin toggle.
- `icons.py` — Nerd Font icon constants with ASCII fallbacks. `get_icon(nerd_fonts, nf_char, ascii_char)` selects the appropriate character.

**Data flow**: Scanner finds git dirs → creates `ScanResult(repo, remotes)` → Store upserts into SQLite → TUI loads from Store for display/search. StatusFetcher fetches git status → Store upserts into `repo_status` → TUI reloads repos (with status via LEFT JOIN) for badge display. List navigation triggers `_sync_detail_panel()` which calls `detail_panel.set_repo(repo)` for real-time right-panel updates.

## UI Terminology

The TUI uses a **双栏联动布局**（two-column linked layout）.

### Layout Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│ [/ search bar — conditional, full width]                           │
├───────────────────────┬─────────────────────────────────────────────┤
│ ── Repos ──────────   │ ── Detail ──────────────────────────────── │
│   ▸ ★ name [tag]     │     Name      repo-name                     │
│     /path/to/repo    │     Path      /path/to/repo                 │
│                      │     Git       https://github.com/...         │
│                      │     Status    main ●                        │
│                      │ ─────────────────────────────────────────── │
│                      │   ▸ Pinned    No        ← cursor row        │
│                      │     Alias     (none)                        │
│                      │     Tags      [python] [api]                │
│                      │     Desc      description                   │
│                      │ ─────────────────────────────────────────── │
│                      │   Shift+I:ide  Shift+O:open  ...            │
│ ──────────────────   │ ──────────────────────────────────────────  │
├───────────────────────┴─────────────────────────────────────────────┤
│ status bar / edit input                                             │
│ footer: shortcuts                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

- **搜索栏**（search bar）— 默认完全隐藏。按 `/` 展开带亮色边框的搜索输入框进入搜索输入态。Enter 确认后输入框隐藏，顶部显示当前搜索词（只读）。Esc/Ctrl+C 清空搜索恢复全部。搜索在左右焦点下均可触发。
- **项目列表**（repo list）— 左侧面板，约 40% 宽度，两行式列表
  - **列表项**（list item）— 每项占两行：
    - 第一行 = 指示符（`▸` 选中态 / 空格 普通态）+ `★`（置顶项）+ 名称/别名 + 标签
    - 第二行 = 路径（左对齐）+ 状态徽标（右对齐）
  - **状态徽标**（status badge）— 右对齐显示当前分支和状态
    - 干净：`main ●`（绿色 `#3fb950`）
    - 有变更：`feature ○ +3`（橙色 `#f0883e`）
    - 领先/落后：`main ● ↑1 ↓3`（黄色 `#d29922`）
    - 加载中：`···`（灰色）
    - 获取失败：`⚠`（灰色）
  - 排序规则：置顶优先 → 查看次数降序 → 名称升序
- **详情面板**（detail panel）— 右侧面板，约 60% 宽度，三个区域：
  - **Metadata 区域**（只读）：Name/Path/Git/Status，不可选中
  - **Local Markers 区域**（可选中）：Pinned(0)/Alias(1)/Tags(2)/Desc(3)，`↑`/`↓` 导航，Enter 执行操作
  - **Shortcuts 区域**（静态）：显示 Shift+I/O/P/C/U 快捷键提示
- **状态栏**（status bar）— 显示选中项目的描述和路径；编辑态时显示输入内容和光标；过滤态下显示搜索词和结果数
- **快捷键栏**（footer）— 显示主要快捷键，按 Shift+操作键时短暂高亮 2 秒
- **焦点状态**（focus pane）— 三态：`"list"` / `"detail"` / `"edit"`
  - 焦点侧边框为高亮色（`#58a6ff`），非焦点侧暗灰色（`#30363d`）
- **窄终端降级** — 终端宽度 < 80 列时右侧面板折叠，仅显示列表

### 快捷键

| 按键 | 功能 | 可用焦点 |
|------|------|----------|
| `↑` / `↓` | 列表导航 / 详情行导航 | list / detail |
| `Enter` | 打开 IDE（列表焦点）/ 执行行操作（详情焦点）| list / detail |
| `/` | 进入搜索 | list, detail |
| `Tab` / `→` | 焦点移至右侧详情面板 | list |
| `Esc` / `←` | 焦点移回左侧列表 | detail |
| `Shift+I` | 用 IDE 打开 | list, detail |
| `Shift+O` | 用系统默认方式打开 | list, detail |
| `Shift+P` | 复制仓库路径到剪贴板 | list, detail |
| `Shift+R` | 重新扫描文件系统 | list, detail |
| `Shift+C` | 提交代码 | list, detail |
| `Shift+U` | 拉取最新代码 | list, detail |
| `Ctrl+C` ×2 | 退出程序（2秒内按两次）| any |

- 编辑态下全局快捷键（Shift+I/O/P/C/U）被屏蔽
- 编辑态下 `↑`/`↓` 被屏蔽，Enter 保存，Esc/Ctrl+C 取消
- `Esc` 不退出程序，用于取消编辑/搜索/焦点切换

### 退出机制

- `q` 键不绑定，按 `q` 无任何效果
- `Esc` 不退出程序，仅用于取消操作（退出编辑态、退出搜索、焦点切回列表）
- 退出程序需要连续两次 `Ctrl+C`（2 秒窗口）
- `Ctrl+C` 按优先级链消费：编辑态取消 → IDE 选择态取消 → 搜索态取消 → 双击退出

### 编辑模式（Edit Modes）

编辑模式在详情面板的 Local Markers 区域触发：

- **Pinned** — Enter 直接切换置顶状态
- **Alias** — Enter 进入别名编辑态，Enter 保存，Esc/Ctrl+C 取消
- **Tags** — Enter 进入标签编辑态，输入+Enter 添加，`1`~`9` 按序号删除，Esc/Ctrl+C 退出
- **Description** — Enter 进入描述编辑态，Enter 保存，Esc/Ctrl+C 取消
- 编辑时状态栏显示输入内容和光标，详情面板行保持原始值不变
- `view_count` 仅在编辑操作（别名/标签/描述/置顶）时递增，光标移动不递增

## Key Patterns

- Store uses lazy SQLite connection (`_connect()` on first access) with `check_same_thread=False` for background scan support
- Scanner's `run_scan(blocking=True/False)` toggles between synchronous and threaded execution
- StatusFetcher's `run_fetch(repos, blocking, on_status, on_error, on_done)` follows the same threaded pattern. On per-repo failure, calls `on_error(repo_id)` instead of upserting, preserving cached status. The TUI shows `⚠` for error repos via `RepoListControl.error_repo_ids`. Status fetch is triggered on startup and on Shift+R rescan completion.
- TUI uses `app.invalidate()` to trigger re-renders after state changes
- Config falls back to defaults if the file is missing or corrupted, and rewrites it. `nerd_fonts` config key (default `false`) controls icon rendering.
- Detail panel uses `set_repo(repo)` for real-time sync with list selection. Cursor only covers Local Markers rows (0-3: Pinned/Alias/Tags/Desc). Metadata rows are display-only.
- Single VSplit layout with `_focus_pane` three-state management (`"list"` / `"detail"` / `"edit"`). Focus switching updates border highlight styles dynamically. No layout replacement — focus is managed within the same layout.
- Search area completely hidden by default via `ConditionalContainer`. Available from both focus panes.
- Key bindings use `Condition` filters for focus-dependent behavior. `←`/`→` handle both IDE selection (eager) and focus switching based on filter priority.
- IDE selection mode (`_ide_selecting`) is a temporary overlay state in the status bar.
- Commit/Pull actions use braille spinner animations in the status bar with `threading.Timer` (120ms ticks).
- Footer highlight timer uses `threading.Timer` for 2-second decay
- Style class names avoid prompt_toolkit built-in names (e.g. `repo-selected` instead of `selected`) to prevent style conflicts
- Tests create real git repos via subprocess in `tmp_path` fixtures
- Narrow terminal degradation (<80 cols) hides right panel via `ConditionalContainer` with `_is_wide_enough()` check
