# 目录结构重组方案

## 背景

拆分超 500 行文件后，`src/loop/` 有 19 个文件（含 runner/），`src/tui/` 有 14 个文件，目录过于平铺。按职责和依赖关系，将高内聚文件组合到子目录中。

当前结构：

```
src/loop/                    src/tui/
  __init__.py                  __init__.py
  claude_runner.py             actions.py
  cmd_commit.py                app.py
  cmd_edit.py                  app_actions.py
  cmd_log.py                   app_review.py
  cmd_review.py                detail.py
  cmd_run.py                   detail_edit.py
  config.py                    icons.py
  git_ops.py                   key_bindings.py
  log_format.py                layout.py
  review_analyzer.py           repo_list.py
  review_context.py            search.py
  review_report.py             status_bar.py
  review_tester.py             styles.py
  review_verifier.py
  state.py
  task.py
  task_review.py
  runner/
    __init__.py
    claude.py
    cybervisor.py
```

## 方案

### 目标结构

```
src/loop/                    src/tui/
  __init__.py                  __init__.py
  claude_runner.py             actions.py
  cmd_commit.py                app.py
  cmd_edit.py                  app_actions.py
  cmd_log.py                   app_review.py
  cmd_run.py                   icons.py
  config.py                    key_bindings.py
  git_ops.py                   layout.py
  log_format.py                status_bar.py
  state.py                     styles.py
  task.py                      widgets/
  task_review.py                 __init__.py
  runner/                        detail.py
    __init__.py                  detail_edit.py
    claude.py                    repo_list.py
    cybervisor.py                search.py
  review/
    __init__.py
    cmd.py            (← cmd_review.py)
    context.py        (← review_context.py)
    report.py         (← review_report.py)
    analyzer.py       (← review_analyzer.py)
    tester.py         (← review_tester.py)
    verifier.py       (← review_verifier.py)
```

### 1. `src/loop/review/` — Code Review 子系统

6 个文件组成完整的 review 能力，`cmd.py` 依赖其余 5 个，其余 5 个互相独立：

| 原文件 | 新路径 | 行数 |
|--------|--------|------|
| `review_context.py` | `review/context.py` | 268 |
| `review_report.py` | `review/report.py` | 83 |
| `review_analyzer.py` | `review/analyzer.py` | 143 |
| `review_tester.py` | `review/tester.py` | 95 |
| `review_verifier.py` | `review/verifier.py` | 73 |
| `cmd_review.py` | `review/cmd.py` | 372 |

**依赖关系**（全部指向父级，无内部循环）：

- `cmd.py` → `context.py`, `report.py`, `analyzer.py`(lazy), `tester.py`(lazy), `verifier.py`(lazy), 父级 `git_ops`, `claude_runner`
- `context.py` → 父级 `git_ops`
- `analyzer.py` → 无 loop 依赖
- `tester.py` → 无 loop 依赖
- `verifier.py` → 父级 `claude_runner`
- `report.py` → 无 loop 依赖

**`review/__init__.py`** 重新导出关键符号，保持外部导入简洁：

```python
from blink.loop.review.cmd import handle, run_review, cleanup_review_branch, setup_review_branch
from blink.loop.review.report import ReviewResult, parse_verdict, save_report, ensure_review_dir
from blink.loop.review.context import build_review_prompt, collect_context
```

### 2. `src/tui/widgets/` — UI 控件

4 个文件是独立的 UI 控件，不依赖 BlinkApp：

| 原文件 | 新路径 | 行数 |
|--------|--------|------|
| `detail.py` | `widgets/detail.py` | 453 |
| `detail_edit.py` | `widgets/detail_edit.py` | 101 |
| `repo_list.py` | `widgets/repo_list.py` | 164 |
| `search.py` | `widgets/search.py` | 39 |

**依赖关系**（全部指向父级或同级，无循环）：

- `detail.py` → 父级 `actions.EditorInfo`，同级 `detail_edit.DetailEditMixin`
- `detail_edit.py` → 无 tui 依赖
- `repo_list.py` → 父级 `icons.*`
- `search.py` → 无 tui 依赖

**`widgets/__init__.py`** 重新导出关键控件：

```python
from blink.tui.widgets.detail import DetailPanel, _remote_to_https
from blink.tui.widgets.repo_list import RepoListControl
from blink.tui.widgets.search import SearchBar
```

## 影响范围

| 类型 | 操作 |
|------|------|
| 新建 | `src/loop/review/__init__.py` |
| 新建 | `src/tui/widgets/__init__.py` |
| 移动 | 6 个 loop review 文件 → `review/` 子目录（去掉 review_ 前缀） |
| 移动 | 4 个 tui 控件文件 → `widgets/` 子目录 |
| 修改 | `src/cli.py` — 导入路径 |
| 修改 | `src/tui/app.py`, `app_review.py`, `layout.py` — 导入路径 |
| 修改 | `tests/test_review_unit.py`, `test_review_integration.py`, `test_loop_integration.py` — 导入路径 |
| 修改 | `tests/test_detail_render.py`, `test_detail_edit.py`, `test_edit_routing.py`, `test_phase1/2/3.py`, `test_repo_list.py` — 导入路径 |

## 待定

- 是否也把 `cmd_run.py`, `cmd_edit.py`, `cmd_log.py`, `cmd_commit.py` 归入 `src/loop/cmds/` 子目录？（4 个 CLI 入口文件，每个都很小，可后续视情况处理）
- `src/tui/` 剩余 9 个文件是否进一步分组（如 `app/` 子目录）？当前 tui/app*.py + key_bindings + layout + status_bar 仍有 6 个与 BlinkApp 紧耦合的文件
