# UI 术语与快捷键规范

## 布局

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
│                      │   ▸ Terminal  Open in Terminal      [Shift+1]│
│                      │     IDE       Open with IDE         [Shift+2]│
│                      │     Finder    Open in Finder        [Shift+3]│
│                      │ ─────────────────────────────────────────── │
│                      │     Git       Open in Browser       [Shift+4]│
│                      │     Commit    Auto Commit Changes   [Shift+5]│
│                      │     Pull      Pull Changes          [Shift+6]│
│                      │ ─────────────────────────────────────────── │
│                      │     Task      Add todo task         [Shift+7]│
│                      │     Review    AI Code Review        [Shift+8]│
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

## 搜索栏

- 默认完全隐藏，按 `/` 展开带亮色边框的搜索输入框
- Enter 确认后输入框隐藏，顶部显示当前搜索词（只读）
- Esc/Ctrl+C 清空搜索恢复全部
- 搜索范围：名称、别名、描述、路径、远程 URL、标签
- 在左右焦点下均可触发

## 项目列表

- 左侧面板，约 48% 宽度，两行式列表
- **列表项**（每项两行）：
  - 第一行 = 指示符（`▸` 选中 / 空格 普通）+ `★`（置顶）+ 名称/别名 + 标签
  - 第二行 = 路径（左对齐）+ 状态徽标（右对齐）
- **状态徽标**颜色与状态：
  - 干净：`main ●`（绿 `#3fb950`）
  - 有变更：`feature ○ +3`（橙 `#f0883e`）
  - 领先/落后：`main ● ↑1 ↓3`（黄 `#d29922`）
  - 加载中：`···`（灰）
  - 获取失败：`⚠`（灰）
- 排序：置顶优先 → 查看次数降序 → 名称升序

## 详情面板

- 右侧面板，约 52% 宽度，三个区域：
- **Metadata**（只读）：Name / Path / Repo / Status，不可选中，CJK 感知自动换行
  - Path 和 Repo 行支持鼠标点击交互（Path 在终端打开，Repo 在浏览器打开）
- **Actions**（可选中，分三组 + 动态 Report 行）：
  - Group 1: Terminal(0) / IDE(1) / Finder(2) — 快捷键 Shift+1/2/3
  - Group 2: Git(3) / Commit(4) / Pull(5) — 快捷键 Shift+4/5/6
  - Group 3: Task(6) / Review(7) — 快捷键 Shift+7/8
  - Report（动态，仅存在 review 报告时显示）
  - 未聚焦：普通态 + 快捷键徽标（如 `[Shift+1]`）
  - 聚焦：选中行显示 `[Enter]`，默认选中 Terminal（行 0）
  - 组间分割线为通栏长线
- **Local Markers**（可选中，紧接 Actions 后）：
  - 未聚焦：无选中效果
  - 聚焦：显示当前选中行

## 状态栏

- 显示选中项目的描述和路径
- 编辑态时显示输入内容和光标
- 过滤态下显示搜索词和结果数
- 所有操作反馈提示 5 秒后自动消失

## 快捷键栏

- 显示主要快捷键
- 按 Shift+操作键时短暂高亮 2 秒（`threading.Timer`）

## 焦点状态

- 三态：`"list"` / `"detail"` / `"edit"`
- 焦点侧边框高亮色（`#58a6ff`），非焦点侧暗灰（`#30363d`）

## 快捷键表

| 按键 | 功能 | 可用焦点 |
|------|------|----------|
| `↑` / `↓` | 列表导航 / 详情行导航 | list / detail |
| `Enter` | 打开 IDE（列表）/ 执行操作（详情）| list / detail |
| `/` | 进入搜索 | list, detail |
| `Tab` / `→` | 焦点移至右侧详情面板 | list |
| `Esc` / `←` | 焦点移回左侧列表 | detail |
| `Shift+1` | 打开终端 | list, detail |
| `Shift+2` | 用 IDE 打开 | list, detail |
| `Shift+3` | 在 Finder 中打开 | list, detail |
| `Shift+4` | 浏览器打开远程仓库 | list, detail |
| `Shift+5` | AI 自动提交变更 | list, detail |
| `Shift+6` | 拉取最新代码 | list, detail |
| `Shift+7` | 添加 Todo 任务 | list, detail |
| `Shift+8` | AI Code Review | list, detail |
| `Shift+R` | 重新扫描 | list, detail |
| `Ctrl+C` ×2 | 退出程序 | any |

- 编辑态屏蔽：全局 Shift 快捷键、↑↓
- 编辑态保留：Enter 保存、Esc/Ctrl+C 取消

## 窄终端降级

- 终端宽度 < 80 列时右侧面板折叠
- 通过 `ConditionalContainer` + `_is_wide_enough()` 实现
