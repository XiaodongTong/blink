# P1 完善方案：列表展示优化 + 别名/标签/详情

## 背景

P0 MVP 已完成：扫描、搜索、列表展示、编辑器打开、复制路径。以下功能处于半成品或未实现状态，需要补齐。

---

## 一、列表展示优化

### 现状

`repo_list.py:44-47` 中每个仓库占一行，格式：
```
  name  —  /path/to/repo  (https://github.com/org/repo.git)
```
信息挤在一起，远程 URL 不实用且占用空间。

### 改为两行展示

```
  project-name          Tags: python, api
  /Users/xx/workingspace/project
```

- 第一行：项目名称（或别名）+ 标签
- 第二行：路径（灰色，缩进）
- 去掉远程 URL 展示
- 选中项高亮两行

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/blink/tui/repo_list.py` | `create_content` 方法改为每个 repo 渲染两行，标签拼接到第一行末尾 |
| `src/blink/tui/app.py` | 无需改动 |

### 渲染逻辑

```python
# 伪代码 - create_content 内部
for i, repo in enumerate(self.repos):
    display_name = repo.alias or repo.name
    tag_text = f"  [{', '.join(tag_names)}]" if tag_names else ""
    line1 = f"  {display_name}{tag_text}"
    line2 = f"  {repo.path}"
    style = "class:selected" if i == selected else ...
    lines.append([(style, line1), ("class:dim" or style, line2)])
```

`preferred_height` 返回 `len(self.repos) * 2` 或 `1`（空列表时）。

---

## 二、别名编辑

### 现状

`models.py` 有 `alias` 字段，`store.py` 数据库有 `alias` 列，但无 UI 设置。

### 实现

在详情面板或主列表中按 `e` 进入编辑模式，用 prompt-toolkit 的小输入框修改别名。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/blink/store.py` | 新增 `set_alias(repo_id, alias)` 方法 |
| `src/blink/tui/app.py` | 添加 `e` 快捷键，弹出内联输入框修改选中仓库的别名 |
| `src/blink/tui/repo_list.py` | 展示时优先使用 `alias`，alias 为空则用 `name` |

---

## 三、标签系统

### 现状

计划文档中有 `tags` 和 `repo_tags` 表设计，但代码中完全没有实现。

### 数据层

`store.py` 新增：

```sql
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_tags (
    repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (repo_id, tag_id)
);
```

新增方法：

| 方法 | 说明 |
|------|------|
| `get_tags_for_repo(repo_id)` | 获取仓库的所有标签 |
| `add_tag(repo_id, tag_name)` | 给仓库添加标签，不存在则自动创建 |
| `remove_tag(repo_id, tag_name)` | 移除仓库的某个标签 |
| `get_all_tags()` | 获取所有标签（用于搜索补全） |

### 模型层

`models.py` 的 `Repo` dataclass 新增 `tags: List[str]` 字段。

### 搜索

`store.py` 的 `search_repos` JOIN `repo_tags` + `tags` 表，将标签名纳入搜索范围。

### TUI 交互

- 主列表按 `t` 弹出标签管理弹窗（添加/删除标签）
- 搜索时标签名也能匹配
- 列表第一行末尾展示标签

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/blink/models.py` | `Repo` 新增 `tags: List[str]` |
| `src/blink/store.py` | 建表、CRUD、搜索扩展 |
| `src/blink/tui/app.py` | 添加 `t` 快捷键，弹出标签管理 |
| `src/blink/tui/repo_list.py` | 第一行末尾展示标签 |

---

## 四、详情面板

### 现状

`detail.py` 是空占位，`app.py:131` 中 `Enter` 键只显示 "Detail view coming in P1"。

### 实现

按 `Enter` 进入详情视图，展示完整信息并支持操作：

```
┌─ project-name ───────────────────────────────┐
│  别名: my-project                             │
│  路径: /Users/xx/workingspace/project         │
│  描述: A web API service                      │
│  远程:                                        │
│    origin → github.com/org/project.git        │
│    mirror → gitlab.com/org/project.git        │
│  标签: python, api, backend                   │
│  最后扫描: 2026-05-16                         │
├───────────────────────────────────────────────┤
│  v=VSCode  u=Cursor  a=Antigravity  y=复制    │
│  e=编辑别名/描述  t=管理标签  Esc=返回列表     │
└───────────────────────────────────────────────┘
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `src/blink/tui/detail.py` | 实现详情面板控件 |
| `src/blink/tui/app.py` | `Enter` 切换到详情视图，`Esc` 返回列表，详情视图内复用编辑器/复制快捷键 |

---

## 实施顺序

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | 列表两行展示（去掉远程 URL） | 无 |
| 2 | 标签数据层（建表 + CRUD） | 无 |
| 3 | 别名编辑（`e` 键 + store 方法） | 步骤 1 |
| 4 | 标签 TUI（`t` 键 + 列表展示标签） | 步骤 2 |
| 5 | 详情面板（`Enter` 进入完整视图） | 步骤 3, 4 |
| 6 | 搜索扩展（标签纳入搜索范围） | 步骤 2 |
| 7 | 更新 README + 测试 | 步骤 5, 6 |

---

## 验收标准

- [x] 列表每个仓库显示两行，不显示远程 URL
- [x] 展示名称优先使用别名，无别名则用目录名
- [x] 可以通过 `e` 键设置/修改别名
- [x] 可以通过 `t` 键给仓库添加/移除标签
- [x] 标签在列表第一行末尾展示
- [x] 搜索能匹配标签名
- [x] `Enter` 进入详情面板，展示完整信息
- [x] 详情面板支持编辑器打开、复制路径、编辑别名/标签
- [x] 所有新功能有对应测试
