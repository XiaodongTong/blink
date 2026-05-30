# TUI 详细说明

## app.py — BlinkApp 主类

- 初始化协调，组装各子模块
- 三态焦点管理：`_focus_pane` = `"list"` / `"detail"` / `"edit"`
- 后台操作（scan/commit/pull/status fetch）的线程管理和回调调度
- 操作回调：`_open_git_in_browser()`、`_run_add_task()`、`_open_terminal()`、`_open_finder()`
- 所有状态栏通知通过 `_set_scan_status(msg, timeout)` 自动消失（默认 3s，task 通知 2s）

### 焦点与编辑
- `_set_focus(pane)` 更新 `_focus_pane` 并调用 `detail.set_focused()` 和边框样式
- 编辑态屏蔽全局快捷键（Shift+1~8）和 ↑↓
- IDE 选择模式（`_ide_selecting`）是状态栏临时覆盖层

### 后台操作
- Status fetch：启动时和 Shift+R rescan 完成后触发
- Commit/Pull：后台线程，状态栏显示"正在提交..."/"正在拉取..."

## styles.py

样式定义（GitHub dark 主题色），`build_style()` 返回 `Style` 实例。纯数据模块，无状态依赖。

## layout.py

- `build_layout(app)` 构建双栏 `VSplit` 布局（左列表 ~48% + 右详情 ~52%）
- `EditStatusControl`：编辑模式状态栏的自定义 UIControl（支持光标位置显示）
- 窄终端（<80列）通过 `ConditionalContainer` 隐藏右面板

## key_bindings.py

`build_key_bindings(app)` 注册所有按键绑定：
- IDE 选择模式（最高优先级）
- Review 分支选择模式
- Ctrl+C 双击退出、Esc 取消链
- 焦点切换（Tab/←→）
- 列表/详情导航（↑↓）
- 搜索（/）、Shift+1~8（Terminal/IDE/Finder/Git/Commit/Pull/Task/Review）
- 编辑态字符路由（可打印字符、Backspace、CJK 输入）

## status_bar.py

状态栏和页脚文本渲染：
- `build_status_text(app)`：根据当前状态返回 FormattedText（IDE 选择、pull、review、commit、搜索、扫描等）
- `build_footer_text(app)`：页脚快捷键提示，支持高亮动画
- `build_search_prefix_text(app)`：搜索前缀显示

## app_review.py — ReviewOrchestrator

TUI Review 编排（`ReviewOrchestrator` 类）：
- `start_branch_select(repo)`：获取最近 5 分支（`git_ops.get_recent_branches()`），←→ 导航
- `confirm_branch()`：确认后执行 review
- `cancel()`：取消分支选择
- `_run_review(repo, branch)`：完整 review 流程（collect_context → setup_review_branch → AI → save_report）
- Shift+L 打开最近 review 报告到 IDE

## repo_list.py

> 已移至 `widgets/repo_list.py`。

自定义 `UIControl` / `Window`，两行式列表渲染：

- 第一行 = 指示符（`▸` 选中 / 空格 普通）+ `★`（置顶）+ 名称/别名 + 标签
- 第二行 = 路径（左对齐）+ 状态徽标（右对齐）
- Nerd Font 图标支持（`config.nerd_fonts` 控制）
- 选中项填充整行宽度保持背景色一致
- 徽标使用 `display_width()` 做 CJK 宽度计算

## search.py

> 已移至 `widgets/search.py`。

`SearchBar` 封装 `prompt_toolkit.Buffer`，通过 `ConditionalContainer` 控制可见性。

## actions.py

- 编辑器检测与启动（VSCode、Cursor、Antigravity、系统 open）
- Antigravity 兼容：`_detect_antigravity()` 检测 Antigravity IDE 变体
- 配置的 IDE 未安装时自动清空配置
- `open_terminal(repo_path)` 在终端中打开仓库路径
- 剪贴板通过 `pbcopy`
- `IDE_CHOICES` 定义三个 IDE 选项
- TUI 和 CLI（`blink edit`）共用

## detail.py — DetailPanel 类

> 已移至 `widgets/detail.py`，编辑逻辑在 `widgets/detail_edit.py`。

三区布局渲染仓库信息：

### Metadata（只读）
- Name / Path / Repo / Status
- Path 和 Repo 行支持鼠标点击交互（clickable=True）
- CJK 感知自动换行（`_wrap_value()`）
- `_build_info_lines()` 每字段可产生多行

### Actions（可选中，分三组 + 动态 Report）
- Group 1: Terminal(0) / IDE(1) / Finder(2) — 快捷键 Shift+1/2/3
- Group 2: Git(3) / Commit(4) / Pull(5) — 快捷键 Shift+4/5/6
- Group 3: Task(6) / Review(7) — 快捷键 Shift+7/8
- Report（动态行，仅存在 review 报告时显示，无快捷键）
- 聚焦时选中行显示 `[Enter]`，未聚焦时显示快捷键徽标
- 默认选中 Terminal（行 0）
- 组间分割线为通栏长线

### Local Markers（可选中，紧接 Actions 后）
- Pinned / Alias / Tags / Desc
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

- **Pinned**：Enter 直接切换
- **Alias**：Enter 进入编辑，Enter 保存，Esc/Ctrl+C 取消
- **Tags**：Enter 进入编辑，输入+Enter 添加，`1`~`9` 按序号删除，Esc/Ctrl+C 退出
- **Description**：Enter 进入编辑，Enter 保存，Esc/Ctrl+C 取消
- 编辑时状态栏显示输入内容和光标，详情面板行保持原始值
