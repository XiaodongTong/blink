# TUI 详细说明

## app.py — BlinkApp 主类

- 双栏 `VSplit` 布局（左列表 ~48% + 右详情 ~52%）
- 三态焦点管理：`_focus_pane` = `"list"` / `"detail"` / `"edit"`
- 所有按键绑定、搜索状态机、退出机制、编辑态输入路由、后台扫描/状态获取均在此
- `_open_with_ide(path)` 统一 IDE 打开逻辑，`_trigger_open_ide(repo)` 委托给它
- 操作回调：`_open_git_in_browser()`、`_run_add_task()`、`_copy_repo_path()`、`_open_finder()`、`_run_review()`
- Shift+V 触发 review 分支选择：获取最近 5 分支（`git_ops.get_recent_branches()`），←→ 导航，Enter 确认
- Shift+L 打开最近 review 报告到 IDE
- 样式定义在 `_build_style()`，使用 GitHub dark 主题色
- 窄终端（<80列）通过 `ConditionalContainer` 隐藏右面板

### 焦点与编辑
- `_set_focus(pane)` 更新 `_focus_pane` 并调用 `detail.set_focused()` 和边框样式
- 编辑态屏蔽全局快捷键（Shift+I/O/P/C/G/T/U）和 ↑↓
- IDE 选择模式（`_ide_selecting`）是状态栏临时覆盖层

### 后台操作
- Status fetch：启动时和 Shift+R rescan 完成后触发
- Commit/Pull：后台线程，状态栏显示"正在提交..."/"正在拉取..."
- 所有状态栏通知通过 `_set_scan_status(msg, timeout)` 自动消失（默认 3s，task 通知 2s）

## repo_list.py

自定义 `UIControl` / `Window`，两行式列表渲染：

- 第一行 = 指示符（`▸` 选中 / 空格 普通）+ `★`（置顶）+ 名称/别名 + 标签
- 第二行 = 路径（左对齐）+ 状态徽标（右对齐）
- Nerd Font 图标支持（`config.nerd_fonts` 控制）
- 选中项填充整行宽度保持背景色一致
- 徽标使用 `display_width()` 做 CJK 宽度计算

## search.py

`SearchBar` 封装 `prompt_toolkit.Buffer`，通过 `ConditionalContainer` 控制可见性。

## actions.py

- 编辑器检测与启动（VSCode、Cursor、Antigravity、系统 open）
- 剪贴板通过 `pbcopy`
- `IDE_CHOICES` 定义三个 IDE 选项
- TUI 和 CLI（`blink edit`）共用

## detail.py — DetailPanel 类

三区布局渲染仓库信息：

### Metadata（只读）
- Name / Path / Repo / Status
- CJK 感知自动换行（`_wrap_value()`）
- `_build_info_lines()` 每字段可产生多行

### Actions（可选中，索引 0-6）
- IDE(0) / Git(1) / Commit(2) / Task(3) / Finder(4) / Review(5) / Path(6)
- 聚焦时选中行显示 `[Enter]`，未聚焦时显示快捷键徽标
- 默认选中 IDE（行 0）

### Local Markers（可选中，索引 7-10）
- Pinned(7) / Alias(8) / Tags(9) / Desc(10)
- 仅聚焦时显示选中效果

### 编辑操作
- `set_repo(repo)` 实时同步列表选择
- 内联别名/描述编辑、标签管理、置顶切换
- `view_count` 仅在 Local Markers 编辑操作时递增，Actions 操作不递增

### 工具函数
- `_remote_to_https()`：模块级函数，SSH URL 转 HTTPS 用于浏览器打开

## icons.py

Nerd Font 图标常量 + ASCII 回退。`get_icon(nerd_fonts, nf_char, ascii_char)` 选择字符。

## 退出机制

- `q` 不绑定
- `Esc` 仅取消操作（退出编辑/搜索/焦点切回列表），不退出程序
- 退出需连续两次 `Ctrl+C`（2秒窗口）
- `Ctrl+C` 优先级链：编辑态取消 → IDE 选择态取消 → 搜索态取消 → 双击退出

## 编辑模式

在 Local Markers 区域触发：

- **Pinned**（行 7）：Enter 直接切换
- **Alias**（行 8）：Enter 进入编辑，Enter 保存，Esc/Ctrl+C 取消
- **Tags**（行 9）：Enter 进入编辑，输入+Enter 添加，`1`~`9` 按序号删除，Esc/Ctrl+C 退出
- **Description**（行 10）：Enter 进入编辑，Enter 保存，Esc/Ctrl+C 取消
- 编辑时状态栏显示输入内容和光标，详情面板行保持原始值
