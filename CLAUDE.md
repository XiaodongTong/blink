# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Constitutional Rules

**文档同步规范**：任何代码修改，都必须同步更新所有相关文档——包括 `CLAUDE.md`、`README.md`、以及这两个文件中引用到的本地 md 文件。涉及新增/删除/重命名模块、修改公开接口、变更快捷键或 UI 布局、更改配置项、调整架构或数据流等影响用户或开发者认知的变更，必须在提交前完成文档更新。纯格式调整、注释增删不影响行为的修改可豁免。

**CLI 参数简写规范**：所有 CLI 参数必须同时提供长参数和短参数形式（只要不冲突）。长参数使用 `--` 前缀，短参数使用 `-` 前缀。新增参数时必须一并添加对应的短参数。

## Project Overview

Blink is a lightweight terminal TUI tool for scanning, searching, and managing local git repositories. Written in Python, it uses `prompt-toolkit` for the TUI and `click` for CLI. Data is stored in SQLite under `~/.blink/`.

## Commands

```bash
uv sync                    # Install dependencies
uv run blink               # Launch the TUI
uv run blink -R            # Force full rescan before TUI (shorthand for --rescan)
uv run blink -v            # Show version (shorthand for --version)
uv run blink run -s        # Show task status (shorthand for --status)
uv run blink edit [path]   # Edit tasks.yaml / add task
uv run blink config-task -a [path]  # Add a task entry to tasks.yaml (shorthand for --add)
uv run blink commit -p .   # Auto-commit changes
uv run blink log [N]       # View task logs
uv run pytest              # Run all tests
uv run pytest tests/test_scanner.py  # Run a single test file
uv run pytest -k test_scan_paths_finds_git_repos  # Run a single test
uv build                   # Build distributable packages
```

Insert `breakpoint()` in source code and run `uv run blink` for pdb debugging.

## Architecture

**Entry point**: `src/blink/cli.py` — click group with `invoke_without_command=True`. When no subcommand is given, launches TUI. Five subcommands (`run`, `edit`, `config-task`, `commit`, `log`) delegate to `blink.loop` handler functions via argparse.Namespace shim objects.

**Core modules** (all in `src/blink/`):

- `models.py` — `Repo` (includes `pinned`, `view_count`, and `status` fields), `Remote`, and `RepoStatus` dataclasses. Also provides `display_width()` utility for CJK-aware character width calculation.
- `config.py` — JSON config loader (`~/.blink/config.json`), with defaults for scan paths, excludes, editor, `nerd_fonts`
- `scanner.py` — `Scanner` class that walks filesystem to find `.git` dirs, then fetches remotes/description via git subprocess. `StatusFetcher` class fetches git status (branch, dirty count, ahead/behind) in parallel via `git status --porcelain=v2 --branch`. `parse_status_v2()` parses porcelain v2 output. `parse_pull_output()` parses `git pull` output into (success, message). `check_pull_prereqs(repo)` validates repo eligibility for pull. Both fetcher classes use `ThreadPoolExecutor` for parallel processing and support blocking and background (threaded) modes.
- `store.py` — SQLite persistence layer (WAL mode). Tables: `repos`, `remotes`, `repo_status`, `schema_version`. Upsert-based writes. Full-text search across name/alias/description/path/remote URL. Schema migration v1→v2 adds `pinned` and `view_count` columns; v2→v3 adds `repo_status` table. `get_all_repos()`/`search_repos()` LEFT JOIN `repo_status` to populate `Repo.status`. Repos sorted by `pinned DESC, view_count DESC, name ASC`.

**Loop package** (`src/blink/loop/`):

