# Plan 7: AI 辅助代码 Review 工作流

## 背景与目标

作为若干项目的主程，需要频繁 review 同事的分支代码，并作出三种结论：

| 结论 | 描述 |
|------|------|
| ✅ **APPROVE** | 没有问题，可以直接合并 |
| ⚠️ **APPROVE_WITH_NOTES** | 有问题但无伤大雅，本次可合并，问题列出供后续改进 |
| ❌ **REQUEST_CHANGES** | 有严重问题，不能合并，需修改后重新提交 |

本方案将 AI review 能力集成进 blink 的 TUI 选项目 + `blink run` 命令体系，形成完整的交互流程。

---

## 核心流程设计

```
TUI 中选中目标仓库
        │
        ▼
[Shift+V] 触发 Code Review 流程
        │
        ├─ 1. 后台获取最近 5 个分支（按 committer date 排序，排除 main/master 和当前分支）
        │      status bar 显示「正在获取分支列表...」
        │
        ▼
Status bar 进入分支选择模式
        │
        ├─ 2. ←→ 选择分支，Enter 确认，Esc 取消
        │      显示格式：Review [2/5]: ▸ feature/auth-improvements
        │
        ▼
blink review <branch> [--against <base>]
        │
        ├─ 3. 创建临时 review 分支 (review/<branch>-<date>)
        │      = main + 同事分支 merge 结果
        │
        ├─ 4. 收集上下文
        │      ├─ git diff main..<branch>（纯变更视角）
        │      ├─ 临时分支整体代码视角
        │      └─ ./docs/blink/review-rules.md（项目规则，如有）
        │
        ├─ 5. 调用 claude 进行分析（structured output）
        │
        ▼
输出结构化 Review 报告
        │
        ├─ verdict: APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES
        ├─ summary: 总体评价
        ├─ issues[]: 问题列表（severity / file / line / description / suggestion）
        ├─ required_changes[]: 必改项 + 具体修改方案（REQUEST_CHANGES 时必填）
        └─ notes[]: 后续改进建议（APPROVE_WITH_NOTES 时填写）

        │
        ▼
报告保存至 <project>/docs/blink/code-review/<branch>-<date>.md
（该路径已加入项目 .gitignore，由主程手动决定是否 git 追踪）
        │
        ▼
TUI 状态栏显示结论，可 Shift+L 在 IDE 中打开报告文件
```

---

## 上下文收集策略（三层）

### 层 1：Git Diff 视角
```bash
git diff main..<colleague-branch>        # 纯变更 diff
git log main..<colleague-branch> --oneline  # 提交历史
git diff --stat main..<colleague-branch> # 变更文件统计
```
优点：快速、精准，只看改动。适合大多数 review 场景。

### 层 2：临时 Review 分支（整体视角）
```bash
git checkout -b review/<branch>-<date> main
git merge --no-ff <colleague-branch>
```
优点：Claude 可以在这个分支上真正运行、读取文件、理解整体上下文，而不只看 diff。
特性：review 结束后自动删除（或标记为可删除），不污染主干。

### 层 3：项目 Review 规则文件
位置：`<project-root>/docs/blink/review-rules.md`

内容示例：
```markdown
# Review Rules for <ProjectName>

## 必查项
- 所有数据库查询必须使用参数化 SQL，禁止字符串拼接
- API 响应不得暴露 stack trace 给前端

## 历史教训
- 2024-03: PR#42 引入了 N+1 查询问题，此后数据库相关改动需重点关注
- 2024-07: 配置项变更未同步文档，导致部署失败

## 代码风格
- 函数超过 50 行需要拆分
- 所有 public 方法需要 docstring
```

加载逻辑：review 时自动检测 `./docs/blink/review-rules.md`，若存在则作为 `<rules>` 块注入 prompt。

---

## 新增模块设计

### `src/blink/loop/cmd_review.py`（新文件）

```python
"""blink review — AI-assisted code review for colleague branches."""
```

