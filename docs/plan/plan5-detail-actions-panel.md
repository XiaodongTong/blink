# Plan 5: 详情面板操作区重构

## 目标

将快捷操作从 footer 提示和静态 Shortcuts 区域迁移到右侧详情面板的可交互操作区（Actions），实现可视化、可选中、Enter 触发的操作列表。

## 当前布局（Before）

```
┌────────────────────────────────────────────────────────────────┐
│                    主内容区（双栏）                              │
├──────────────────┬─────────────────────────────────────────────┤
│  Repo List       │  Detail Panel                               │
│                  │    ── Metadata (只读) ──                     │
│                  │    Name / Path / Git / Status                │
│                  │    ───────────────── separator               │
│                  │    ── Local Markers (可选中) ──              │
│                  │    ▸ Pinned / Alias / Tags / Desc            │
│                  │    ───────────────── separator               │
│                  │    ── Shortcuts (静态文本) ──                │
│                  │    Shift+I:ide  Shift+O:Finder  ...          │
├──────────────────┴─────────────────────────────────────────────┤
│ status bar                                                     │
│ footer: Enter:ide /:search Tab:focus Shift+I:ide Shift+O:open │
│         Shift+P:path Shift+R:rescan Shift+C:commit Shift+U:pull│
└────────────────────────────────────────────────────────────────┘
```

**问题：**
1. Shortcuts 区域是静态文本，无法交互，且与 footer 快捷键提示重复
2. Footer 中 Shift+I/O/P/C 与右侧面板的操作完全重复，占据空间
3. 新增操作（Open in browser、Add Todo Task）缺少入口

## 目标布局（After）

```
┌────────────────────────────────────────────────────────────────┐
│                    主内容区（双栏）                              │
├──────────────────┬─────────────────────────────────────────────┤
│  Repo List       │  Detail Panel                               │
│                  │    ── Metadata (只读) ──                     │
│                  │    Name / Path / Git / Status                │
│                  │    ───────────────── separator               │
│                  │    ── Actions (可选中，cursor 可达) ──       │
│                  │    ▸ IDE     Open With IDE       --[Enter]  │
│                  │      Path    Copy project path   --[Shift+P]│
│                  │      Commit  Commit Changes      --[Shift+C]│
│                  │      Finder  Open with Finder    --[Shift+O]│
│                  │      Git     Open in browser     --[Shift+G]│
│                  │      Task    Add Todo Loop Task  --[Shift+T]│
│                  │    ───────────────── separator               │
│                  │    ── Local Markers (可选中) ──              │
│                  │    ▸ Pinned / Alias / Tags / Desc            │
├──────────────────┴─────────────────────────────────────────────┤
│ status bar                                                     │
│ footer: Enter:ide /:search Tab:focus Shift+R:rescan Shift+U:pull│
└────────────────────────────────────────────────────────────────┘
```

## 变更详情

### 1. detail.py — 新增 Actions 区域

**光标模型变更：**

```
# 原模型
LINE_PINNED = 0   # Local Markers 从 index 0 开始
LINE_ALIAS  = 1
LINE_TAGS   = 2
LINE_DESC   = 3
MAX_LINE    = 3

# 新模型 — Actions 占据 index 0-5，Local Markers 占据 index 6-9
LINE_IDE    = 0
LINE_PATH   = 1
LINE_COMMIT = 2
LINE_FINDER = 3
LINE_GIT    = 4
LINE_TASK   = 5
LINE_PINNED = 6
LINE_ALIAS  = 7
LINE_TAGS   = 8
LINE_DESC   = 9
MAX_LINE    = 9
```

**渲染变更（`_build_lines`）：**

在 Metadata separator 和 Local Markers 之间插入 Actions section：

