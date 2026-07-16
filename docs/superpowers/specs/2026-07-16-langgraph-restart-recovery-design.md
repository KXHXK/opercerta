# LangGraph 四点重启恢复契约设计

## 决策状态

本设计的架构、数据流、错误语义和测试边界已在 2026-07-16 的实施对话中分段确认；本文件仍需用户完成书面规格复核。它补齐 `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` Task 5 的精确契约，不修改冻结的产品范围。

Task 4 已证明审批原子性和工单写入 effectively-once。Task 5 只证明单 Worker 进程重启后，LangGraph 控制流可以结合 PostgreSQL 业务事实安全恢复；它不声称多 Worker 调度、跨区域容灾或节点 exactly-once。

## 目标与范围

Task 5 建立一个最小、JSON-only、可持久化的 LangGraph 流程，并演示以下四个重启点：

1. operation 业务行已保存、首个图检查点尚未写入；
2. 图已在审批处中断、审批决定尚不存在；
3. 审批决定已经落库、图尚未恢复；
4. 工单已经落库、对应图检查点尚未写入。

每个场景必须使用已释放的图 A/checkpointer A 和新建的图 B/checkpointer B 模拟进程重启。恢复不调用模型、不重新生成风险或计划，也不绕过 Task 3 审批和 Task 4 幂等边界。

## 已确认方案

### 业务快照复用现有 JSONB

不新增数据库迁移。Task 5 把恢复所需的最小冻结业务快照保存在现有 `operations.request_payload` JSONB 中：

```json
{
  "schema_version": 1,
  "request": {},
  "risk": {},
  "plan": {},
  "work_order_payload": {}
}
```

四个内容字段都是 JSON object。当前不虚构具体库存、维修或维护字段；业务入口以后可在更靠近业务边界的位置增加强类型 schema，但不能静默改变 `schema_version=1` 的恢复语义。

### 批准与拒绝都必须恢复

`ApprovalRepository` 对批准和拒绝都会原子保存决定并把 operation 推进到 `resuming`。恢复逻辑必须读取已保存的真实决定：

- `approved`：继续执行幂等工单、验证并进入 `completed`；
- `rejected`：不调用工单 Repository，进入 `rejected`，工单数保持零。

只测试批准不足以证明系统读取了原决定，因此两条路径均属于 Task 5 验收范围。

### 独立 OperationStateRepository

新增 `OperationStateRepository`，集中承担 operation 状态、审计序号和状态审计事件的同事务迁移。LangGraph 节点和 `RecoveryCoordinator` 不直接执行 SQL；现有 `ApprovalRepository` 与 `WorkOrderRepository` 不扩展成通用状态仓储。

## 总体架构

```text
PostgreSQL public 业务事实
        ↓
OperationStateRepository.load_recovery_view
        ↓
RecoveryCoordinator ←→ LangGraph + langgraph Schema 检查点
        ↓
ApprovalRepository / WorkOrderRepository / OperationStateRepository
```

- `public.operations`、`approvals`、`work_orders` 和 `audit_events` 是业务真相。
- `langgraph` Schema 只保存控制流检查点。
- 两者不共享事务；恢复必须同时读取业务事实和图快照。
- 检查点落后于业务事实是预期故障模型，不允许用检查点覆盖已提交的审批或工单。
- operation UUID 的规范小写字符串同时用作业务 ID 和 LangGraph `thread_id`；`operations.thread_id` 必须等于该字符串。

## 领域与状态契约

### `OperationSnapshot`

新增禁止额外字段和字段重赋值的 Pydantic 模型：

| 字段 | 类型与约束 | 语义 |
| --- | --- | --- |
| `schema_version` | `Literal[1]` | 当前恢复快照版本 |
| `request` | `dict[str, JsonValue]` | 已持久化原始请求事实 |
| `risk` | `dict[str, JsonValue]` | 已持久化确定性风险事实 |
| `plan` | `dict[str, JsonValue]` | 已持久化的一步动作计划 |
| `work_order_payload` | `dict[str, JsonValue]` | 传给 Task 4 工单命令的完整快照 |