主要功能：
- `handle(args)` — CLI 入口，解析参数，驱动整个 review 流程
- `setup_review_branch(dir_path, branch, base)` — 创建临时 review 分支
- `cleanup_review_branch(dir_path, branch_name)` — review 结束后删除临时分支
- `collect_context(dir_path, branch, base)` — 收集三层上下文
- `build_review_prompt(diff, log, rules)` — 组装 Claude prompt
- `parse_verdict(output)` — 解析 Claude 输出中的结论标记
- `save_report(dir_path, branch, verdict, content)` — 保存报告到 `<project>/docs/blink/code-review/`
- `ensure_review_dir(dir_path)` — 确保 `docs/blink/code-review/` 目录存在（自动创建）

### `src/blink/loop/git_ops.py`（扩展）

新增函数：
- `create_review_branch(dir_path, colleague_branch, base_branch)` — 创建临时合并分支
- `delete_branch(dir_path, branch_name)` — 安全删除分支（带 -D 强制选项）
- `branch_exists(dir_path, name)` — 已存在，直接复用
- `get_diff_stat(dir_path, base, branch)` — 返回变更文件统计
- `get_recent_branches(dir_path, limit=5)` — 返回按最近提交日期排序的本地分支（排除 main/master 和当前分支）

---

## Claude Prompt 设计

```
你是一位经验丰富的代码审查专家。请对以下代码变更进行全面 review。

<rules>
{project_rules}
</rules>

<commit_log>
{commit_log}
</commit_log>

<diff_stat>
{diff_stat}
</diff_stat>

<diff>
{full_diff}
</diff>

请严格按照以下格式输出 review 结果：

## 总体评价
[一段话描述整体代码质量和主要印象]

## 结论
VERDICT: [APPROVE|APPROVE_WITH_NOTES|REQUEST_CHANGES]

## 问题列表
（如无问题则写"无"）
- [CRITICAL|MAJOR|MINOR] `文件名:行号` — 问题描述
  建议：具体修改建议（含代码示例，越具体越好）

## ❌ 必改项（仅 VERDICT 为 REQUEST_CHANGES 时填写，否则省略此节）
> 以下内容将作为退回意见直接发给同事，请写得清晰、可操作。

### 必改项 1：[简短标题]
**文件**：`文件路径:行号`
**问题**：详细描述问题是什么，为什么必须改
**修改方案**：
```
// 改前
原始代码片段

// 改后
修改后的代码片段
```

### 必改项 2：[简短标题]
... （重复上述结构）

## ⚠️ 后续改进建议（仅 APPROVE_WITH_NOTES 时填写，否则省略此节）
> 本次可以合并，但建议同事后续跟进。
- 建议描述（含文件和行号）

## Review 完毕
<promise>COMPLETE</promise>
```

**严重程度定义：**
- `CRITICAL`：安全漏洞、数据丢失风险、功能性错误 → 触发 REQUEST_CHANGES
- `MAJOR`：性能问题、逻辑缺陷、接口设计问题 → 可能触发 APPROVE_WITH_NOTES 或 REQUEST_CHANGES
- `MINOR`：代码风格、命名、注释 → 触发 APPROVE_WITH_NOTES

**Verdict 判定规则：**
- 有任何 CRITICAL → REQUEST_CHANGES（**必须**填写「必改项」节，每项附改前/改后代码示例）
- 有 MAJOR 无 CRITICAL → APPROVE_WITH_NOTES（填写「后续改进建议」节）
- 只有 MINOR 或无问题 → APPROVE

> **重要**：REQUEST_CHANGES 时，「必改项」节是核心产出——要让同事看完就知道改哪里、改成什么样，不需要再来回沟通。



---

## CLI 接口

### `blink review` 新子命令

```bash
# 基本用法：review 同事分支（自动检测主分支）
blink review feature/colleague-feature

# 指定 base 分支
blink review feature/colleague-feature --against develop

# 不创建临时分支，只看 diff（更快，上下文较少）
blink review feature/colleague-feature --diff-only

# 查看已有 review 报告列表
blink review --list

# 指定项目目录
blink review feature/colleague-feature --dir ~/projects/my-project
```