- `config.py` — Constants for loop data directory (`~/.blink/loop/`), ANSI colors, YAML header. `ensure_tloop_home()` initializes directory structure. `load_config()` parses `tasks.yaml`.
- `state.py` — JSON state file management (`state.json`). Task status tracking and archiving of completed tasks.
- `git_ops.py` — Git safety checks (`is_git_repo`, `is_git_clean`, `has_staged_changes`), auto-commit via Claude (`ensure_clean_git`), branch creation (`create_task_branch`).
- `claude_runner.py` — `run_claude()` wraps `claude --dangerously-skip-permissions --print` with retry and verification loops.
- `review.py` — Post-task code review via self-critique. `review_changes()` diffs against base commit and sends to Claude.
- `task.py` — `run_task()` executes a single task: auto-commit, branch creation, runner selection (cybervisor/claude), state updates.
- `cmd_run.py` — `handle()` for `blink run` subcommand: runs tasks from `tasks.yaml`.
- `cmd_edit.py` — `handle()` for `blink edit`: unified IDE selection (uses `Config.preferred_ide` and `IDE_CHOICES` from `actions.py`), task file editing. `_add_task(path)` appends task entry and returns confirmation message string. Both TUI and `blink config-task --add` call `_add_task()` directly. TUI opens tasks.yaml in IDE after adding; CLI callers print the returned message.
- `cmd_commit.py` — `handle()` for `blink commit`: auto-commits dirty working tree via Claude.
- `cmd_log.py` — `handle()` for `blink log`: lists and displays task log files.
- `runner/` — `Runner` ABC with `ClaudeRunner` (round-loop execution) and `CybervisorRunner` backends.

**TUI** (`src/blink/tui/`):

- `app.py` — Main `BlinkApp` class. Composes two-column `VSplit` layout (left repo list ~48% width, right detail panel ~52%). Manages three-state focus pane (`_focus_pane`: `"list"` / `"detail"` / `"edit"`). All key bindings, search state machine, exit mechanism, edit-mode input routing, background scan orchestration, and background status fetching live here. `_open_with_ide(path)` generalizes IDE opening for any path; `_trigger_open_ide(repo)` delegates to it. Callbacks for detail panel actions: `_open_git_in_browser()` (webbrowser.open), `_run_add_task()` (calls `_add_task()` then opens tasks.yaml via `_open_with_ide()`), `_copy_repo_path()`, `_open_finder()`. Key bindings Shift+I/O/P/C/G/T/R/U wired with search/edit/IDE-selecting filters. Styles defined in `_build_style()` using GitHub dark theme colors. Narrow terminal (<80 cols) hides right panel via `ConditionalContainer`.
- `repo_list.py` — Custom `UIControl`/`Window` for the two-line repo list. Each repo renders as: line 1 = indicator + `★` (if pinned) + name/alias + tags, line 2 = path + right-aligned status badge (`branch ● +N ↑N ↓N`). Supports Nerd Font icons when `config.nerd_fonts` is True. Selected items pad lines to full width for consistent background fill. Badge uses CJK-aware width calculation via `display_width()`.
- `search.py` — `SearchBar` wrapping a `prompt_toolkit.Buffer`. Visibility controlled by `ConditionalContainer` in app layout.
- `actions.py` — Editor detection and launch (VSCode, Cursor, Antigravity, system open), clipboard via `pbcopy`. `IDE_CHOICES` defines the three IDE options for the unified IDE selection flow. Used by both TUI and CLI (`blink edit`).
- `detail.py` — `DetailPanel` class rendering repo info in three sections: Metadata (Name/Path/Repo/Status, read-only, with CJK-aware line wrapping for long values), Actions (IDE/Git/Commit/Task/Finder/Path, cursor-navigable indices 0–5), and Local Markers (Pinned/Alias/Tags/Desc, cursor-navigable indices 6–9). 10 cursor-navigable rows (MAX_LINE=9). Supports `set_repo(repo)` for real-time sync, inline alias/desc edit, tag management, pin toggle, and action callbacks. `_wrap_value()` performs CJK-aware word wrapping; `_build_info_lines()` produces one or more lines per metadata field. `_remote_to_https()` at module level converts SSH URLs to HTTPS for browser opening.
- `icons.py` — Nerd Font icon constants with ASCII fallbacks. `get_icon(nerd_fonts, nf_char, ascii_char)` selects the appropriate character.