每个字段允许空 object，但必须递归满足 Task 4 已冻结的 JSON 边界：只允许字符串、有限数字、布尔、`null`、数组和字符串 key 的 object；拒绝非字符串 key、自定义对象、元组、`NaN` 和正负无穷。

从数据库加载后必须通过 `OperationSnapshot.model_validate()`；缺字段、错误版本或非法内容不能由默认值、模型调用或猜测补齐。

### `ReliabilityState`

LangGraph `TypedDict` 只允许 JSON 可序列化字段：

- `operation_id: str`；
- `snapshot: dict[str, JsonValue]`；
- `approval: dict[str, JsonValue] | None`，只含 `approval_id` 与 `decision`；
- `work_order: dict[str, JsonValue] | None`，只含 `work_order_id` 与 `payload_hash`；
- `replayed: bool`；
- `recovery_action: str | None`。

状态中禁止 Engine、Connection、Repository、Exception、Secret、客户端对象和完整审计记录。依赖通过图节点闭包注入，不进入检查点。

### `RecoveryView`

`OperationStateRepository.load_recovery_view(operation_id)` 返回不可变读模型，至少包含：

- `operation_id`、`thread_id`、`status`；
- 已校验的 `OperationSnapshot`；
- 可选审批定位字段：`approval_id`、`decision`；
- 可选工单定位字段：`work_order_id`、`payload_hash`。

不得把审批原因、完整工单 payload 或数据库驱动内部映射泄漏进图状态。`thread_id != str(operation_id)`、审批字段只存在一半或工单字段只存在一半都属于 `RecoveryStateConflict`。

### `OperationTransitionResult`

每次状态方法返回不可变结果：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `operation_id` | `UUID` | 目标 operation |
| `status` | `OperationStatus` | 调用后的数据库状态 |
| `changed` | `bool` | 本次是否真实迁移并追加审计 |
| `audit_sequence` | `int | None` | 新事件序号；安全重复为 `None` |

## OperationStateRepository 契约

Repository 提供以下明确方法，不暴露通用任意状态写接口：

| 方法 | 允许来源 | 目标 | 事件 | 安全审计 payload |
| --- | --- | --- | --- | --- |
| `mark_awaiting_approval(operation_id)` | `received` | `awaiting_approval` | `approval_requested` | `snapshot_version` |
| `mark_executing(operation_id, approval_id)` | `resuming` | `executing` | `execution_started` | `approval_id` |
| `mark_verifying(operation_id, work_order_id)` | `executing` | `verifying` | `verification_started` | `work_order_id` |
| `mark_completed(operation_id, work_order_id)` | `verifying` | `completed` | `operation_completed` | `work_order_id` |
| `mark_rejected(operation_id, approval_id)` | `resuming` | `rejected` | `operation_rejected` | `approval_id` |

共同事务顺序：

1. `SELECT ... FOR UPDATE` 锁定 operation；
2. 不存在时抛出既有 `OperationNotFound`；
3. 当前状态等于目标状态时，确认对应状态事件已经存在且定位字段一致，然后返回 `changed=False`，不增加审计序号；
4. 当前状态不属于允许来源时抛出 `OperationTransitionConflict`，零写入；
5. 增加 `next_audit_sequence`、更新 operation 状态与时间；
6. 使用同一时间和序号插入状态事件；
7. 提交后返回 `changed=True` 和新审计序号。

若数据库显示目标状态但缺少对应事件，或事件定位字段与当前调用不一致，不能把它当安全重复，必须抛出 `RecoveryStateConflict`。

## Checkpointer 生命周期与安全

`checkpoints.py` 负责：