### `tasks.yaml` 任务模式（批量 review）

```yaml
tasks:
  - name: Review colleague/feature-auth
    dir: ~/projects/my-project
    prompt_file: ./prompts/review-auth-branch.md
    branch: false          # 不创建新分支（review 分支由 cmd_review 自己管）
    review: false
    use: claude
    review_branch: feature/auth-improvements   # 新字段：待 review 的分支
    review_against: main                        # 新字段：对比的 base 分支
```

---

## TUI 集成

### 新快捷键：`Shift+V`（Review）

在 `src/blink/tui/app.py` 中：

1. **触发方式**：`Shift+V` — 在列表或详情焦点下均可触发
2. **交互流程**：
   ```
   Shift+V
     → 后台线程获取最近 5 个分支（按 committer date 排序）
     → status bar 显示「正在获取分支列表...」
     → 获取完成后进入分支选择模式：
       显示格式：Review [1/5]: ▸ feature/auth  ←→:选择  Enter:确认  Esc:取消
     → 用户 ←→ 选择分支，Enter 确认
     → 后台线程执行 review 流程
     → status bar 显示「🔍 正在 review...」
     → 完成后显示结论徽标：「✅ APPROVE」/ 「⚠️ 有注意事项」/ 「❌ 需要修改」
     → Shift+L 可打开报告文件
   ```

3. **Detail Panel 新增区域**（可选，后续迭代）：
   ```
   ── Reviews ─────────────────────────────────
     feature/auth  ✅ APPROVE          2026-05-20
     feature/pay   ❌ REQUEST_CHANGES  2026-05-18
   ```

### Footer 快捷键更新

| 按键 | 功能 |
|------|------|
| `Shift+V` | AI Code Review（新增） |

---

## 文件结构

```
<project-root>/
└── docs/
    └── blink/
        ├── review-rules.md              ← 项目 review 规则（可 git 追踪）
        └── code-review/                 ← review 报告输出目录（已加入 .gitignore）
            ├── feature-auth-20260520.md
            └── feature-pay-20260518.md
```

> `docs/blink/code-review/` 已加入项目 `.gitignore`，由主程决定是否手动 `git add` 某份报告留档（如需归档评审记录时）。

`~/.blink/loop/` 无需额外存储 review 报告，保持简洁：
```
~/.blink/loop/
├── tasks.yaml
├── state.json
├── logs/
└── archive/
```

---

## 报告格式示例

### 示例 A：APPROVE_WITH_NOTES

文件名：`docs/blink/code-review/feature-auth-20260520.md`

````markdown
# Code Review Report

**项目**: my-project  
**分支**: feature/auth-improvements  
**对比**: main  
**时间**: 2026-05-20 14:32  
**结论**: ⚠️ APPROVE_WITH_NOTES  

---

## 总体评价
整体实现思路清晰，认证逻辑正确。主要问题是 refresh_token 并发场景有竞态风险，以及两处 SQL 查询可以优化。建议本次合并，问题作为技术债务后续跟进。

## 问题列表
- [MAJOR] `src/auth/token.py:87` — refresh_token 在并发场景下可能产生竞态条件  
  建议：使用数据库乐观锁或 Redis 原子操作

- [MINOR] `src/auth/models.py:23` — User 模型缺少 created_at 字段的索引  
  建议：添加 `db.Index('ix_user_created_at', 'created_at')`

## ⚠️ 后续改进建议
- `src/auth/token.py:87`：refresh_token 并发问题建议在下个 sprint 单独处理
- 考虑统一 error response 格式，目前 auth 模块与其他模块格式不一致
````

---

### 示例 B：REQUEST_CHANGES

文件名：`docs/blink/code-review/feature-payment-20260521.md`

````markdown
# Code Review Report

**项目**: my-project  
**分支**: feature/payment-v2  
**对比**: main  
**时间**: 2026-05-21 10:15  
**结论**: ❌ REQUEST_CHANGES  

---

## 总体评价
支付流程的主逻辑基本正确，但存在两个严重问题：金额字段未做精度保护（浮点运算）以及支付回调接口缺少签名验证。**需要修改后重新提交。**

