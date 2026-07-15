# OperCerta 开发日志初始化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 OperCerta 业务行为的前提下，建立简体中文为主的开发日志、决策记录、当前状态页和根目录文档索引，使自动压缩或新会话能从 Git 中恢复项目事实。

**Architecture:** `docs/development-log/` 保存过程事实和恢复入口；根目录 `DOCUMENT_INDEX.md` 保存所有重要文档的路径、用途、状态、最后核验 commit 和阅读优先级。每日过程可追加，决策记录保持稳定，当前状态只接受已验证结果。

**Tech Stack:** Markdown、Git、PowerShell、现有 pytest 结果。

## Global Constraints

- 仅记录 `D:\CODEX\agent-portfolio\opercerta`；不创建或启动其他项目。
- 以简体中文为主，保留 `Git commit`、`pytest`、`PostgreSQL`、`TDD` 等专业名词。
- 不写密码、token、API key、私有连接串、真实客户数据、旧公司材料或模型内部推理。
- 只记录新鲜命令输出或已提交文件可证明的事实；无证据时写“未记录”，不补写推测。
- 日志初始化不会改变业务代码、数据库、部署配置或 `OperCerta release gate`；发布门禁保持 `CLOSED`。

---

### Task 1: 创建日志说明、当前状态、首日日志与环境决策记录

**Files:**

- Create: `docs/development-log/README.md`
- Create: `docs/development-log/current-state.md`
- Create: `docs/development-log/daily/2026-07-15.md`
- Create: `docs/development-log/decisions/2026-07-15-windows-native-postgres.md`

**Interfaces:**

- Consumes: 已提交的日志设计 `docs/superpowers/specs/2026-07-15-development-log-design.md`、原生 PostgreSQL 设计/计划、Git 历史与当前 `pytest` 证据。
- Produces: 后续会话可按固定顺序阅读的日志入口；Task 2 的 `DOCUMENT_INDEX.md` 将引用这些已存在文件。

- [ ] **Step 1: 创建日志机制说明**

用 `apply_patch` 创建 `docs/development-log/README.md`，内容为：

```markdown
# OperCerta 开发日志

本目录是 OperCerta 的可复查工程记录，不是聊天记录备份。

## 阅读顺序

1. 根目录 `DOCUMENT_INDEX.md`
2. `current-state.md`
3. 最近一份 `daily/` 日志
4. 与当前任务相关的 `decisions/` 记录
5. `IMPLEMENTATION_HANDOFF.md`、实施计划和新鲜 Git/测试输出

## 文件职责

- `current-state.md`：只写已验证的当前事实、阻塞、下一步和发布门禁。
- `daily/YYYY-MM-DD.md`：按检查点追加当天的目标、观察、动作、证据、结果和下一步。
- `decisions/YYYY-MM-DD-主题.md`：记录架构、安全、环境、数据模型或发布门禁的稳定决策。

## 安全与真实性

不得写入密码、token、API key、私有连接串、真实客户数据、旧公司材料或完整敏感请求/响应。日志与测试、Git 或实际服务状态冲突时，以新鲜命令输出为准，并在当日日志记录更正。
```

- [ ] **Step 2: 创建已验证的当前状态页**

用 `apply_patch` 创建 `docs/development-log/current-state.md`，内容为：

```markdown
# OperCerta 当前状态

最后核验：2026-07-15，Git commit `a0564b1`。

## 当前阶段

可靠性内核的纯 Python 部分已实现；下一阶段是为审批竞态和幂等写入准备 Windows 原生 PostgreSQL 18.4 测试环境。

## 已验证事实

- 非法输入契约提交：`642fc2f`。
- 确定性状态恢复策略提交：`8bcf7c3`。
- 单元测试命令 `uv run pytest tests/unit -q` 于 2026-07-15 退出码 0，结果为 `19 passed`。
- Windows 原生 PostgreSQL 环境设计提交：`d506c8c`；本机端口固定为 `127.0.0.1:55432`，规格修正提交：`51c1583`。
- 原生 PostgreSQL 环境实施计划提交：`85c04d1`。
- 开发日志与文档索引设计提交：`a0564b1`。

## 当前阻塞与风险

- 本机 PostgreSQL 18.4 尚未安装和验证，审批竞态、幂等写入与重启恢复的集成测试尚不能开始。
- `IMPLEMENTATION_HANDOFF.md` 仍描述早期仓库状态；在原生 PostgreSQL 环境验证后按环境计划同步。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

执行 `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` 的 Task 1：确认 `.env.local` 忽略规则、记录环境基线并从官方渠道获取 PostgreSQL 18.4 Windows x86-64 安装器。

## 发布门禁

`OperCerta release gate: CLOSED`。本地环境通过不等于发布通过；Linux/Docker 验证和完整可靠性内核证据仍待完成。
```

- [ ] **Step 3: 创建当天首条过程日志**

用 `apply_patch` 创建 `docs/development-log/daily/2026-07-15.md`，内容为：