- 从 `SecretStr` 数据库 URL 派生不回显的 checkpointer DSN；
- 把 SQLAlchemy 驱动形式转换为 Psycopg 可接受的 PostgreSQL DSN；
- 设置连接 `search_path=langgraph`，使 saver 表只建立在独立 Schema；
- 通过 `AsyncPostgresSaver.from_conn_string()` 管理连接；
- 在数据库 bootstrap 或集成测试 session setup 中显式调用一次 `await checkpointer.setup()`。

禁止每个请求重复执行 `setup()`，也禁止让 checkpointer 与业务 SQLAlchemy Connection 共享事务。

锁定版本 `langgraph-checkpoint-postgres==3.1.0` 的本地 API 已核验：`from_conn_string(conn_string, pipeline=False, serde=None)` 返回 async context manager，`setup()` 必须由调用方显式执行。

`.env.example` 和测试进程设置 `LANGGRAPH_STRICT_MSGPACK=true`。该环境变量必须在导入/构造默认 `JsonPlusSerializer` 前生效；本地 `langgraph-checkpoint==4.1.1` 源码确认它会启用内建安全类型 allowlist。即使启用严格模式，Task 5 仍只保存 plain JSON 数据，不增加自定义反序列化 allowlist。

## 最小图拓扑

```text
START
  → prepare_approval
  → request_approval (interrupt)
      ├─ approved → mark_executing → execute_work_order
      │           → mark_verifying → verify_work_order
      │           → mark_completed → END
      └─ rejected → mark_rejected → END
```

节点约束：

- `prepare_approval` 调用 `mark_awaiting_approval`；
- `request_approval` 在 `interrupt()` 前不写审批、不写工单；
- 恢复值必须包含已保存的 `approval_id` 和 `decision`；
- `mark_executing` 在工单调用前原子进入 `executing`；
- `execute_work_order` 只用冻结的 `work_order_payload` 构造 Task 4 `WorkOrderCommand`；
- `mark_verifying` 保存工单定位字段后进入 `verifying`；
- `verify_work_order` 回读数据库并验证 operation ID、工单 ID 和 payload hash；
- `mark_completed` 和 `mark_rejected` 通过 Repository 写终态与审计；
- 节点不调用模型、MCP、Redis 或真实外部工具。

## RecoveryCoordinator 算法

`RecoveryCoordinator.recover(operation_id: UUID) -> RecoveryAction` 既执行恢复动作，也返回本次选择的 `RecoveryAction` 供日志与测试断言。

1. 通过 `load_recovery_view` 读取并校验业务事实；
2. 以 `thread_id=str(operation_id)` 调用已编译图的 state snapshot 接口；
3. 无已保存快照时分类为 `CheckpointPhase.MISSING`；
4. snapshot task 中存在 interrupt 时分类为 `CheckpointPhase.INTERRUPTED`；
5. 其余已存在快照分类为 `CheckpointPhase.RUNNABLE`；
6. 用业务状态、checkpoint phase、是否有审批和是否有工单构造现有 `RecoveryFacts`；
7. 调用现有 `choose_recovery_action()`；
8. 只执行对应动作：
   - `REBUILD_FROM_BUSINESS_FACTS`：从 `OperationSnapshot` 构造初始 JSON state 并运行至 interrupt；
   - `KEEP_WAITING`：不调用图，不写业务表；
   - `RESUME_DECISION`：使用已保存 `approval_id` 与 `decision` 构造 `Command(resume=...)`；
   - `REPLAY_IDEMPOTENT_EXECUTION`、`VERIFY_EXISTING_WORK_ORDER`、`CONTINUE_CHECKPOINT`：从现有 thread checkpoint 继续，允许节点安全重放；
   - `NO_OP`：不调用图，不新增审计。

若快照中的 operation ID 与业务 ID 不同、审批决定不是 `approved/rejected`、终态仍有待执行 checkpoint，或组合无法安全解释，抛出 `RecoveryStateConflict`，不得选择方便路径继续。

## 四点重启预期