## 问题列表
- [CRITICAL] `src/payment/order.py:134` — 金额使用 float 运算，存在精度丢失风险  
  建议：改用 `decimal.Decimal`

- [CRITICAL] `src/payment/callback.py:56` — 支付回调未验证第三方签名，可伪造支付成功  
  建议：接入支付宝/微信签名验证 SDK

## ❌ 必改项

### 必改项 1：金额计算精度问题
**文件**：`src/payment/order.py:134`  
**问题**：`total = price * quantity` 使用 float 运算，当金额为 0.1、0.2 等场景时会产生精度误差，可能导致实际扣款金额与展示金额不一致，属于资金安全问题。  
**修改方案**：
```python
# 改前
total = price * quantity

# 改后
from decimal import Decimal
total = Decimal(str(price)) * Decimal(str(quantity))
# 或统一在模型层使用 Decimal 字段，避免每处都转换
```

### 必改项 2：支付回调签名验证缺失
**文件**：`src/payment/callback.py:56`  
**问题**：回调接口直接信任请求参数中的支付状态，任何人可以伪造 POST 请求使订单状态变为已支付。  
**修改方案**：
```python
# 改前
def handle_callback(request):
    order_id = request.POST['order_id']
    status = request.POST['status']
    update_order(order_id, status)  # 直接更新，无验证

# 改后
def handle_callback(request):
    if not verify_signature(request.POST, PAYMENT_SECRET_KEY):
        return HttpResponse(status=400)
    order_id = request.POST['order_id']
    status = request.POST['status']
    update_order(order_id, status)
```
参考：支付宝签名验证文档 https://opendocs.alipay.com/open/204/105301
````



---

## 实施路线图

### Phase 1：核心 CLI（最小可用版本）
- [ ] `src/blink/loop/cmd_review.py` — 实现基础 review 流程
- [ ] `src/blink/loop/git_ops.py` — 新增 `create_review_branch` / `delete_branch` / `get_diff_stat`
- [ ] `src/blink/cli.py` — 注册 `review` 子命令
- [ ] `~/.blink/loop/reviews/` — 目录初始化（在 `ensure_tloop_home` 中添加）
- [ ] `src/blink/loop/config.py` — 添加 `REVIEWS_DIR` 常量

### Phase 2：TUI 集成
- [ ] `src/blink/tui/app.py` — 添加 `Shift+V` 快捷键和输入流程
- [ ] `src/blink/tui/detail.py` — 添加 Reviews 区域（可选）
- [ ] `CLAUDE.md` / `README.md` — 文档同步更新

### Phase 3：规则体系完善
- [ ] 为每个项目创建 `docs/blink/review-rules.md` 模板
- [ ] `blink review --init-rules` — 生成规则文件初始模板
- [ ] 支持 `tasks.yaml` 中批量配置 review 任务

---

## 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| TUI 分支选择方式 | ←→ 选择最近 5 个分支 | 免输入，一键选择；分支名通常较长，手动输入体验差 |
| review 分支清理时机 | review 完成后立即删除 | 避免临时分支积累；如需复现可重新运行 |
| verdict 由谁决定 | Claude 给出建议，人工最终确认 | AI 作为决策辅助，主程保留最终权力 |
| MAJOR 问题的 verdict | 默认 APPROVE_WITH_NOTES | 保守原则，CRITICAL 才强制阻塞 |
| 大 diff 处理 | 超过 100KB diff 自动截断，只看 diff_stat + 重点文件 | 避免超出 context window |
| 报告存储位置 | `<project>/docs/blink/code-review/`（项目内） | 与项目代码同源，便于主程按需手动归档；已加入 `.gitignore` 由主程控制 |
| 规则文件位置 | `<project>/docs/blink/review-rules.md` | 与现有 `docs/blink/constitution.md` 保持一致 |
| REQUEST_CHANGES 必改项 | 每项必须附改前/改后代码示例 | 让同事看完即可动手，减少沟通来回 |