**Data flow**: Scanner finds git dirs → creates `ScanResult(repo, remotes)` → Store upserts into SQLite → TUI loads from Store for display/search. StatusFetcher fetches git status → Store upserts into `repo_status` → TUI reloads repos (with status via LEFT JOIN) for badge display. List navigation triggers `_sync_detail_panel()` which calls `detail_panel.set_repo(repo)` for real-time right-panel updates. TUI Shift+C calls `blink.loop.git_ops.ensure_clean_git()` in background thread; Shift+T calls `blink.loop.cmd_edit._add_task()` then opens tasks.yaml via unified `_open_with_ide()` flow. `config-task --add` also calls `_add_task()` to append task entries. CLI subcommands delegate to `blink.loop.cmd_*` handlers. All loop data stored under `~/.blink/loop/`.

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
│                      │     Repo      https://github.com/...         │
│                      │     Status    main ●                        │
│                      │ ─────────────────────────────────────────── │
│                      │   ▸ IDE       Open with IDE        [Shift+I] │
│                      │     Git       Open in browser      [Shift+G] │
│                      │     Commit    Auto Commit Changes  [Shift+C] │
│                      │     Task      Add todo task        [Shift+T] │
│                      │     Finder    Open in Finder       [Shift+O] │
│                      │     Path      Copy repo path       [Shift+P] │
│                      │ ─────────────────────────────────────────── │
│                      │   ▸ Pinned    No        ← cursor row        │
│                      │     Alias     (none)                        │
│                      │     Tags      [python] [api]                │
│                      │     Desc      description                   │
│ ──────────────────   │ ──────────────────────────────────────────  │
├───────────────────────┴─────────────────────────────────────────────┤
│ status bar / edit input                                             │
│ footer: shortcuts                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

- **搜索栏**（search bar）— 默认完全隐藏。按 `/` 展开带亮色边框的搜索输入框进入搜索输入态。Enter 确认后输入框隐藏，顶部显示当前搜索词（只读）。Esc/Ctrl+C 清空搜索恢复全部。搜索在左右焦点下均可触发。
- **项目列表**（repo list）— 左侧面板，约 48% 宽度，两行式列表
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
- **详情面板**（detail panel）— 右侧面板，约 52% 宽度，三个区域：
  - **Metadata 区域**（只读）：Name/Path/Repo/Status，不可选中
  - **Actions 区域**（可选中）：IDE(0)/Git(1)/Commit(2)/Task(3)/Finder(4)/Path(5)，`↑`/`↓` 导航，Enter 执行操作。未聚焦时所有行显示为普通态并显示对应快捷键徽标（如 `[Shift+I]`）；聚焦时选中行显示 `[Enter]` 替代快捷键徽标，默认选中 IDE（行 0）
  - **Local Markers 区域**（可选中）：Pinned(6)/Alias(7)/Tags(8)/Desc(9)，`↑`/`↓` 导航，Enter 执行操作。未聚焦时无选中效果；聚焦时才显示当前选中行
- **状态栏**（status bar）— 显示选中项目的描述和路径；编辑态时显示输入内容和光标；过滤态下显示搜索词和结果数。所有操作反馈提示（如提交完成、路径已复制、任务已添加等）均显示在状态栏中，5 秒后自动消失
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
| `Shift+C` | 自动提交代码（AI commit） | list, detail |
| `Shift+G` | 在浏览器中打开远程仓库 | list, detail |
| `Shift+T` | 添加 Todo 任务（追加到 `~/.blink/loop/tasks.yaml`，完成后自动打开 IDE 编辑） | list, detail |
| `Shift+U` | 拉取最新代码 | list, detail |
| `Ctrl+C` ×2 | 退出程序（2秒内按两次）| any |

- 编辑态下全局快捷键（Shift+I/O/P/C/G/T/U）被屏蔽
- 编辑态下 `↑`/`↓` 被屏蔽，Enter 保存，Esc/Ctrl+C 取消
- `Esc` 不退出程序，用于取消编辑/搜索/焦点切换

### 退出机制

- `q` 键不绑定，按 `q` 无任何效果
- `Esc` 不退出程序，仅用于取消操作（退出编辑态、退出搜索、焦点切回列表）
- 退出程序需要连续两次 `Ctrl+C`（2 秒窗口）
- `Ctrl+C` 按优先级链消费：编辑态取消 → IDE 选择态取消 → 搜索态取消 → 双击退出

### 编辑模式（Edit Modes）

编辑模式在详情面板的 Local Markers 区域触发：