| 重启点 | 业务事实 | 图事实 | 预期动作与结果 |
| --- | --- | --- | --- |
| 首个检查点前 | operation + 有效快照，无审批/工单 | missing | `rebuild_from_business_facts`，重新到审批 interrupt |
| 等待审批 | `awaiting_approval`，无审批/工单 | interrupted | `keep_waiting`，零自动审批、零工单 |
| 审批落库后 | `resuming` + 一条决定 | interrupted | `resume_decision`；批准完成一个工单，拒绝进入 `rejected` 且零工单 |
| 工单落库后 | `resuming` + approved + 一个工单 | 仍为旧 interrupt | `resume_decision`，执行节点调用 `create_or_get` 得到原 ID 和 `replayed=True`，最终完成 |

最后一个场景故意让业务表领先于图检查点，以证明 Task 4 幂等边界而不是图本身防止重复工单。

## 错误契约

新增错误放在现有 `domain/errors.py`：

- `InvalidOperationSnapshot(operation_id: UUID, reason: str)`：稳定 code 为 `invalid_operation_snapshot`，保留 operation ID 与安全 reason；
- `OperationTransitionConflict(operation_id: UUID, current_status: str, target_status: str)`：稳定 code 为 `operation_transition_conflict`；
- `RecoveryStateConflict(operation_id: UUID, reason: str)`：稳定 code 为 `recovery_state_conflict`。

错误消息、日志、图状态和审计均不得包含完整业务快照、数据库 URL、密码或异常对象。checkpointer 连接失败不翻译为成功业务状态；调用方收到基础设施异常，业务表保持最后已提交事实，下一次恢复重新分类。

## TDD 与验收顺序

实施顺序固定为：

1. `OperationSnapshot` 非法输入 RED；
2. 快照模型与稳定错误 GREEN；
3. `OperationStateRepository` 合法迁移、同目标重复、冲突迁移和同事务审计 RED/GREEN；
4. checkpointer 独立 Schema、严格序列化、setup 和快照读写 RED/GREEN；
5. 图在任何工单写入前 interrupt 的 RED/GREEN；
6. 无崩溃的批准与拒绝路径；
7. 四点重启矩阵，其中审批落库后包含批准和拒绝两个 case；
8. 使用完全释放的 A/B 图和 checkpointer 实例证明进程等价重启；
9. 重启矩阵以独立测试进程重复 10 轮；
10. 完整 Pytest、Ruff lint、Ruff format check、mypy 和凭据扫描。

验收必须由数据库事实断言：

- 等待审批时零自动审批、零工单；
- 拒绝恢复时零工单；
- 批准恢复只有一条审批和一条工单；
- 写后恢复返回原工单 ID，不产生第二条 `work_order_created`；
- `completed` 或 `rejected` 各只有一条匹配终态审计；
- checkpointer 失败不改变原业务决定；
- 重复次数、测试数和耗时只记录实际命令输出，不预填效果指标。

## 非目标

- 不实现 FastAPI、SSE、前端、JWT 或 RBAC；
- 不调用真实模型、MCP、库存、维修或付款系统；
- 不实现 Redis、Docker、云部署、多 Worker 调度、租约或心跳；
- 不新增业务数据库列或 `0002` 迁移；
- 不扩展未冻结的具体业务 payload schema；
- 不提前实施 Task 6 的完整可靠性内核证据；
- 不启动 ForenTrail 或其他项目；
- 不因 Task 5 本地通过而打开发布门禁。

## 自审结论

- 业务快照位置、版本和 JSON 边界只有一个解释；
- 批准、拒绝和四个重启点均有明确业务结果；
- Repository 方法、允许来源状态、目标状态、审计事件和重复语义一一对应；
- LangGraph 检查点与业务事务明确分离，不宣称 exactly-once；
- 严格序列化开关已按本地锁定版本源码核验，不依赖未经验证的隐式行为；
- 没有未选择方案、占位字段或跨 Task 范围；
- Task 5 完成后发布门禁仍为 `CLOSED`。
