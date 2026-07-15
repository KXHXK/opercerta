# 审批领域契约设计补充

## 决策状态

本设计补充已在 2026-07-15 的实施对话中确认，用于补齐
`docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` Task 3 引用了但未定义的审批领域接口。
它服从 `docs/specs/2026-07-14-opercerta-design.md` 的状态机、数据一致性和安全边界，不修改冻结的产品范围。

## 问题与范围

详细设计已经规定审批人、决定、原因、时间、单次决定、原子落库和重复提交冲突，但现有代码及实施计划没有明确以下 Python 契约：

- `ApprovalDecision`
- `ApprovalCommand`
- `ApprovalRecord`
- `ApprovalAlreadyDecided`
- `OperationNotFound`

本补充只定义这些领域对象、错误语义和对应测试边界。数据库迁移、Repository 事务实现、API/RBAC、LangGraph 恢复节点和工单幂等逻辑仍按各自实施任务完成。

## 方案比较

1. **独立审批模块 + 不可变 Pydantic 模型（采用）**：在 `domain/approvals.py` 集中审批枚举、命令和记录；输入输出均有运行时校验，可直接跨 API、Repository 和工作流边界复用。
2. **继续扩展 `domain/contracts.py`**：文件数量较少，但会把操作请求与审批生命周期混在一起，后续测试和依赖边界会逐渐模糊。
3. **全部使用冻结 dataclass**：内部对象简单，但无法直接承担不可信 API 输入的字段校验，后续需要再维护一组重复的传输模型。

采用方案 1。它与当前 `OperationRequest` 的 Pydantic v2 风格一致，同时让审批模块保持单一职责。

## 领域契约

### `ApprovalDecision`

`ApprovalDecision` 是 `StrEnum`，只允许两个稳定值：

- `APPROVED = "approved"`
- `REJECTED = "rejected"`

未知值必须在进入 Repository 前被 Pydantic 拒绝，不允许 Repository 猜测、降级或替换决定。

### `ApprovalCommand`

`ApprovalCommand` 是冻结且禁止额外字段的 Pydantic 模型：

| 字段 | 类型与约束 | 含义 |
| --- | --- | --- |
| `operation_id` | `UUID`，必填 | 被审批的 OperCerta 操作 |
| `approver_id` | 去除首尾空白后长度 `1..128` 的字符串 | 已由上层认证得到的审批人主体标识 |
| `decision` | `ApprovalDecision` | 批准或拒绝 |
| `reason` | 去除首尾空白后长度 `1..1000` 的字符串 | 必填审批理由，用于业务事实与审计 |

领域模型只保存审批人标识，不在此处实现 JWT 或角色校验。API 层以后必须从认证上下文构造 `approver_id`，不能信任请求体自报身份。

### `ApprovalRecord`

`ApprovalRecord` 是冻结且禁止额外字段的 Pydantic 模型，包含 `id: UUID`、`ApprovalCommand` 的四个业务字段和 `created_at: datetime`。`created_at` 必须带时区，由 Repository 在事务内生成；记录 ID 和时间不得由外部审批请求提供。

Repository 成功返回的记录必须与同一事务写入 `approvals` 的事实一致，不能在提交前返回推测结果。

## 错误契约

错误类型放在 `domain/errors.py`，延续现有错误对象携带稳定 `code` 的方式。`OperationNotFound` 继承 `LookupError`，`ApprovalAlreadyDecided` 继承 `RuntimeError`；两者的构造参数均为 `operation_id: UUID`：

| 错误 | 触发条件 | 稳定代码 | 副作用 |
| --- | --- | --- | --- |
| `OperationNotFound` | 加锁查询找不到 `operation_id` | `operation_not_found` | 整个事务零写入 |
| `ApprovalAlreadyDecided` | 已有审批记录，或操作已不处于 `awaiting_approval` | `approval_already_decided` | 整个事务零写入 |

两个错误都保留 `operation_id` 供安全日志和后续 API 映射使用。当前 Task 3 不提前实现 HTTP 状态映射；后续 API 层将不存在映射为 404、审批冲突映射为 409。

## 原子数据流

`ApprovalRepository.submit_once(command)` 必须在单个 `engine.begin()` 事务中完成：

1. 使用 `SELECT ... FOR UPDATE` 锁定目标 `operations` 行。
2. 行不存在时抛出 `OperationNotFound`，不写任何表。
3. 已有决定或当前状态不是 `awaiting_approval` 时抛出 `ApprovalAlreadyDecided`，不写任何表。
4. 插入唯一的 `approvals` 记录。
5. 将操作状态更新为 `resuming`，并原子增加审计序号。
6. 追加一个 `approval_recorded` 审计事件，再提交事务并返回 `ApprovalRecord`。

批准和拒绝都先进入 `resuming`。这是详细设计中的故障恢复中间态：决定落库后即使进程崩溃，恢复节点仍可读取原决定，再分别进入 `executing` 或 `rejected`。Task 3 不把拒绝直接写成终态。

`approvals.operation_id` 的唯一约束是最终碰撞防线；行锁负责让同一操作的并发请求按顺序观察已提交的决定。异常必须回滚审批、状态和审计三类写入，不允许部分成功。

## TDD 与验收边界

实施按以下顺序进行：

1. 领域契约 RED：非法决定、空审批人、空原因、额外字段和无时区记录被拒绝。
2. 领域契约 GREEN：只实现足以满足上述契约的模型和稳定错误。
3. PostgreSQL 迁移：建立既定业务表、唯一约束和 `langgraph` Schema。
4. 审批竞态 RED：十个独立事务同时提交五个批准与五个拒绝。
5. Repository GREEN：恰好一个调用返回 `ApprovalRecord`，其余九个返回 `ApprovalAlreadyDecided`；数据库中恰好一条审批、一条 `approval_recorded` 事件，操作状态为 `resuming`。
6. 重复运行竞态测试并执行完整 `pytest`、Ruff 和 mypy 门禁。

竞态测试不得断言批准或拒绝中的哪一方获胜，只能断言唯一胜者及其数据库事实一致。通过次数、耗时和其他指标只记录实际命令输出，不预先填写。

## 非目标

- 不在 Task 3 实现认证、RBAC、HTTP 端点或前端按钮。
- 不在 Task 3 实现审批过期计时器或 LangGraph 恢复路由。
- 不修改工单幂等语义；它仍属于 Task 4。
- 不引入 Redis、Docker 或其他项目代码。
- 不因本地竞态测试通过而打开 OperCerta 发布门禁。

## 自审结论

- 没有 TBD、TODO 或未选择的接口方案。
- `resuming` 语义与详细设计的状态机和崩溃恢复说明一致。
- 字段、错误代码、事务后置条件和测试断言均为单一解释。
- 范围仅覆盖 OperCerta 审批契约与 Task 3 的直接前置条件。