- **Pinned**（光标行 6）— Enter 直接切换置顶状态
- **Alias**（光标行 7）— Enter 进入别名编辑态，Enter 保存，Esc/Ctrl+C 取消
- **Tags**（光标行 8）— Enter 进入标签编辑态，输入+Enter 添加，`1`~`9` 按序号删除，Esc/Ctrl+C 退出
- **Description**（光标行 9）— Enter 进入描述编辑态，Enter 保存，Esc/Ctrl+C 取消
- 编辑时状态栏显示输入内容和光标，详情面板行保持原始值不变
- `view_count` 仅在 Local Markers 编辑操作（别名/标签/描述/置顶）时递增；Actions 行操作不递增

## Key Patterns

- Store uses lazy SQLite connection (`_connect()` on first access) with `check_same_thread=False` for background scan support
- Scanner's `run_scan(blocking=True/False)` toggles between synchronous and threaded execution
- StatusFetcher's `run_fetch(repos, blocking, on_status, on_error, on_done)` follows the same threaded pattern. On per-repo failure, calls `on_error(repo_id)` instead of upserting, preserving cached status. The TUI shows `⚠` for error repos via `RepoListControl.error_repo_ids`. Status fetch is triggered on startup and on Shift+R rescan completion.
- TUI uses `app.invalidate()` to trigger re-renders after state changes
- Config falls back to defaults if the file is missing or corrupted, and rewrites it. `nerd_fonts` config key (default `false`) controls icon rendering.
- Detail panel uses `set_repo(repo)` for real-time sync with list selection. Cursor covers Actions rows (0-5: IDE/Git/Commit/Task/Finder/Path) and Local Markers rows (6-9: Pinned/Alias/Tags/Desc). Metadata rows are display-only and wrap across multiple lines when values exceed available width (`_wrap_value` with CJK-aware width calculation). `set_focused(bool)` controls whether selection highlighting is shown; app calls it via `_set_focus(pane)` which also updates `_focus_pane`. Actions rows show `[Enter]` on the selected row when focused; when unfocused all rows render without selection effect and display shortcut badges instead.
- Single VSplit layout with `_focus_pane` three-state management (`"list"` / `"detail"` / `"edit"`). Focus switching updates border highlight styles dynamically. No layout replacement — focus is managed within the same layout.
- Search area completely hidden by default via `ConditionalContainer`. Available from both focus panes.
- Key bindings use `Condition` filters for focus-dependent behavior. `←`/`→` handle both IDE selection (eager) and focus switching based on filter priority.
- IDE selection mode (`_ide_selecting`) is a temporary overlay state in the status bar. `_open_with_ide(path)` generalizes IDE opening for any path (repo or file), checking `Config.preferred_ide` first, then falling back to selection mode with `_ide_pending_path`.
- Commit/Pull actions show static "正在提交..."/"正在拉取..." text in the status bar. All status bar notifications (commit/pull/task/copy/browser/open results) auto-dismiss after a configurable timeout (default 3s, task notifications use 2s) via `_set_scan_status(msg, timeout)`.
- Footer highlight timer uses `threading.Timer` for 2-second decay
- Style class names avoid prompt_toolkit built-in names (e.g. `repo-selected` instead of `selected`) to prevent style conflicts
- Tests create real git repos via subprocess in `tmp_path` fixtures
- Narrow terminal degradation (<80 cols) hides right panel via `ConditionalContainer` with `_is_wide_enough()` check
- CLI uses `click.group(invoke_without_command=True)` — `--rescan` stays on the group, subcommands (`run`/`edit`/`commit`/`log`) use lazy imports to avoid loading loop modules for TUI-only use
- TUI commit action (`_run_commit`) calls `blink.loop.git_ops.ensure_clean_git()` directly in a background thread with `quiet=True` — no subprocess, no PATH dependency on `tloop`, no stdout pollution
- TUI task action (`_run_add_task`) calls `blink.loop.cmd_edit._add_task()` which returns a message string, then opens tasks.yaml via unified `_open_with_ide()` (status bar shows success message with 2-second timeout). `blink config-task --add` also calls `_add_task()` and prints the returned message.
- Loop data directory is `~/.blink/loop/` (not `~/.tloop/`). Contains `tasks.yaml`, `state.json`, `logs/`, `archive/`
