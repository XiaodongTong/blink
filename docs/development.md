# Blink 开发指南

## 环境要求

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) — Python 包管理器
- [git](https://git-scm.com/) — 版本控制
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code)（可选，用于 AI 功能开发调试）

## 初始化

```bash
git clone <repo-url> blink && cd blink
uv sync
```

## 运行

```bash
uv run blink              # 启动 TUI
uv run blink -R           # 强制重新扫描
```

## 测试

```bash
uv run pytest                              # 全部测试
uv run pytest tests/test_scanner.py        # 单文件
uv run pytest -k test_scan_paths_finds_git_repos  # 单测试
```

## 调试

在源码任意位置插入 `breakpoint()`，运行 `uv run blink`，程序会在断点处进入 pdb。

## 构建

```bash
uv build    # 构建分发包
```

## 项目结构

```
src/
  cli.py              入口，click group
  models.py           Repo/Remote/RepoStatus 数据类
  logger.py           按天轮转日志
  config.py           JSON 配置加载
  scanner.py          仓库扫描 + git 状态并行获取
  store.py            SQLite 持久化（WAL），全文搜索
  tui/                TUI 模块
    app.py            主应用类
    styles.py         样式定义
    layout.py         双栏布局
    key_bindings.py   按键绑定
    status_bar.py     状态栏
    repo_list.py      列表控件
    detail.py         详情面板
    search.py         搜索栏
    actions.py        IDE 检测/启动、剪贴板
    icons.py          Nerd Font 图标常量
    widgets/          UI 控件
      detail.py       详情面板
      detail_edit.py  详情面板编辑 mixin
      repo_list.py    两行式列表控件
      search.py       搜索栏控件
  loop/               Loop 任务引擎
    cmd_run.py        run 子命令
    cmd_edit.py       edit 子命令
    cmd_commit.py     commit 子命令
    cmd_log.py        log 子命令
    task.py           任务编排
    state.py          状态管理
    git_ops.py        Git 操作
    review/           Code Review 子系统
      cmd.py          review 子命令
      context.py      review 上下文收集
      report.py       报告持久化
      analyzer.py     静态分析
      tester.py       测试执行
      verifier.py     验证 pass
    runner/           Runner 抽象
tests/                测试文件
docs/                 文档
  agents/             AI 协作文档
```

## 数据目录

```
~/.blink/
  config.json         用户配置
  blink.db            SQLite 数据库
  loop/               任务系统
    tasks.yaml        任务定义
    state.json        运行时状态
    logs/             执行日志
    archive/          已完成任务归档
  logs/               应用日志
```

## 详细文档

| 文档 | 内容 |
|------|------|
| [Loop 模块文档](agents/loop.md) | Loop 产品定位、架构、任务配置、Runner、状态管理、Code Review |
| [架构与数据流](agents/architecture.md) | 入口点、模块详细职责、完整数据流 |
| [TUI 详细说明](agents/tui.md) | 各 TUI 模块详细职责、焦点管理、编辑模式、退出机制 |
| [UI 术语与快捷键](agents/ui-spec.md) | 布局图、各区域规范、快捷键表、窄终端降级 |
| [关键开发模式](agents/key-patterns.md) | Store 懒连接、扫描模式、IDE 选择、提交/拉取、测试 |
| [Review 流程图](agents/review-flow.md) | AI Code Review 完整流程 |
