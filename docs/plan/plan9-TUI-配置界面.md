# TUI 配置界面

## 背景

当前 `~/.blink/config.json` 只能手动编辑，用户无法在 TUI 中直观地修改配置。同时 editor 配置项存储的是内部 key（如 `"a"` 代表 Antigravity），用户无法理解配置含义。需要一个独立的配置界面，让用户可以方便地查看和修改常用配置。

## 方案

### 1. editor 配置值改为展示名

**现状**：`config.json` 中 `editor: "a"`，`"a"` 是 `IDE_CHOICES` 的 key，用户不可读。

**改动**：将存储值从 key 改为展示名（`EditorInfo.name`），即 `editor: "Antigravity"`。

涉及修改：

| 文件 | 改动 |
|------|------|
| `src/tui/actions.py` | 新增 `find_editor_by_name(name) -> str | None`：遍历 `detect_editors()` 结果，按 `name` 字段查找，返回对应 key |
| `src/tui/app.py` `_open_with_ide()` | 读取 `config.editor` 后，调用 `find_editor_by_name()` 转换为 key，再传入 `open_in_editor()`。若找不到则视为已卸载，清除配置并弹出 IDE 选择 |
| `src/tui/key_bindings.py` IDE 选择确认处 | `app._config.set("editor", name)` 改为存储 name 而非 key |
| `src/config.py` | `editor` 默认值保持 `None`；新增 `_migrate_editor_key()` 私有方法，在 `_load()` 末尾调用：若值是旧格式（单字母 key），自动转换为 name 并保存 |

迁移逻辑伪代码：

```python
def _migrate_editor_key(self) -> None:
    val = self._data.get("editor")
    if val is None or len(val) > 1:
        return  # None 或已经是 name，无需迁移
    # val 是单字母 key，查表转换为 name
    from blink.tui.actions import IDE_CHOICES
    for key, name in IDE_CHOICES:
        if key == val:
            self._data["editor"] = name
            self._save()
            return
```

### 2. 新增配置面板

新增 `src/tui/app_config.py`，实现 `ConfigPanel(UIControl)`。

#### 布局结构

```
── Configuration ──────────────────────────

  Editor        Antigravity           [Enter]
  Commit Model  haiku                 [Enter]
  Review Model  opus                  [Enter]
  Task Model    opus                  [Enter]
  Task Review   opus                  [Enter]

── Other ─────────────────────────────────

  Scan Paths    ["~"]
  Exclude Dirs  [".Trash", ...]       (read-only)
  Auto Sync     0 days                (read-only)
  Nerd Fonts    false                 (read-only)

───────────────────────────────────────────
 [e] Edit in Editor   [Esc] Back
```

#### 配置项分组

**可编辑组**（回车触发选择）：

| 配置项 | 配置路径 | 选择来源 | 类型 |
|--------|----------|----------|------|
| Editor | `editor` | 已安装 IDE 列表（`detect_editors()` 中 `available=True` 的）| 枚举选择 |
| Commit Model | `models.commit` | 模型列表 | 枚举选择 |
| Review Model | `models.review` | 模型列表 | 枚举选择 |
| Task Model | `models.task` | 模型列表 | 枚举选择 |
| Task Review | `models.task_review` | 模型列表 | 枚举选择 |

**只读组**（本次不支持 TUI 修改，用 `(read-only)` 标注）：

| 配置项 | 配置路径 |
|--------|----------|
| Scan Paths | `scan_paths` |
| Exclude Dirs | `exclude_dirs` |
| Auto Sync | `auto_sync_days` |
| Nerd Fonts | `nerd_fonts` |

#### 选择模式

选中可编辑项后按 Enter，进入选择模式（类似现有 IDE 选择模式）：

- 面板底部弹出选项列表，当前值高亮
- 左右方向键切换高亮项
- Enter 确认选择并保存
- Escape / Ctrl+C 取消

模型选项列表固定为：`haiku`, `sonnet`, `opus`，3 个一行可放下。

IDE 可选项有 12 个，水平一排放不下。选中可视区域最后一条时自动向右滑动，露出后续选项；向左选中第一条可见项时向左回滑。实现方式：维护一个 `_select_scroll_offset` 变量，渲染时只显示从 offset 开始的 N 个选项（N = 面板宽度 / 单项宽度），光标到达边界时调整 offset。

选择确认后立即调用 `config.set()` 保存。

#### 编辑器打开

按 `e` 键用系统编辑器打开 `~/.blink/config.json`，退出编辑器后自动 reload 配置。

### 3. 主界面入口

在 `key_bindings.py` 中添加快捷键 `Shift+S`（即 `S`）进入配置界面。

进入配置界面时：
- `app._focus_pane` 切换为 `"config"`
- 将 `detail_window` 的 content 替换为 `ConfigPanel`
- 按 Escape 返回详情面板

### 4. 文件结构

| 文件 | 职责 |
|------|------|
| `src/tui/app_config.py` | `ConfigPanel` 类 + `ConfigSelectMode` 枚举 |
| `src/tui/app.py` | 新增 `_config_panel`、`_enter_config()`、`_exit_config()` 方法 |
| `src/tui/key_bindings.py` | 新增 `Shift+S` 绑定 + 配置选择模式按键处理 |
| `src/tui/actions.py` | 新增 `find_editor_by_name()` |
| `src/config.py` | 新增 `_migrate_editor_key()` |

### 5. 交互流程

```
主界面 → Shift+S → 配置面板（光标在可编辑组第一项）
                         │
            ┌────────────┼────────────┐
            ↓            ↓            ↓
         上下导航     Enter 选择    e 编辑文件
            │            │            │
            │      弹出选项列表      打开编辑器
            │      ← → 切换高亮      退出后 reload
            │      Enter 确认保存
            │            │            │
            └────────────┼────────────┘
                         ↓
                    Esc 返回主界面
```

## 影响范围

- `src/config.py`：editor 迁移逻辑
- `src/tui/actions.py`：新增查找函数
- `src/tui/app.py`：配置面板状态管理
- `src/tui/key_bindings.py`：新增快捷键和选择模式
- 新增 `src/tui/app_config.py`

## 待定

- 模型选项列表是否需要从 API 动态获取，还是硬编码 `haiku/sonnet/opus`
- `nerd_fonts` 是 bool 值，本次暂不开放编辑，后续可加入 toggle 切换
- 配置面板底部是否需要显示当前配置文件路径
- 选择模式已改为方向键 + Enter，与现有 IDE 选择模式交互一致，不再使用序号输入
