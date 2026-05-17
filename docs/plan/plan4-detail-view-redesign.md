# Plan 4: 详情视图交互重构

## 目标

将详情视图从"快捷键驱动"改为"表单式行选中"交互——用户通过上下键选中某一行，按 Enter 执行该行操作。

---

## 变更项

### 4.1 移除列表视图中的编辑快捷键

**现状**：列表视图中 `e` 编辑别名、`t` 管理标签。

**改为**：
- 列表视图中移除 `e`（别名编辑）和 `t`（标签管理）快捷键
- 别名、标签、描述的编辑操作**仅在详情视图**中通过行选中交互触发
- 列表视图相关的 edit mode 代码（`_editing_alias`、`_editing_tag`、`_alias_buffer`、`_tag_buffer` 等）一并清理

**涉及文件**：
- `src/blink/tui/app.py` — 移除 `e`/`t` 绑定及列表视图 edit mode 状态

### 4.2 数据层：新增 `set_description`

**现状**：Store 只有 `set_alias`、`add_tag`、`remove_tag`，没有编辑 description 的接口。

**改为**：
- Store 新增 `set_description(repo_id: int, description: str)` 方法
- SQL: `UPDATE repos SET description = ? WHERE id = ?`

**涉及文件**：
- `src/blink/store.py` — 新增 `set_description` 方法

### 4.3 详情视图行选中机制

**现状**：详情视图是纯展示，操作靠全局快捷键触发。

**改为**：
- 详情视图每一行可被选中（高亮），用 `↑`/`↓` 方向键切换
- `j`/`k` 不存在（已全局删除）
- `↑`/`↓` **不需要 Shift**，直接触发
- 编辑态下 `↑`/`↓` **被屏蔽**，不触发导航
- 选中效果：当前选中行以高亮背景区分（`#264f78`，与列表视图选中色一致）

**行结构**（从上到下）：

| 行序号 | 内容 | 选中后 Enter 操作 |
|--------|------|-------------------|
| 0 | Alias | 进入别名编辑态 |
| 1 | Name | 复制项目名称到剪贴板，状态栏提示"已复制项目名称" |
| 2 | Path | 复制路径到剪贴板，状态栏提示"已复制项目路径" |
| 3 | Description | 进入描述编辑态 |
| 4 | Remotes | 复制远程地址到剪贴板，状态栏提示"已复制远程地址" |
| 5 | Tags | 进入标签编辑态 |
| 6 | Scanned | 复制扫描时间到剪贴板，状态栏提示"已复制扫描时间" |
| 7 | 用 Antigravity 打开 | 执行打开 |
| 8 | 用 Cursor 打开 | 执行打开 |
| 9 | 用 Visual Studio Code 打开 | 执行打开 |
| 10 | 用 Finder 打开 | 执行打开 |

**涉及文件**：
- `src/blink/tui/detail.py` — 新增 `_cursor_index: int` 状态，重写 `_formatted_text` 渲染逻辑（每行加选中高亮）
- `src/blink/tui/app.py` — 详情视图中绑定 `↑`/`↓`/`Enter` 到详情视图的行选中逻辑

### 4.4 行选中后的交互

#### 编辑类行（Alias / Description / Tags）

所有编辑态共享以下规则：
- 进入后 **只响应**：可打印字符、Backspace、Enter（保存）、Esc/Ctrl+C（取消）
- 编辑态下 `↑`/`↓` 被屏蔽，不能导航
- Ctrl+C 按优先级链消费：编辑态 > 详情视图（不会触发详情视图退出）

**Alias 行**被选中 + Enter：
- 进入编辑态，状态栏显示输入框，**预填当前别名值**
- Enter 保存 → Store 调用 `set_alias` → 刷新详情面板 → 退出编辑态
- Esc/Ctrl+C 取消，恢复原值

**Description 行**被选中 + Enter：
- 进入编辑态，状态栏显示输入框，**预填当前描述值**（如已有 description，方便用户参考/复制）
- Enter 保存 → Store 调用 `set_description` → 刷新详情面板 → 退出编辑态
- Esc/Ctrl+C 取消，恢复原值

**Tags 行**被选中 + Enter：
- 进入标签编辑态
- 编辑态下额外响应：
  - 输入标签名 + Enter → 添加标签（Store 调用 `add_tag`，实时刷新）
  - `Shift+1`~`Shift+9` → 删除对应序号标签（Store 调用 `remove_tag`，实时刷新）
- Esc/Ctrl+C 退出编辑态

#### 复制类行（Name / Path / Remotes / Scanned）

- Enter → 将该行内容复制到剪贴板 → 状态栏提示"已复制 XXX"

#### 操作类行（Antigravity / Cursor / VSCode / Finder）

- Enter → 调用对应编辑器/系统打开仓库路径

**涉及文件**：
- `src/blink/tui/detail.py` — 各行 Enter handler、编辑态管理
- `src/blink/tui/app.py` — `↑`/`↓`/`Enter` 绑定委派到 detail panel

### 4.5 详情视图底部操作区

**现状**：详情视图底部有快捷键栏（footer），显示 `e:edit alias t:manage tags …`。

**改为**：
- **移除详情视图的快捷键栏（footer）**
- 详情面板底部追加 4 行操作项（作为可选中行，见上表行 7-10）：
  ```
  ○ Antigravity
  ○ Cursor
  ○ Visual Studio Code
  ○ Finder
  ```
- 这些行通过 ↑↓ 导航、Enter 执行
- 详情视图通过 `Esc` / `Ctrl+C` 返回列表视图

**涉及文件**：
- `src/blink/tui/detail.py` — 渲染底部操作行
- `src/blink/tui/app.py` — 移除详情视图 footer 窗口

---

## 详情视图新布局

```
┌─────────────────────────────────────────────────┐
│   Alias     my-alias                 ← 选中高亮  │
│   Name      repo-name                             │
│   Path      /path/to/repo                         │
│   Desc      description text                      │
│   Remotes   origin → git@github.com:...           │
│   Tags      [tag1] [tag2]                         │
│   Scanned   2025-01-01                            │
│                                                   │
│   ○ Antigravity                                   │
│   ○ Cursor                                        │
│   ○ Visual Studio Code                            │
│   ○ Finder                                        │
│─────────────────────────────────────────────────│
│ 42 repos                           ← 状态栏      │
└─────────────────────────────────────────────────┘
```

- `↑`/`↓` 切换选中行（不需要 Shift）
- `Enter` 执行当前行操作
- `Esc` / `Ctrl+C` 返回列表视图
- 编辑态下 `↑`/`↓` 被屏蔽
- 无快捷键栏

---

## 影响范围

| 文件 | 变更类型 |
|------|----------|
| `src/blink/tui/app.py` | 移除列表编辑键、详情视图按键绑定、移除详情 footer |
| `src/blink/tui/detail.py` | 行选中状态、行渲染高亮、各行 Enter handler、底部操作行、编辑态管理 |
| `src/blink/store.py` | 新增 `set_description` 方法 |
| `CLAUDE.md` | 更新详情视图布局图、交互说明 |
| `README.md` | 更新详情面板说明 |
