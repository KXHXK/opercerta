# 幂等工单契约设计补充

## 决策状态

本设计补充的方案 1 与新工单初始状态 `created` 已在 2026-07-15 至 2026-07-16 的实施对话中确认；书面规格仍待用户复核。它用于补齐
`docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` Task 4 引用了但未完整定义的工单领域接口。
它服从 `docs/specs/2026-07-14-opercerta-design.md` 的审批边界、数据一致性和失败恢复语义，不修改冻结的产品范围。

## 问题与范围

现有计划已经规定稳定幂等键、canonical payload hash、授权校验、单事务写入和十路竞态验收，但没有精确定义以下 Python 契约：

- `WorkOrderCommand`
- `WorkOrderRecord`
- `WorkOrderWriteResult`
- `IdempotencyConflict`
- `WriteNotAuthorized`
- canonical JSON 的输入边界和快照语义

本补充只定义这些领域对象、纯函数、错误语义、Repository 后置条件和对应测试边界。HTTP/API、真实外部执行、具体库存或维护 payload、LangGraph 恢复节点和工单后续状态推进仍按各自任务完成。

## 方案比较

1. **独立工单模块 + 通用 JSON object payload（采用）**：在 `domain/work_orders.py` 集中命令、记录、结果和确定性指纹函数；当前不虚构尚未冻结的具体业务字段。
2. **立即定义库存与维护的强类型 payload union**：业务约束更强，但当前没有获批的完整字段集合，会提前扩大产品设计和测试范围。
3. **命令只接受调用方准备好的 canonical JSON 字符串**：内部实现简单，但把关键一致性责任推给调用方，接口难用且容易产生跨语言编码差异。

采用方案 1。它满足当前模拟工单的可靠性目标，同时保留以后在上层增加具体业务 payload schema 的空间。

## 领域契约

### JSON 值边界

`JsonValue` 只允许 JSON 可表达的值：字符串、有限数字、布尔值、`null`、数组，以及 key 为字符串的 object。明确拒绝 `NaN`、正负无穷、自定义对象、非字符串 key 和其他不能稳定编码为 JSON 的值。

Task 4 的 payload 顶层必须是 object。空 object 在该基础设施契约中是有效输入，因为当前没有获批的业务必填字段；具体业务校验以后由更靠近业务入口的契约承担，不能在可靠性内核里虚构。

### `WorkOrderCommand`

`WorkOrderCommand` 是禁止额外字段和字段重新赋值的 Pydantic 模型：

| 字段 | 类型与约束 | 含义 |
| --- | --- | --- |
| `operation_id` | `UUID`，必填 | 获得审批并准备创建工单的 OperCerta 操作 |
| `payload` | `dict[str, JsonValue]`，必填 | 当前模拟工单的 JSON object 参数 |

Pydantic 的冻结配置不保证嵌套 `dict` 和 `list` 深度不可变，因此 Repository 进入事务后必须立即对 payload 做一次 canonical serialization。待存储 payload 必须由 `json.loads(canonical_json)` 得到，SHA-256 也必须来自同一个 canonical JSON。一次调用内不能分别读取可变输入来生成 hash 和数据库 payload。

### `WorkOrderRecord`

`WorkOrderRecord` 是禁止额外字段和字段重新赋值的 Pydantic 模型：

| 字段 | 类型与约束 | 含义 |
| --- | --- | --- |
| `id` | `UUID` | 数据库工单标识 |
| `operation_id` | `UUID` | 关联的 OperCerta 操作 |
| `idempotency_key` | 非空字符串，最大 128 字符 | 系统派生的稳定幂等键 |
| `payload` | `dict[str, JsonValue]` | 首次写入时保存的 payload 快照 |
| `payload_hash` | 64 字符小写十六进制字符串 | canonical payload 的 SHA-256 |
| `status` | `Literal["created"]` | Task 4 新工单的固定初始状态 |
| `created_at` | 带时区 `datetime` | 数据库创建时间 |
| `updated_at` | 带时区 `datetime` | 数据库更新时间 |