```markdown
# 2026-07-15 开发日志

## 17:30 Asia/Shanghai｜建立日志与上下文恢复机制

- 目标：把关键工程事实从对话上下文转为可提交、可复查的仓库记录。
- 观察：当前分支为 `main`；`git remote -v` 无输出；可靠性内核的纯 Python 单元测试已通过。
- 动作：确认开发日志采用当前状态、每日过程、决策记录三层结构，并增加根目录 `DOCUMENT_INDEX.md` 作为文档目录。
- 证据：日志设计提交 `7e3b353`；文档索引设计提交 `a0564b1`；`uv run pytest tests/unit -q` 输出 `19 passed`，退出码 0。
- 结果：日志机制设计已确认；日志文件初始化待本提交完成后验证。
- 风险与下一步：日志不替代测试证据；下一步创建根目录文档索引，然后执行 Windows 原生 PostgreSQL 环境计划。
```

- [ ] **Step 4: 创建 Windows 原生 PostgreSQL 决策记录**

用 `apply_patch` 创建 `docs/development-log/decisions/2026-07-15-windows-native-postgres.md`，内容为：

```markdown
# 决策：Windows 原生 PostgreSQL 18.4 作为当前集成测试数据库

## 背景

当前 Windows 工作站的 WSL2/虚拟化组件修复未成功，Docker Desktop 与 Docker Engine 不再作为本地开发前置条件。审批竞态、幂等写入和 LangGraph PostgreSQL checkpoint 仍需要真实 PostgreSQL 事务语义。

## 候选方案

1. Windows 原生 PostgreSQL 18.4。
2. 远程 Linux PostgreSQL。
3. WSL2 加 Docker Desktop。

## 采用方案

采用 Windows 原生 PostgreSQL 18.4，服务仅监听 `127.0.0.1:55432`，使用 SCRAM 认证，专用测试数据库为 `opercerta_test`。

## 理由

该方案能在当前工作站立即提供真实并发和事务验证，且不因未修复的 Windows 组件存储问题阻塞可靠性内核。远程服务会额外引入网络和凭据边界；WSL2 加 Docker 在当前机器上仍是已知阻塞。

## 影响与验证

本地 Task 3 的前置条件改为可连接的 PostgreSQL 实例。验证要求包括 PostgreSQL 18.4、`127.0.0.1:55432` 唯一监听、SCRAM、专用角色/数据库和真实 SQL 探针。Linux/Docker 一致性验证仍属于后续发布门禁。

## 回滚条件

若官方 PostgreSQL 18.4 Windows 安装器不能在当前 Windows 版本正常安装或无法满足回环/SCRAM 验证，停止环境安装并记录证据；不使用 SQLite 替代并发测试，也不宣称发布通过。

## 关联记录

- 设计：`docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md`，提交 `d506c8c`。
- 端口锁定：提交 `51c1583`。
- 实施计划：`docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md`，提交 `85c04d1`。
```

- [ ] **Step 5: 验证日志文本与提交初始化记录**

Run:

```powershell
git diff --check
rg -n "password|token|API key|postgresql\+psycopg://" docs/development-log
git status --short
git add docs/development-log
git commit -m "docs: initialize development log"
git status --short --branch
```

Expected: 文本中只出现安全规则里的敏感术语，不出现实际凭据或连接串；工作树在提交后保持干净。

### Task 2: 创建根目录文档索引并将日志纳入恢复入口

**Files:**

- Create: `DOCUMENT_INDEX.md`
- Modify: `docs/development-log/daily/2026-07-15.md`
- Modify: `docs/development-log/current-state.md`

**Interfaces:**

- Consumes: Task 1 创建并提交的日志文件，以及 `git rev-parse --short HEAD` 的实际输出。
- Produces: 根目录中文文档目录；后续会话可从一个文件定位当前设计、计划、日志、交接和证据。

- [ ] **Step 1: 获取日志初始化 commit**

```powershell
git rev-parse --short HEAD
```

Expected: 输出 Task 1 的 `docs: initialize development log` commit 短哈希。将该实际哈希写入本任务后续两个文件的“最后核验”字段。

- [ ] **Step 2: 创建根目录 `DOCUMENT_INDEX.md`**

用 `apply_patch` 创建 `DOCUMENT_INDEX.md`。文件使用中文表格，按以下目录项列出路径、用途、状态、最后核验 commit 和阅读优先级：