```python
# ── Actions section (cursor-navigable) ──
lines.append(self._build_action_line("IDE    ", "Open With IDE      ", cur == self.LINE_IDE, width))
lines.append(self._build_action_line("Path   ", "Copy project path  ", cur == self.LINE_PATH, width))
lines.append(self._build_action_line("Commit ", "Auto Commit Changes", cur == self.LINE_COMMIT, width))
lines.append(self._build_action_line("Finder ", "Open with Finder   ", cur == self.LINE_FINDER, width))
lines.append(self._build_action_line("Git    ", "Open in browser    ", cur == self.LINE_GIT, width))
lines.append(self._build_action_line("Task   ", "Add Todo Loop Task ", cur == self.LINE_TASK, width))

# Separator
lines.append([("class:detail-sep", "─" * width)])
```

**新增 `_build_action_line` 方法：**

每行格式为 `▸ Label   Description    --[快捷键]`，选中时快捷键显示为 `--[Enter]`，未选中时显示原始快捷键。

```python
_ACTION_SHORTCUTS = {
    0: "Shift+I",  # IDE
    1: "Shift+P",  # Path
    2: "Shift+C",  # Commit
    3: "Shift+O",  # Finder
    4: "Shift+G",  # Git (新)
    5: "Shift+T",  # Task (新)
}

def _build_action_line(self, label: str, desc: str, selected: bool, width: int) -> list:
    cls = "detail-selected" if selected else "normal"
    lbl = "detail-label-sel" if selected else "label"
    shortcut = "Enter" if selected else self._ACTION_SHORTCUTS.get(...)
    # 指示符 + 标签 + 描述 + 右对齐 --[快捷键]
    ...
```

**`handle_enter` 变更：**

在 cursor_index 对应 Actions 行时，触发对应操作：

```python
if line == self.LINE_IDE:
    self._on_open_ide()
elif line == self.LINE_PATH:
    self._on_copy_path()      # 新增回调
elif line == self.LINE_COMMIT:
    self._on_commit()
elif line == self.LINE_FINDER:
    self._on_open_finder()    # 新增回调
elif line == self.LINE_GIT:
    self._on_open_git()       # 新增回调
elif line == self.LINE_TASK:
    self._on_add_task()       # 新增回调
```

**新增回调参数（`__init__`）：**

```python
on_copy_path: Callable[[], None] = lambda: None,
on_open_finder: Callable[[], None] = lambda: None,
on_open_git: Callable[[], None] = lambda: None,
on_add_task: Callable[[], None] = lambda: None,
```

**删除 `_build_shortcut_hints` 和 `_SHORTCUT_HINTS`。**

### 2. detail.py — 删除 Shortcuts 区域

- 删除 `_SHORTCUT_HINTS` 常量
- 删除 `_build_shortcut_hints` 方法
- `_build_lines` 中移除最后一个 separator 和 shortcuts 渲染

### 3. app.py — 新增回调实现

在 `_init_detail_panel` 中传入新回调：

| 回调 | 实现 |
|------|------|
| `on_copy_path` | 复用现有 Shift+P 逻辑：`copy_path(repo.path)` + 状态消息 |
| `on_open_finder` | 复用现有 Shift+O 逻辑：`open_in_editor(repo.path, "o", self._editors)` |
| `on_open_git` | **新增**：调用 `webbrowser.open(url)` 打开浏览器，url 由 `_remote_to_https(remote.url)` 转换（如 `https://github.com/XiaodongTong/clawx`） |
| `on_add_task` | **新增**：调用 `subprocess.Popen(["tloop", "edit", repo.path])`，模式与 commit 一致（非阻塞后台执行） |

**`on_open_git` 实现：**

```python
def _open_git_in_browser(self, repo: Repo) -> None:
    from blink.tui.detail import _remote_to_https
    if not repo.remotes:
        self._set_scan_status("No remote URL")
        return
    url = _remote_to_https(repo.remotes[0].url)
    if url:
        webbrowser.open(url)
        self._set_scan_status(f"Opened: {url}")
    else:
        self._set_scan_status("Cannot convert to HTTPS URL")
```