Task 4 只产生 `created`，不提前定义或实现工单执行阶段的其他状态。Repository 从数据库构造记录时必须返回独立 payload 对象，不能泄漏数据库驱动内部的可变引用。

### `WorkOrderWriteResult`

`WorkOrderWriteResult` 是禁止额外字段和字段重新赋值的 Pydantic 模型：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `work_order` | `WorkOrderRecord` | 首次创建或安全重放得到的同一数据库工单 |
| `replayed` | `bool` | 首次创建为 `False`，相同请求重放为 `True` |

首次写入和安全重放必须返回相同的 `work_order.id`。

## 幂等键与 payload 指纹

### 稳定幂等键

`derive_idempotency_key(operation_id: UUID) -> str` 只由系统调用，不接受外部覆盖。固定格式为：

```text
work-order:v1:<canonical-lowercase-uuid>
```

其中 `v1` 固定当前语义，使未来契约升级不会静默改变旧键。同一个 operation 在 v1 中最多对应一个工单，这与现有 `work_orders.operation_id` 唯一约束一致。

### Canonical JSON

`canonical_payload_json(payload) -> str` 使用以下确定性规则：

```python
json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
)
```

这是 OperCerta 当前契约使用的确定性编码，不宣称完整实现 RFC 8785。object key 递归排序，不输出无意义空白，Unicode 直接编码为 UTF-8，且不做额外 Unicode normalization。

`hash_payload(payload) -> str` 对 canonical JSON 的 UTF-8 bytes 计算 SHA-256，并返回 64 字符小写十六进制摘要。object 字段顺序不同但 JSON 内容相同时摘要必须相同；内容变化时摘要必须不同。

## 错误契约

错误类型放在现有 `domain/errors.py`，延续稳定 `code` 和安全定位字段的风格：

| 错误 | 触发条件 | 稳定代码 | 副作用 |
| --- | --- | --- | --- |
| `OperationNotFound` | 加锁查询找不到 operation | `operation_not_found` | 整个事务零写入 |
| `IdempotencyConflict` | 已有工单的 payload hash 与当前请求不同 | `idempotency_conflict` | 不修改原工单，不新增审计 |
| `WriteNotAuthorized` | 首次创建时没有 approved 决定，或 operation 状态不允许 | `write_not_authorized` | 整个事务零写入 |

`OperationNotFound` 复用已有错误。新增错误使用以下构造契约：

- `IdempotencyConflict(operation_id: UUID, idempotency_key: str)` 继承 `RuntimeError`，保留两个同名属性；
- `WriteNotAuthorized(operation_id: UUID, status: str)` 继承 `RuntimeError`，保留两个同名属性。

错误消息、测试输出和审计事件均不得回显完整 payload 或任何凭据。

## 原子数据流

`WorkOrderRepository.create_or_get(command)` 必须在单个数据库事务中完成正常路径：

1. 立即规范化 payload，以同一快照生成待存储对象和 `payload_hash`。
2. 使用 `SELECT ... FOR UPDATE` 锁定目标 `operations` 行。
3. 行不存在时抛出 `OperationNotFound`，不写任何表。
4. 按系统派生的幂等键查询已有工单。
5. 已有工单且 hash 相同，返回原记录和 `replayed=True`，不新增审计事件。
6. 已有工单但 hash 不同，抛出 `IdempotencyConflict`，不修改任何记录。
7. 只有工单不存在时，才要求存在一条 `approved` 审批，并要求 operation 状态属于 `resuming`、`executing`、`verifying`。
8. 授权不满足时抛出 `WriteNotAuthorized`，不写工单或成功审计。
9. 插入一条状态为 `created` 的 `work_orders` 记录；首次写入的 `created_at` 与 `updated_at` 使用同一个带时区时间值。
10. 增加 `operations.next_audit_sequence`，并在同一事务追加一条 `work_order_created` 审计事件。
11. 提交后返回新记录和 `replayed=False`。