| 路径 | 用途 | 状态 | 最后核验 commit | 优先级 |
| --- | --- | --- | --- | --- |
| `README.md` | 项目概览与使用边界 | 需要随最小纵向闭环同步 | `a0564b1` | 2 |
| `IMPLEMENTATION_HANDOFF.md` | 会话交接与下一动作 | 需要在 PostgreSQL 环境验证后同步 | `a0564b1` | 3 |
| `docs/specs/2026-07-14-agent-project-naming-design.md` | 命名设计 | 已冻结基线 | `c7fa618` | 4 |
| `docs/specs/AI_Agent四项目总体设计规格.md` | 总体设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-agent-portfolio-design.md` | 组合设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-opercerta-design.md` | OperCerta 详细设计 | 已冻结基线 | `48d299c` | 4 |
| `docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md` | 本机数据库环境决策 | 已确认 | `51c1583` | 4 |
| `docs/superpowers/specs/2026-07-15-development-log-design.md` | 开发日志与上下文恢复规则 | 已确认 | `a0564b1` | 1 |
| `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` | 可靠性内核 TDD 计划 | Task 3 前置条件待环境计划同步 | `24ea72a` | 3 |
| `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` | PostgreSQL 环境计划 | 待执行 | `85c04d1` | 1 |
| `docs/superpowers/plans/2026-07-15-development-log-bootstrap.md` | 日志初始化计划 | 执行中 | 当前 `HEAD` | 1 |
| `docs/development-log/README.md` | 日志机制说明 | 已初始化 | Task 1 实际 commit | 1 |
| `docs/development-log/current-state.md` | 当前已验证状态 | 已初始化 | Task 1 实际 commit | 1 |
| `docs/development-log/daily/2026-07-15.md` | 当日过程记录 | 已初始化 | Task 1 实际 commit | 2 |
| `docs/development-log/decisions/2026-07-15-windows-native-postgres.md` | 环境架构决策 | 已初始化 | Task 1 实际 commit | 2 |

在表格后写入“计划创建”小节，说明 `docs/release-evidence/` 仅在实际验证产生证据后创建，当前不存在对应文件。再写入“维护规则”小节，要求新增、移动、废弃或改变重要文档状态时，在同一提交更新本索引；索引不复制正文、不保存秘密，并且上下文恢复时优先阅读本文件。

- [ ] **Step 3: 更新首日日志和当前状态中的初始化结果**

用 `apply_patch` 将 Task 1 的实际 commit 写入：

- `docs/development-log/daily/2026-07-15.md` 的结果改为“日志文件已初始化，根目录文档索引已创建并指向实际记录”。
- `docs/development-log/current-state.md` 的最后核验 commit 改为 Task 1 的实际 commit，并在已验证事实中增加“开发日志已初始化，根目录文档索引已创建”。

- [ ] **Step 4: 验证索引完整性并提交**

Run:

```powershell
$paths = Select-String -LiteralPath DOCUMENT_INDEX.md -Pattern '^\| `[^`]+` \|' -AllMatches |
    ForEach-Object { $_.Matches | ForEach-Object { $_.Groups[1].Value } } |
    Where-Object { $_ -match '^(README\.md|IMPLEMENTATION_HANDOFF\.md|docs/)' }
$missing = $paths | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing) { $missing; throw 'DOCUMENT_INDEX.md references a missing file.' }
git diff --check
git add DOCUMENT_INDEX.md docs/development-log
git commit -m "docs: add project document index"
git status --short --branch
```

Expected: `missing` 为空，Markdown 无空白错误，提交后工作树干净。`docs/release-evidence/` 只能出现在“计划创建”文字中，不能作为不存在文件的 Markdown 链接。

### Task 3: 记录日志机制完成边界并移交环境计划

**Files:**

- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-15.md`

**Interfaces:**

- Consumes: Task 2 的文档索引和最终 Git 状态。
- Produces: 下一会话可直接开始的最小环境任务说明。

- [ ] **Step 1: 追加日志初始化完成检查点**

用 `apply_patch` 在 `docs/development-log/daily/2026-07-15.md` 末尾追加：

```markdown
## 日志初始化完成｜移交 PostgreSQL 环境计划

- 目标：确认文档索引与三层日志可作为后续上下文恢复入口。
- 观察：根目录 `DOCUMENT_INDEX.md` 已列出当前设计、计划、日志和计划创建的证据目录。
- 动作：完成索引路径校验、Git 提交和当前状态更新。
- 证据：`git diff --check` 退出码 0；索引路径校验无缺失；相关提交见 `git log --oneline`。
- 结果：日志机制已可用；业务实现尚未开始新的数据库代码。
- 风险与下一步：继续执行 Windows 原生 PostgreSQL 环境计划 Task 1；不因日志完成改变发布门禁。
```

- [ ] **Step 2: 运行最终文档门禁并提交移交记录**

```powershell
git diff --check
rg -n "postgresql\+psycopg://|BEGIN [A-Z ]*PRIVATE KEY|api[_-]?key\s*=|token\s*=" DOCUMENT_INDEX.md docs/development-log
git add docs/development-log
git commit -m "docs: hand off logging to environment setup"
git status --short --branch
```

Expected: 敏感内容搜索无匹配，Markdown 检查通过，工作树干净；下一任务仍是 PostgreSQL 环境计划，`OperCerta release gate` 保持 `CLOSED`。

## Plan Self-Review

- **Spec coverage:** Task 1 建立三层日志；Task 2 创建根目录文档索引并列出设计、计划、日志、交接和未来证据；Task 3 写入可恢复的移交边界。
- **Truthfulness:** 当前状态、首日日志和决策记录只使用已执行测试、已有 commit 和已批准环境设计；不存在的发布证据仅作为计划创建条件记录。
- **Secret safety:** 所有验证命令只查找敏感模式；计划没有密码、token 或连接串值。
- **Scope:** 没有运行时依赖、业务代码、数据库或部署变更；环境计划与发布门禁不被绕过。