**`on_add_task` 实现：**

```python
def _run_add_task(self, repo: Repo) -> None:
    import subprocess
    if not shutil.which("tloop"):
        self._set_scan_status("未安装 tloop")
        return
    proc = subprocess.Popen(
        ["tloop", "edit", repo.path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # 后台等待完成，显示结果
    def wait_and_refresh():
        proc.wait()
        self._start_timer(0.5, lambda: self._set_scan_status(
            "✓ Task 已更新" if proc.returncode == 0 else "✗ Task 更新失败"
        ))
    t = threading.Thread(target=wait_and_refresh, daemon=True)
    t.start()
```

### 4. app.py — 新增 Shift+G / Shift+T 快捷键

```python
@kb.add("G", filter=...)
def _(event):
    repo = self._get_active_repo()
    if repo:
        self._open_git_in_browser(repo)

@kb.add("T", filter=...)
def _(event):
    repo = self._get_active_repo()
    if repo:
        self._run_add_task(repo)
```

### 5. app.py — Footer 精简

从 footer hints 中移除已迁移到 Actions 区域的快捷键：

```python
# Before
hints = [
    ("Enter", "ide"), ("/", "search"), ("Tab", "focus"),
    ("Shift+I", "ide"), ("Shift+O", "open"), ("Shift+P", "path"),
    ("Shift+R", "rescan"), ("Shift+C", "commit"), ("Shift+U", "pull"),
]

# After — 移除 Shift+I/O/P/C，新增 Shift+G/T
hints = [
    ("Enter", "ide"), ("/", "search"), ("Tab", "focus"),
    ("Shift+R", "rescan"), ("Shift+G", "browser"), ("Shift+T", "task"), ("Shift+U", "pull"),
]
```

### 6. `set_repo` 重置光标

`set_repo()` 中重置 `_cursor_index = 0`，现在指向第一个 Action 行（IDE），行为不变。

## 光标导航总结

```
index  区域           行为
─────────────────────────────────
0      Actions:IDE    Enter → 打开 IDE
1      Actions:Path   Enter → 复制路径
2      Actions:Commit Enter → 提交代码
3      Actions:Finder Enter → Finder 打开
4      Actions:Git    Enter → 浏览器打开
5      Actions:Task   Enter → 添加 Task
6      Markers:Pinned Enter → 切换置顶
7      Markers:Alias  Enter → 编辑别名
8      Markers:Tags   Enter → 编辑标签
9      Markers:Desc   Enter → 编辑描述
```

↑/↓ 在 index 0-9 之间连续导航。跨区域无阻断。

## 样式

Actions 行复用 Local Markers 的选中样式：

| 元素 | 未选中样式 | 选中样式 |
|------|-----------|---------|
| 指示符 | `class:dim` + 4 空格 | `class:detail-indicator` + `▸ ` |
| 标签 | `class:label` | `class:detail-label-sel` |
| 内容 | `class:normal` | `class:detail-selected` |
| 快捷键 | `class:detail-shortcut-dim` | `class:detail-shortcut-key`（高亮） |
| 行背景填充 | 无 | `class:detail-selected` |

## 涉及文件

| 文件 | 变更类型 |
|------|---------|
| `src/blink/tui/detail.py` | 新增 Actions section、删除 Shortcuts section、新增光标行号常量、新增回调参数 |
| `src/blink/tui/app.py` | 新增回调实现、新增 Shift+G/T 绑定、footer 精简 |
| `CLAUDE.md` | 更新 UI Terminology 中的 Layout 描述、快捷键表、Detail Panel 描述 |
| `README.md` | 同步更新快捷键说明和布局描述 |

## 不涉及

- 左侧 Repo List 无变更
- 搜索功能无变更
- Store / Scanner / Config 无变更
- 编辑模式（alias/tags/desc）行为不变