已有工单的安全重放在授权检查之前返回。这使 operation 即使已经推进到后续状态，重试仍能取回首次业务结果；授权规则只决定能否首次创建，不能让已创建结果变得不可重放。

审计事件 payload 固定为 `work_order_id`、`idempotency_key` 和 `payload_hash` 三个非敏感定位字段，不复制完整工单 payload。工单插入、审计序号和创建事件必须同事务提交或回滚，不能出现“有工单无审计”或“有审计无工单”。

现有两个唯一约束是最终碰撞防线：

- `uq_work_orders_operation_id`
- `uq_work_orders_idempotency_key`

正常并发由 operation 行锁串行化。若数据库仍返回唯一约束 `IntegrityError`，Repository 必须在回滚后重新读取既有工单，并应用相同 hash 比较：相同则安全重放，不同则冲突，不能把数据库异常直接泄漏为未分类错误。

## 并发与一致性语义

十个独立事务同时提交相同命令时：

- 恰好一个结果 `replayed=False`；
- 恰好九个结果 `replayed=True`；
- 十个结果拥有同一个工单 ID；
- 数据库只有一条该 operation 的工单；
- 只有一条 `work_order_created` 审计事件。

这代表工作流节点可以至少一次调用，但数据库业务写入达到有效一次（effectively-once）。本设计不把数据库边界之外的网络、消息队列或真实第三方执行描述为 exactly-once。

## TDD 与验收边界

实施顺序固定为：

1. **领域非法输入 RED**：缺失或非法 UUID、顶层非 object、非字符串 key、非 JSON 值、`NaN`、无穷和额外字段被拒绝。
2. **确定性纯函数 RED**：稳定幂等键、字典顺序无关 hash、内容变化 hash 变化。
3. **领域 GREEN**：只实现足够满足模型、纯函数和稳定错误的最小代码。
4. **Repository 授权 RED**：operation 不存在、缺少 approved 决定、状态不允许时均零写入。
5. **Repository 竞态 RED**：十个独立事务并发调用相同命令。
6. **Repository GREEN**：实现行锁、已有记录比较、授权、工单和审计同事务写入及唯一冲突翻译。
7. **重放与冲突测试**：相同命令返回原 ID 且无第二条创建审计；同 operation 改变 payload 抛出冲突；operation 状态前进后仍可重放原结果。
8. **门禁复验**：目标测试、数据库集成测试、完整 Pytest、Ruff 和 mypy 全部使用新鲜命令输出；竞态测试按既有计划独立重复 20 轮。

竞态测试不能预先填写耗时、成功率或其他效果指标。测试只断言可观察数据库事实；重复次数和结果只记录实际命令输出。

## 非目标

- 不在 Task 4 实现认证、RBAC、HTTP 端点或前端界面。
- 不调用真实库存、维护、付款或其他第三方系统。
- 不定义尚未冻结的具体业务 payload schema。
- 不实现工单执行器或 `created` 之后的状态推进。
- 不实现 LangGraph 重启恢复；它仍属于 Task 5。
- 不引入 Redis、消息队列、Docker 或其他项目代码。
- 不因本地幂等测试通过而打开 OperCerta 发布门禁。

## 自审结论

- 没有 TBD、TODO、占位字段或未选择的实现方案。
- 领域对象、错误构造、canonical JSON、事务顺序、审计内容和测试断言均为单一解释。
- `created` 初始状态、行锁顺序、授权状态集合及唯一冲突翻译与既有 Task 4 计划一致。
- 空 payload、可变嵌套对象快照和状态前进后的安全重放已明确，不需要实施时猜测。
- 范围只覆盖 OperCerta Task 4，不提前实施 Task 5、真实外部动作或其他项目。
