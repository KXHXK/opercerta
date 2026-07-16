# OperCerta LangGraph Restart Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用严格 TDD 实现 JSON-only LangGraph、独立 PostgreSQL checkpointer、operation 原子状态迁移和四点跨进程等价重启恢复，同时证明批准不重复、拒绝不丢失、工单不重复。

**Architecture:** PostgreSQL `public` Schema 保存不可被 checkpoint 覆盖的业务真相，`langgraph` Schema 只保存控制流；`OperationStateRepository` 负责业务状态与审计的原子迁移，`RecoveryCoordinator` 同时读取业务事实和图快照后复用现有确定性恢复矩阵。图中的依赖通过闭包注入，checkpoint 只包含 plain JSON 数据。

**Tech Stack:** Python 3.12、Pydantic 2.13.4、SQLAlchemy 2.0.51 Core async、Psycopg 3.3.4、PostgreSQL 18.4、LangGraph 1.2.9、langgraph-checkpoint-postgres 3.1.0、langgraph-checkpoint 4.1.1、Pytest 9.1.1、pytest-asyncio 1.4.0、Ruff 0.15.21、mypy 2.3.0。

## Global Constraints

- 只修改 `D:\CODEX\agent-portfolio\opercerta`；不复用旧公司源码、数据、规则、截图、模型或品牌材料。
- 只实施可靠性内核 Task 5；不实现 API/SSE、认证、前端、真实模型、MCP、Redis、Docker、云部署、多 Worker 或其他项目。
- 不新增业务列或 `0002` 迁移；恢复快照固定复用 `operations.request_payload`，版本固定为 `schema_version=1`。
- operation UUID 的规范小写字符串同时作为 `operations.thread_id` 和 LangGraph `thread_id`；不一致必须分类为 `RecoveryStateConflict`。
- `public` 业务事实优先于 `langgraph` checkpoint；checkpoint 落后是预期故障模型，不能覆盖已经提交的审批、拒绝或工单。
- LangGraph state 只允许 plain JSON；禁止 Engine、Connection、Repository、Secret、Exception、客户端和完整审计记录进入 checkpoint。
- `.env.example` 与测试进程必须在默认 serializer 导入或构造前设置 `LANGGRAPH_STRICT_MSGPACK=true`；不增加自定义反序列化 allowlist。
- `checkpointer.setup()` 只在数据库 bootstrap 或测试进程 session setup 执行一次；业务事务与 checkpointer 事务不得共享 Connection。
- 四个重启点都必须释放 graph A/checkpointer A，再新建 graph B/checkpointer B；审批落库后必须分别覆盖批准与拒绝。
- 测试、重复次数、耗时和通过数只记录真实输出；不得把本地重复结果解释成生产成功率或 exactly-once。
- Task 5 完成后发布门禁仍为 `CLOSED`；Task 6 完成前不得声称可靠性内核验证完成。

## File Responsibility Map

| Path | Responsibility |
| --- | --- |
| `src/opercerta/domain/json_values.py` | 共享递归 JSON 边界校验，避免 Task 4 与 Task 5 产生不同语义 |
| `src/opercerta/domain/operation_state.py` | `OperationSnapshot`、审批恢复值、`RecoveryView`、`OperationTransitionResult` |
| `src/opercerta/domain/errors.py` | 三类稳定且不泄露 payload/凭据的 Task 5 错误 |
| `src/opercerta/domain/work_orders.py` | 改用共享 JSON 校验器，保持 Task 4 外部行为不变 |
| `src/opercerta/infrastructure/db/operation_state_repository.py` | 恢复视图读取、operation 行锁、状态与审计原子迁移、安全重复检查 |
| `src/opercerta/infrastructure/checkpoints.py` | Secret-safe DSN、独立 `langgraph` search path、严格 serializer 前置检查、saver 生命周期 |
| `src/opercerta/workflow/reliability_graph.py` | JSON-only 最小图、interrupt、批准/拒绝路由、幂等工单与验证节点 |
| `src/opercerta/workflow/recovery_coordinator.py` | checkpoint 分类、业务事实校验、现有恢复矩阵选择和对应图动作 |
| `tests/unit/domain/test_operation_state.py` | 快照非法输入、冻结模型、稳定错误的 RED/GREEN |
| `tests/integration/db/test_operation_state_repository.py` | 合法迁移、安全重复、冲突、审计原子性与恢复视图数据库断言 |
| `tests/integration/workflow/test_checkpoints.py` | checkpointer Schema、setup、严格 JSON checkpoint 和 DSN 安全边界 |
| `tests/integration/workflow/test_reliability_graph.py` | 首次 interrupt、无崩溃批准与拒绝路径 |
| `tests/integration/workflow/test_restart_recovery.py` | 四点 A/B 重启矩阵、批准/拒绝、工单安全重放和数据库最终事实 |
| `tests/integration/conftest.py` | 测试进程严格 serializer 开关与一次性 checkpointer setup |
| `.env.example` | 记录严格 msgpack 的非秘密环境配置 |

---

### Task 1: Frozen recovery snapshot and shared JSON boundary

**Files:**
- Create: `src/opercerta/domain/json_values.py`
- Create: `src/opercerta/domain/operation_state.py`
- Create: `tests/unit/domain/test_operation_state.py`
- Modify: `src/opercerta/domain/work_orders.py`
- Modify: `src/opercerta/domain/errors.py`

**Interfaces:**
- Produces: `require_json_object(value: object, field_name: str) -> object`.
- Produces: `OperationSnapshot`, `ApprovalResume`, `RecoveryView`, `OperationTransitionResult`.
- Produces: `InvalidOperationSnapshot`, `OperationTransitionConflict`, `RecoveryStateConflict`.
- Preserves: Task 4 `WorkOrderCommand` JSON rejection and canonical hash behavior.

- [ ] **Step 1: RED — add snapshot and error contract tests**

Create `tests/unit/domain/test_operation_state.py` with tests that:

```python
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import ApprovalResume, OperationSnapshot

OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")


def valid_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        "request": {"summary": "synthetic"},
        "risk": {"level": "high"},
        "plan": {"step": "create_work_order"},
        "work_order_payload": {"quantity": 4},
    }


def test_snapshot_accepts_complete_plain_json() -> None:
    snapshot = OperationSnapshot.model_validate(valid_snapshot())
    assert snapshot.schema_version == 1
    assert snapshot.work_order_payload == {"quantity": 4}


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": 2},
        {"request": []},
        {"risk": {1: "value"}},
        {"plan": {"steps": ("one",)}},
        {"work_order_payload": {"value": object()}},
        {"work_order_payload": {"value": float("nan")}},
        {"extra": True},
    ],
)
def test_snapshot_rejects_invalid_or_non_json_input(mutation: dict[str, object]) -> None:
    data = valid_snapshot()
    data.update(mutation)
    with pytest.raises(ValidationError):
        OperationSnapshot.model_validate(data)


@pytest.mark.parametrize("missing", ["request", "risk", "plan", "work_order_payload"])
def test_snapshot_never_fabricates_missing_fields(missing: str) -> None:
    data = valid_snapshot()
    data.pop(missing)
    with pytest.raises(ValidationError):
        OperationSnapshot.model_validate(data)


def test_snapshot_and_resume_fields_cannot_be_reassigned() -> None:
    snapshot = OperationSnapshot.model_validate(valid_snapshot())
    with pytest.raises(ValidationError):
        snapshot.schema_version = 1
    resume = ApprovalResume(approval_id=OPERATION_ID, decision=ApprovalDecision.APPROVED)
    with pytest.raises(ValidationError):
        resume.decision = ApprovalDecision.REJECTED


def test_errors_keep_only_stable_safe_fields() -> None:
    invalid = InvalidOperationSnapshot(OPERATION_ID, "request_payload_failed_validation")
    transition = OperationTransitionConflict(OPERATION_ID, "received", "completed")
    conflict = RecoveryStateConflict(OPERATION_ID, "thread_id_mismatch")
    assert (invalid.code, str(invalid)) == ("invalid_operation_snapshot", invalid.code)
    assert invalid.reason == "request_payload_failed_validation"
    assert transition.code == "operation_transition_conflict"
    assert transition.current_status == "received"
    assert transition.target_status == "completed"
    assert conflict.code == "recovery_state_conflict"
    assert conflict.reason == "thread_id_mismatch"
```

- [ ] **Step 2: Run focused RED**

```powershell
uv run pytest tests/unit/domain/test_operation_state.py -q
```

Expected RED: collection fails because `opercerta.domain.operation_state` and the three new errors do not exist.

- [ ] **Step 3: GREEN — centralize JSON validation and add domain models**

Create `src/opercerta/domain/json_values.py`:

```python
import math


def require_json_object(value: object, field_name: str) -> object:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    _require_json_value(value, field_name)
    return value


def _require_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _require_json_value(item, field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} object keys must be strings")
            _require_json_value(item, field_name)
        return
    raise ValueError(f"{field_name} must contain only JSON values")
```

Create `src/opercerta/domain/operation_state.py`:

```python
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationInfo, field_validator

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.json_values import require_json_object
from opercerta.domain.recovery import OperationStatus


class OperationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    request: dict[str, JsonValue]
    risk: dict[str, JsonValue]
    plan: dict[str, JsonValue]
    work_order_payload: dict[str, JsonValue]

    @field_validator("request", "risk", "plan", "work_order_payload", mode="before")
    @classmethod
    def require_plain_json_object(cls, value: object, info: ValidationInfo) -> object:
        return require_json_object(value, info.field_name)


class ApprovalResume(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: UUID
    decision: ApprovalDecision


@dataclass(frozen=True, slots=True)
class RecoveryView:
    operation_id: UUID
    thread_id: str
    status: OperationStatus
    snapshot: OperationSnapshot
    approval_id: UUID | None
    decision: ApprovalDecision | None
    work_order_id: UUID | None
    payload_hash: str | None


@dataclass(frozen=True, slots=True)
class OperationTransitionResult:
    operation_id: UUID
    status: OperationStatus
    changed: bool
    audit_sequence: int | None
```

Append to `src/opercerta/domain/errors.py`:

```python
class InvalidOperationSnapshot(ValueError):
    code = "invalid_operation_snapshot"

    def __init__(self, operation_id: UUID, reason: str) -> None:
        self.operation_id = operation_id
        self.reason = reason
        super().__init__(self.code)


class OperationTransitionConflict(RuntimeError):
    code = "operation_transition_conflict"

    def __init__(self, operation_id: UUID, current_status: str, target_status: str) -> None:
        self.operation_id = operation_id
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(self.code)


class RecoveryStateConflict(RuntimeError):
    code = "recovery_state_conflict"

    def __init__(self, operation_id: UUID, reason: str) -> None:
        self.operation_id = operation_id
        self.reason = reason
        super().__init__(self.code)
```

In `src/opercerta/domain/work_orders.py`, remove `math` and the private recursive validator, import `require_json_object`, and make the existing validator return:

```text
return require_json_object(value, "payload")
```

- [ ] **Step 4: Verify GREEN and Task 4 JSON regression**

```powershell
uv run pytest tests/unit/domain/test_operation_state.py tests/unit/domain/test_work_orders.py -q
uv run pytest tests/unit -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Expected: all commands exit `0`; record only observed counts.

- [ ] **Step 5: Commit the domain boundary**

```powershell
git add src/opercerta/domain/errors.py src/opercerta/domain/json_values.py src/opercerta/domain/operation_state.py src/opercerta/domain/work_orders.py tests/unit/domain/test_operation_state.py
git diff --cached --check
git commit -m "feat: define restart recovery state"
```

---

### Task 2: Atomic operation state repository

**Files:**
- Create: `src/opercerta/infrastructure/db/operation_state_repository.py`
- Create: `tests/integration/db/test_operation_state_repository.py`

**Interfaces:**
- Consumes: `AsyncEngine`, existing `operations`, `approvals`, `work_orders`, `audit_events`.
- Produces: `load_recovery_view(operation_id: UUID) -> RecoveryView`.
- Produces: five explicit transition methods returning `OperationTransitionResult`.
- Invariant: operation status, sequence increment and state audit event commit in one PostgreSQL transaction.

- [ ] **Step 1: RED — write database fact tests**

Create integration tests with a `seed_operation()` helper that always stores the complete `schema_version=1` snapshot and canonical `thread_id`. The tests must execute these exact assertions:

```python
@pytest.mark.asyncio
async def test_load_recovery_view_validates_snapshot_and_locators(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    state_repository = OperationStateRepository(engine)
    await state_repository.mark_awaiting_approval(operation_id)
    approval_id = await seed_approval(engine, operation_id, decision="approved")
    result = await WorkOrderRepository(engine).create_or_get(
        WorkOrderCommand(operation_id=operation_id, payload={"quantity": 4})
    )
    view = await OperationStateRepository(engine).load_recovery_view(operation_id)
    assert view.operation_id == operation_id
    assert view.thread_id == str(operation_id)
    assert view.status is OperationStatus.RESUMING
    assert view.snapshot.schema_version == 1
    assert view.approval_id == approval_id
    assert view.decision is ApprovalDecision.APPROVED
    assert view.work_order_id == result.work_order.id
    assert view.payload_hash == result.work_order.payload_hash


@pytest.mark.asyncio
async def test_invalid_snapshot_and_thread_id_are_classified(engine: AsyncEngine) -> None:
    invalid_id = await seed_operation(engine, status="received", snapshot={"schema_version": 2})
    with pytest.raises(InvalidOperationSnapshot, match="invalid_operation_snapshot"):
        await OperationStateRepository(engine).load_recovery_view(invalid_id)
    mismatch_id = await seed_operation(engine, status="received", thread_id="wrong-thread")
    with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
        await OperationStateRepository(engine).load_recovery_view(mismatch_id)


@pytest.mark.asyncio
async def test_full_transition_chain_is_atomic_and_ordered(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    repository = OperationStateRepository(engine)
    awaiting = await repository.mark_awaiting_approval(operation_id)
    approval_id = await seed_approval(engine, operation_id, decision="approved")
    executing = await repository.mark_executing(operation_id, approval_id)
    order = await WorkOrderRepository(engine).create_or_get(
        WorkOrderCommand(operation_id=operation_id, payload={"quantity": 4})
    )
    verifying = await repository.mark_verifying(operation_id, order.work_order.id)
    completed = await repository.mark_completed(operation_id, order.work_order.id)
    assert [awaiting.status, executing.status, verifying.status, completed.status] == [
        OperationStatus.AWAITING_APPROVAL,
        OperationStatus.EXECUTING,
        OperationStatus.VERIFYING,
        OperationStatus.COMPLETED,
    ]
    rows = await audit_facts(engine, operation_id)
    assert [row["event_type"] for row in rows] == [
        "approval_requested",
        "approval_recorded",
        "execution_started",
        "work_order_created",
        "verification_started",
        "operation_completed",
    ]
    assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_same_target_is_safe_only_with_matching_event(engine: AsyncEngine) -> None:
    operation_id = await seed_operation(engine, status="received")
    repository = OperationStateRepository(engine)
    first = await repository.mark_awaiting_approval(operation_id)
    second = await repository.mark_awaiting_approval(operation_id)
    assert first.changed is True and first.audit_sequence == 1
    assert second.changed is False and second.audit_sequence is None
    assert len(await audit_facts(engine, operation_id)) == 1


@pytest.mark.asyncio
async def test_wrong_origin_and_incomplete_target_write_nothing(engine: AsyncEngine) -> None:
    wrong_id = await seed_operation(engine, status="planning")
    with pytest.raises(OperationTransitionConflict, match="operation_transition_conflict"):
        await OperationStateRepository(engine).mark_awaiting_approval(wrong_id)
    incomplete_id = await seed_operation(engine, status="awaiting_approval")
    with pytest.raises(RecoveryStateConflict, match="recovery_state_conflict"):
        await OperationStateRepository(engine).mark_awaiting_approval(incomplete_id)
    assert await audit_facts(engine, wrong_id) == []
    assert await audit_facts(engine, incomplete_id) == []
```

`seed_approval()` in this file must use `ApprovalRepository.submit_once()` rather than inserting an un-audited decision; cleanup deletes the operation so foreign keys cascade.

- [ ] **Step 2: Run repository RED**

```powershell
uv run pytest tests/integration/db/test_operation_state_repository.py -q
```

Expected RED: collection fails because `operation_state_repository` does not exist.

- [ ] **Step 3: GREEN — implement validated view loading and explicit transitions**

Create `src/opercerta/infrastructure/db/operation_state_repository.py` with:

```python
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.approvals import ApprovalDecision
from opercerta.domain.errors import (
    InvalidOperationSnapshot,
    OperationNotFound,
    OperationTransitionConflict,
    RecoveryStateConflict,
)
from opercerta.domain.operation_state import (
    OperationSnapshot,
    OperationTransitionResult,
    RecoveryView,
)
from opercerta.domain.recovery import OperationStatus
from opercerta.infrastructure.db.schema import approvals, audit_events, operations, work_orders


class OperationStateRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load_recovery_view(self, operation_id: UUID) -> RecoveryView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(
                            operations.c.id,
                            operations.c.thread_id,
                            operations.c.status,
                            operations.c.request_payload,
                            approvals.c.id.label("approval_id"),
                            approvals.c.decision,
                            work_orders.c.id.label("work_order_id"),
                            work_orders.c.payload_hash,
                        )
                        .select_from(
                            operations.outerjoin(
                                approvals, approvals.c.operation_id == operations.c.id
                            ).outerjoin(
                                work_orders, work_orders.c.operation_id == operations.c.id
                            )
                        )
                        .where(operations.c.id == operation_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OperationNotFound(operation_id)
        return self._validated_view(operation_id, row)

    async def mark_awaiting_approval(self, operation_id: UUID) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RECEIVED}),
            target=OperationStatus.AWAITING_APPROVAL,
            event_type="approval_requested",
            payload={"snapshot_version": 1},
        )

    async def mark_executing(
        self, operation_id: UUID, approval_id: UUID
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.EXECUTING,
            event_type="execution_started",
            payload={"approval_id": str(approval_id)},
        )

    async def mark_verifying(
        self, operation_id: UUID, work_order_id: UUID
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.EXECUTING}),
            target=OperationStatus.VERIFYING,
            event_type="verification_started",
            payload={"work_order_id": str(work_order_id)},
        )

    async def mark_completed(
        self, operation_id: UUID, work_order_id: UUID
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.VERIFYING}),
            target=OperationStatus.COMPLETED,
            event_type="operation_completed",
            payload={"work_order_id": str(work_order_id)},
        )

    async def mark_rejected(
        self, operation_id: UUID, approval_id: UUID
    ) -> OperationTransitionResult:
        return await self._transition(
            operation_id,
            allowed=frozenset({OperationStatus.RESUMING}),
            target=OperationStatus.REJECTED,
            event_type="operation_rejected",
            payload={"approval_id": str(approval_id)},
        )

    async def _transition(
        self,
        operation_id: UUID,
        *,
        allowed: frozenset[OperationStatus],
        target: OperationStatus,
        event_type: str,
        payload: dict[str, object],
    ) -> OperationTransitionResult:
        async with self._engine.begin() as connection:
            operation = await self._locked_operation(connection, operation_id)
            current_raw = str(operation["status"])
            try:
                current = OperationStatus(current_raw)
            except ValueError:
                raise RecoveryStateConflict(operation_id, "unknown_operation_status") from None
            if current is target:
                await self._require_matching_event(
                    connection, operation_id, event_type=event_type, payload=payload
                )
                return OperationTransitionResult(operation_id, target, False, None)
            if current not in allowed:
                raise OperationTransitionConflict(operation_id, current.value, target.value)
            sequence = int(operation["next_audit_sequence"]) + 1
            changed_at = datetime.now(UTC)
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    status=target.value,
                    next_audit_sequence=sequence,
                    updated_at=changed_at,
                )
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=payload,
                    created_at=changed_at,
                )
            )
        return OperationTransitionResult(operation_id, target, True, sequence)

    async def _locked_operation(
        self, connection: AsyncConnection, operation_id: UUID
    ) -> RowMapping:
        row = (
            (
                await connection.execute(
                    select(operations).where(operations.c.id == operation_id).with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise OperationNotFound(operation_id)
        return row

    async def _require_matching_event(
        self,
        connection: AsyncConnection,
        operation_id: UUID,
        *,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        rows = (
            (
                await connection.execute(
                    select(audit_events.c.payload).where(
                        audit_events.c.operation_id == operation_id,
                        audit_events.c.event_type == event_type,
                    )
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 1 or cast(dict[str, object], rows[0]["payload"]) != payload:
            raise RecoveryStateConflict(operation_id, "target_state_event_mismatch")

    def _validated_view(self, operation_id: UUID, row: RowMapping) -> RecoveryView:
        if str(row["thread_id"]) != str(operation_id):
            raise RecoveryStateConflict(operation_id, "thread_id_mismatch")
        try:
            status = OperationStatus(str(row["status"]))
        except ValueError:
            raise RecoveryStateConflict(operation_id, "unknown_operation_status") from None
        try:
            snapshot = OperationSnapshot.model_validate(row["request_payload"])
        except ValidationError:
            raise InvalidOperationSnapshot(
                operation_id, "request_payload_failed_validation"
            ) from None
        approval_id = cast(UUID | None, row["approval_id"])
        decision_raw = cast(str | None, row["decision"])
        if (approval_id is None) != (decision_raw is None):
            raise RecoveryStateConflict(operation_id, "partial_approval_locator")
        decision: ApprovalDecision | None = None
        if decision_raw is not None:
            try:
                decision = ApprovalDecision(decision_raw)
            except ValueError:
                raise RecoveryStateConflict(operation_id, "invalid_approval_decision") from None
        work_order_id = cast(UUID | None, row["work_order_id"])
        payload_hash = cast(str | None, row["payload_hash"])
        if (work_order_id is None) != (payload_hash is None):
            raise RecoveryStateConflict(operation_id, "partial_work_order_locator")
        return RecoveryView(
            operation_id=operation_id,
            thread_id=str(row["thread_id"]),
            status=status,
            snapshot=snapshot,
            approval_id=approval_id,
            decision=decision,
            work_order_id=work_order_id,
            payload_hash=payload_hash,
        )
```

- [ ] **Step 4: Verify repository GREEN and migration regression**

```powershell
uv run pytest tests/integration/db/test_operation_state_repository.py -q
uv run pytest tests/integration/db -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the atomic state boundary**

```powershell
git add src/opercerta/infrastructure/db/operation_state_repository.py tests/integration/db/test_operation_state_repository.py
git diff --cached --check
git commit -m "feat: make operation transitions atomic"
```

---

### Task 3: Strict PostgreSQL checkpointer lifecycle

**Files:**
- Create: `src/opercerta/infrastructure/checkpoints.py`
- Create: `tests/integration/workflow/test_checkpoints.py`
- Modify: `tests/integration/conftest.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `checkpoint_dsn(database_url: SecretStr) -> SecretStr`.
- Produces: `open_checkpointer(database_url: SecretStr, setup: bool = False)` async context manager.
- Produces: session-scoped `checkpoint_database_url: SecretStr` after exactly one test-process setup.

- [ ] **Step 1: RED — test DSN secrecy, Schema isolation and JSON round-trip**

Create tests that assert:

```python
def test_checkpoint_dsn_is_secret_and_targets_langgraph_schema() -> None:
    source = SecretStr("postgresql+psycopg://user:password@127.0.0.1:55432/database")
    result = checkpoint_dsn(source)
    assert str(result) == "**********"
    raw = result.get_secret_value()
    assert raw.startswith("postgresql://")
    assert "search_path%3Dlanggraph" in raw


@pytest.mark.asyncio
async def test_setup_creates_saver_tables_only_in_langgraph(
    engine: AsyncEngine, checkpoint_database_url: SecretStr
) -> None:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_name IN ('checkpoint_migrations', 'checkpoints', "
                    "'checkpoint_blobs', 'checkpoint_writes')"
                )
            )
        ).all()
    assert {schema for schema, _ in rows} == {"langgraph"}
    assert {name for _, name in rows} == {
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    }


@pytest.mark.asyncio
async def test_plain_json_checkpoint_survives_new_saver_instance(
    checkpoint_database_url: SecretStr,
) -> None:
    thread_id = str(uuid4())
    async with open_checkpointer(checkpoint_database_url) as saver_a:
        graph_a = build_probe_graph(saver_a)
        await graph_a.ainvoke(
            {"operation_id": thread_id, "payload": {"items": [1, True, None]}},
            config={"configurable": {"thread_id": thread_id}},
        )
    async with open_checkpointer(checkpoint_database_url) as saver_b:
        graph_b = build_probe_graph(saver_b)
        snapshot = await graph_b.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        assert snapshot.values["payload"] == {"items": [1, True, None]}
        await saver_b.adelete_thread(thread_id)
```

The test module sets no environment variable itself; `tests/integration/conftest.py` must set it before source imports.

- [ ] **Step 2: Run checkpointer RED**

```powershell
uv run pytest tests/integration/workflow/test_checkpoints.py -q
```

Expected RED: collection fails because `opercerta.infrastructure.checkpoints` does not exist.

- [ ] **Step 3: GREEN — implement lazy strict import and isolated DSN**

Create `src/opercerta/infrastructure/checkpoints.py`:

```python
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def checkpoint_dsn(database_url: SecretStr) -> SecretStr:
    parsed = make_url(database_url.get_secret_value()).set(drivername="postgresql")
    isolated = parsed.update_query_dict({"options": "-c search_path=langgraph"})
    return SecretStr(isolated.render_as_string(hide_password=False))


@asynccontextmanager
async def open_checkpointer(
    database_url: SecretStr,
    *,
    setup: bool = False,
) -> AsyncIterator["AsyncPostgresSaver"]:
    if os.environ.get("LANGGRAPH_STRICT_MSGPACK", "").lower() != "true":
        raise RuntimeError("LANGGRAPH_STRICT_MSGPACK must be true before checkpointer import")
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    dsn = checkpoint_dsn(database_url)
    async with AsyncPostgresSaver.from_conn_string(dsn.get_secret_value()) as saver:
        if setup:
            await saver.setup()
        yield saver
```

At the top of `tests/integration/conftest.py`, immediately after importing `os`, add:

```python
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
```

Add a session fixture that calls setup once and never prints the URL:

```python
@pytest.fixture(scope="session")
def checkpoint_database_url(migrated_database_url: SecretStr) -> SecretStr:
    from opercerta.infrastructure.checkpoints import open_checkpointer

    async def setup_once() -> None:
        async with open_checkpointer(migrated_database_url, setup=True):
            pass

    asyncio.run(setup_once())
    return migrated_database_url
```

Append to `.env.example`:

```dotenv
LANGGRAPH_STRICT_MSGPACK=true
```

- [ ] **Step 4: Verify checkpointer GREEN and inspect Schema placement**

```powershell
uv run pytest tests/integration/workflow/test_checkpoints.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the checkpointer boundary**

```powershell
git add .env.example src/opercerta/infrastructure/checkpoints.py tests/integration/conftest.py tests/integration/workflow/test_checkpoints.py
git diff --cached --check
git commit -m "feat: isolate langgraph checkpoints"
```

---

### Task 4: JSON-only reliability graph and no-crash paths

**Files:**
- Create: `src/opercerta/workflow/__init__.py`
- Create: `src/opercerta/workflow/reliability_graph.py`
- Create: `tests/integration/workflow/test_reliability_graph.py`

**Interfaces:**
- Produces: `ReliabilityState` with only JSON-compatible fields.
- Produces: `build_initial_state(view: RecoveryView) -> ReliabilityState`.
- Produces: `build_reliability_graph(checkpointer, operation_states, work_orders) -> CompiledStateGraph`.
- Invariant: `request_approval` interrupts before approval or work-order side effects.

- [ ] **Step 1: RED — prove interrupt precedes writes and both decisions terminate correctly**

The focused integration file must contain three tests:

```python
@pytest.mark.asyncio
async def test_graph_interrupts_before_approval_or_work_order_write(graph_fixture) -> None:
    operation_id, graph = await graph_fixture(status="received")
    view = await graph_fixture.states.load_recovery_view(operation_id)
    result = await graph.ainvoke(
        build_initial_state(view),
        config={"configurable": {"thread_id": str(operation_id)}},
    )
    assert "__interrupt__" in result
    facts = await business_facts(graph_fixture.engine, operation_id)
    assert facts.status == "awaiting_approval"
    assert facts.approval_count == 0
    assert facts.work_order_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_work_orders"),
    [("approved", "completed", 1), ("rejected", "rejected", 0)],
)
async def test_no_crash_decision_uses_saved_approval(
    graph_fixture, decision: str, expected_status: str, expected_work_orders: int
) -> None:
    operation_id, graph = await graph_fixture(status="received")
    view = await graph_fixture.states.load_recovery_view(operation_id)
    await graph.ainvoke(
        build_initial_state(view),
        config={"configurable": {"thread_id": str(operation_id)}},
    )
    approval = await graph_fixture.approvals.submit_once(
        approval_command(operation_id, decision)
    )
    await graph.ainvoke(
        Command(
            resume={"approval_id": str(approval.id), "decision": approval.decision.value}
        ),
        config={"configurable": {"thread_id": str(operation_id)}},
    )
    facts = await business_facts(graph_fixture.engine, operation_id)
    assert facts.status == expected_status
    assert facts.approval_count == 1
    assert facts.work_order_count == expected_work_orders
    assert facts.terminal_event_count == 1
```

`graph_fixture` is a local helper object in the same test module; it creates a complete snapshot, repositories and compiled graph, and its cleanup deletes the operation and saver thread.

- [ ] **Step 2: Run graph RED**

```powershell
uv run pytest tests/integration/workflow/test_reliability_graph.py -q
```

Expected RED: collection fails because `opercerta.workflow.reliability_graph` does not exist.

- [ ] **Step 3: GREEN — implement the exact topology with closure-injected repositories**

Create `src/opercerta/workflow/__init__.py` as an empty package marker and implement `reliability_graph.py` with this topology and node contract:

```python
from typing import TYPE_CHECKING, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from pydantic import JsonValue, ValidationError

from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.operation_state import ApprovalResume, OperationSnapshot, RecoveryView
from opercerta.domain.work_orders import WorkOrderCommand
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class ReliabilityState(TypedDict):
    operation_id: str
    snapshot: dict[str, JsonValue]
    approval: dict[str, JsonValue] | None
    work_order: dict[str, JsonValue] | None
    replayed: bool
    recovery_action: str | None


ReliabilityGraph = CompiledStateGraph[
    ReliabilityState, None, ReliabilityState, ReliabilityState
]


def build_initial_state(view: RecoveryView) -> ReliabilityState:
    return ReliabilityState(
        operation_id=str(view.operation_id),
        snapshot=cast(dict[str, JsonValue], view.snapshot.model_dump(mode="json")),
        approval=None,
        work_order=None,
        replayed=False,
        recovery_action=None,
    )


def build_reliability_graph(
    checkpointer: "AsyncPostgresSaver",
    operation_states: OperationStateRepository,
    work_orders: WorkOrderRepository,
) -> ReliabilityGraph:
    def operation_id(state: ReliabilityState) -> UUID:
        try:
            return UUID(state["operation_id"])
        except (KeyError, TypeError, ValueError):
            raise RecoveryStateConflict(UUID(int=0), "invalid_graph_operation_id") from None

    def snapshot(state: ReliabilityState) -> OperationSnapshot:
        target = operation_id(state)
        try:
            return OperationSnapshot.model_validate(state["snapshot"])
        except (KeyError, ValidationError):
            raise RecoveryStateConflict(target, "invalid_graph_snapshot") from None

    def approval(state: ReliabilityState) -> ApprovalResume:
        target = operation_id(state)
        try:
            return ApprovalResume.model_validate(state["approval"])
        except (KeyError, ValidationError):
            raise RecoveryStateConflict(target, "invalid_graph_approval") from None

    async def prepare_approval(state: ReliabilityState) -> dict[str, object]:
        await operation_states.mark_awaiting_approval(operation_id(state))
        return {}

    def request_approval(state: ReliabilityState) -> dict[str, object]:
        frozen = snapshot(state)
        resumed = interrupt(
            {
                "operation_id": state["operation_id"],
                "risk": frozen.risk,
                "plan": frozen.plan,
            }
        )
        try:
            decision = ApprovalResume.model_validate(resumed)
        except ValidationError:
            raise RecoveryStateConflict(
                operation_id(state), "invalid_approval_resume"
            ) from None
        return {"approval": decision.model_dump(mode="json")}

    def route_decision(state: ReliabilityState) -> str:
        return approval(state).decision.value

    async def mark_executing(state: ReliabilityState) -> dict[str, object]:
        decision = approval(state)
        await operation_states.mark_executing(operation_id(state), decision.approval_id)
        return {}

    async def execute_work_order(state: ReliabilityState) -> dict[str, object]:
        result = await work_orders.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id(state),
                payload=snapshot(state).work_order_payload,
            )
        )
        return {
            "work_order": {
                "work_order_id": str(result.work_order.id),
                "payload_hash": result.work_order.payload_hash,
            },
            "replayed": result.replayed,
        }

    def work_order_locator(state: ReliabilityState) -> tuple[UUID, str]:
        target = operation_id(state)
        value = state["work_order"]
        if not isinstance(value, dict) or set(value) != {"work_order_id", "payload_hash"}:
            raise RecoveryStateConflict(target, "invalid_graph_work_order")
        work_order_id = value["work_order_id"]
        payload_hash = value["payload_hash"]
        if not isinstance(work_order_id, str) or not isinstance(payload_hash, str):
            raise RecoveryStateConflict(target, "invalid_graph_work_order")
        try:
            return UUID(work_order_id), payload_hash
        except ValueError:
            raise RecoveryStateConflict(target, "invalid_graph_work_order") from None

    async def mark_verifying(state: ReliabilityState) -> dict[str, object]:
        work_order_id, _ = work_order_locator(state)
        await operation_states.mark_verifying(operation_id(state), work_order_id)
        return {}

    async def verify_work_order(state: ReliabilityState) -> dict[str, object]:
        target = operation_id(state)
        expected_id, expected_hash = work_order_locator(state)
        view = await operation_states.load_recovery_view(target)
        if view.work_order_id != expected_id or view.payload_hash != expected_hash:
            raise RecoveryStateConflict(target, "work_order_verification_mismatch")
        return {}

    async def mark_completed(state: ReliabilityState) -> dict[str, object]:
        work_order_id, _ = work_order_locator(state)
        await operation_states.mark_completed(operation_id(state), work_order_id)
        return {}

    async def mark_rejected(state: ReliabilityState) -> dict[str, object]:
        decision = approval(state)
        await operation_states.mark_rejected(operation_id(state), decision.approval_id)
        return {}

    builder = StateGraph(ReliabilityState)
    builder.add_node("prepare_approval", prepare_approval)
    builder.add_node("request_approval", request_approval)
    builder.add_node("mark_executing", mark_executing)
    builder.add_node("execute_work_order", execute_work_order)
    builder.add_node("mark_verifying", mark_verifying)
    builder.add_node("verify_work_order", verify_work_order)
    builder.add_node("mark_completed", mark_completed)
    builder.add_node("mark_rejected", mark_rejected)
    builder.add_edge(START, "prepare_approval")
    builder.add_edge("prepare_approval", "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_decision,
        {"approved": "mark_executing", "rejected": "mark_rejected"},
    )
    builder.add_edge("mark_executing", "execute_work_order")
    builder.add_edge("execute_work_order", "mark_verifying")
    builder.add_edge("mark_verifying", "verify_work_order")
    builder.add_edge("verify_work_order", "mark_completed")
    builder.add_edge("mark_completed", END)
    builder.add_edge("mark_rejected", END)
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Verify interrupt, approved and rejected GREEN**

```powershell
uv run pytest tests/integration/workflow/test_reliability_graph.py -q
uv run pytest tests/integration/workflow/test_checkpoints.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the graph boundary**

```powershell
git add src/opercerta/workflow/__init__.py src/opercerta/workflow/reliability_graph.py tests/integration/workflow/test_reliability_graph.py
git diff --cached --check
git commit -m "feat: interrupt before simulated execution"
```

---

### Task 5: Recovery coordinator and four-point A/B restart matrix

**Files:**
- Create: `src/opercerta/workflow/recovery_coordinator.py`
- Create: `tests/integration/workflow/test_restart_recovery.py`

**Interfaces:**
- Consumes: `ReliabilityGraph`, `OperationStateRepository`, `RecoveryFacts`, `choose_recovery_action`.
- Produces: `RecoveryCoordinator.recover(operation_id: UUID) -> RecoveryAction`.
- Invariant: coordinator never writes approvals and never fabricates a missing snapshot or decision.

- [ ] **Step 1: RED — create the complete restart matrix**

Create one parametrized test for the business-row-before-first-checkpoint and waiting-at-interrupt cases, plus approved, rejected and prewritten-work-order cases. Each case must:

```text
async with open_checkpointer(checkpoint_database_url) as saver_a:
    graph_a = build_reliability_graph(saver_a, states, work_orders)
    # Establish only the case-specific graph/checkpoint fact.
# saver_a and graph_a are now unreachable and the Psycopg connection is closed.

# Commit only the case-specific approval/work-order business fact here.

async with open_checkpointer(checkpoint_database_url) as saver_b:
    graph_b = build_reliability_graph(saver_b, states, work_orders)
    action = await RecoveryCoordinator(graph_b, states).recover(operation_id)
    final_snapshot = await graph_b.aget_state(
        {"configurable": {"thread_id": str(operation_id)}}
    )
    await saver_b.adelete_thread(str(operation_id))

facts = await business_facts(engine, operation_id)
```

Required assertions:

| Case | Returned action | Final status | approvals | work orders | terminal event | replay proof |
| --- | --- | --- | ---: | ---: | ---: | --- |
| business row, no checkpoint | `REBUILD_FROM_BUSINESS_FACTS` | `awaiting_approval` | 0 | 0 | 0 | final snapshot interrupted |
| waiting interrupt | `KEEP_WAITING` | `awaiting_approval` | 0 | 0 | 0 | graph B writes nothing |
| approved after interrupt | `RESUME_DECISION` | `completed` | 1 | 1 | 1 | one `work_order_created` |
| rejected after interrupt | `RESUME_DECISION` | `rejected` | 1 | 0 | 1 | zero work-order calls/rows |
| work order committed after interrupt | `RESUME_DECISION` | `completed` | 1 | 1 | 1 | final graph state has original ID and `replayed=True`; one `work_order_created` |

Add conflict tests for checkpoint `operation_id` mismatch and terminal business state with pending checkpoint; both must raise `RecoveryStateConflict` and leave business row counts unchanged.

- [ ] **Step 2: Run restart RED**

```powershell
uv run pytest tests/integration/workflow/test_restart_recovery.py -q
```

Expected RED: collection fails because `recovery_coordinator` does not exist.

- [ ] **Step 3: GREEN — implement snapshot classification and exact action dispatch**

Create `src/opercerta/workflow/recovery_coordinator.py`:

```python
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langgraph.types import Command, StateSnapshot

from opercerta.domain.errors import RecoveryStateConflict
from opercerta.domain.operation_state import RecoveryView
from opercerta.domain.recovery import (
    CheckpointPhase,
    RecoveryAction,
    RecoveryFacts,
    TERMINAL_STATUSES,
    choose_recovery_action,
)
from opercerta.infrastructure.db.operation_state_repository import OperationStateRepository
from opercerta.workflow.reliability_graph import (
    ReliabilityGraph,
    build_initial_state,
)


class RecoveryCoordinator:
    def __init__(
        self,
        graph: ReliabilityGraph,
        operation_states: OperationStateRepository,
    ) -> None:
        self._graph = graph
        self._operation_states = operation_states

    async def recover(self, operation_id: UUID) -> RecoveryAction:
        view = await self._operation_states.load_recovery_view(operation_id)
        config = {"configurable": {"thread_id": str(operation_id)}}
        snapshot = await self._graph.aget_state(config)
        phase = self._checkpoint_phase(snapshot)
        self._validate_checkpoint(operation_id, view, snapshot, phase)
        action = choose_recovery_action(
            RecoveryFacts(
                status=view.status,
                checkpoint=phase,
                has_approval=view.approval_id is not None,
                has_work_order=view.work_order_id is not None,
            )
        )
        if action is RecoveryAction.REBUILD_FROM_BUSINESS_FACTS:
            await self._graph.ainvoke(build_initial_state(view), config=config)
        elif action is RecoveryAction.KEEP_WAITING or action is RecoveryAction.NO_OP:
            return action
        elif action is RecoveryAction.RESUME_DECISION:
            if view.approval_id is None or view.decision is None:
                raise RecoveryStateConflict(operation_id, "approval_locator_missing")
            await self._graph.ainvoke(
                Command(
                    resume={
                        "approval_id": str(view.approval_id),
                        "decision": view.decision.value,
                    }
                ),
                config=config,
            )
        else:
            await self._graph.ainvoke(None, config=config)
        return action

    def _checkpoint_phase(self, snapshot: StateSnapshot) -> CheckpointPhase:
        if snapshot.created_at is None:
            return CheckpointPhase.MISSING
        if snapshot.interrupts or any(task.interrupts for task in snapshot.tasks):
            return CheckpointPhase.INTERRUPTED
        return CheckpointPhase.RUNNABLE

    def _validate_checkpoint(
        self,
        operation_id: UUID,
        view: RecoveryView,
        snapshot: StateSnapshot,
        phase: CheckpointPhase,
    ) -> None:
        if phase is CheckpointPhase.MISSING:
            return
        values: Mapping[str, Any]
        if not isinstance(snapshot.values, Mapping):
            raise RecoveryStateConflict(operation_id, "checkpoint_values_not_mapping")
        values = snapshot.values
        if values.get("operation_id") != view.thread_id:
            raise RecoveryStateConflict(operation_id, "checkpoint_operation_id_mismatch")
        if view.status in TERMINAL_STATUSES and (
            snapshot.next or phase is CheckpointPhase.INTERRUPTED
        ):
            raise RecoveryStateConflict(operation_id, "terminal_state_has_pending_checkpoint")
```

- [ ] **Step 4: Verify focused restart GREEN and infrastructure failure preservation**

```powershell
uv run pytest tests/integration/workflow/test_restart_recovery.py -q
uv run pytest tests/integration/workflow -q
```

Add this infrastructure-failure preservation test using the same seed and cleanup helpers as the restart matrix:

```python
@pytest.mark.asyncio
async def test_closed_checkpointer_preserves_committed_approval(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
) -> None:
    operation_id = await seed_received_operation(engine)
    states = OperationStateRepository(engine)
    work_orders = WorkOrderRepository(engine)
    async with open_checkpointer(checkpoint_database_url) as saver_a:
        graph_a = build_reliability_graph(saver_a, states, work_orders)
        await graph_a.ainvoke(
            build_initial_state(await states.load_recovery_view(operation_id)),
            config={"configurable": {"thread_id": str(operation_id)}},
        )
    approval = await ApprovalRepository(engine).submit_once(
        approval_command(operation_id, "approved")
    )
    async with open_checkpointer(checkpoint_database_url) as saver_b:
        closed_graph = build_reliability_graph(saver_b, states, work_orders)
    with pytest.raises(psycopg.OperationalError):
        await RecoveryCoordinator(closed_graph, states).recover(operation_id)
    facts = await business_facts(engine, operation_id)
    assert facts.status == "resuming"
    assert facts.approval_ids == [approval.id]
    assert facts.work_order_ids == []
```

Do not translate the checkpointer failure into a successful business state.

- [ ] **Step 5: Repeat the complete restart matrix in fresh Pytest processes**

```powershell
1..10 | ForEach-Object {
    uv run pytest tests/integration/workflow/test_restart_recovery.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Expected: ten independent invocations exit `0`; report the observed completion count, not a production reliability percentage.

- [ ] **Step 6: Run the complete fresh gate**

```powershell
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

If any command fails or behaves unexpectedly, stop feature editing and use `superpowers:systematic-debugging` before changing implementation.

- [ ] **Step 7: Commit the restart recovery boundary**

```powershell
git add src/opercerta/workflow/recovery_coordinator.py tests/integration/workflow/test_restart_recovery.py
git diff --cached --check
git commit -m "feat: recover workflows after restart"
```

---

### Task 6: Record Task 5 evidence without opening the release gate

**Files:**
- Create: `docs/release-evidence/langgraph-restart-recovery.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-16.md`
- Modify: `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md`
- Modify: `docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md`

**Interfaces:**
- Consumes: terminal output and commits produced by Tasks 1–5 only.
- Produces: Chinese-first RED/GREEN, Schema, restart-matrix, database-fact and static-gate evidence.
- Preserves: `OperCerta release gate: CLOSED`; Task 6 of the overall reliability plan remains the next step.

- [ ] **Step 1: Create the evidence file from observed facts only**

Use these exact sections:

```markdown
# OperCerta LangGraph 四点重启恢复证据

## 验证范围
## 环境与锁定版本
## RED 证据
## GREEN 证据
## Checkpointer Schema 与严格序列化
## 四点 A/B 重启矩阵
## 数据库最终事实
## 独立进程重复验证
## 基础设施失败保持的业务事实
## 限制、未验证范围与发布门禁
## Git 回滚点
```

Every result line must be copied from a command executed in Tasks 1–5. The limitations section must explicitly state that Task 5 does not prove multi-Worker scheduling, distributed exactly-once, Linux/Docker release readiness, full MCP/API/UI behavior or public deployment.

- [ ] **Step 2: Synchronize status and retain the Task 6 boundary**

Update the index, handoff, current state, daily log and both plans with the actual commits and observed commands. Mark Task 5 complete only if the complete fresh gate and ten independent restart invocations passed. Keep the overall release gate `CLOSED` and set the next action to overall reliability-kernel Task 6 evidence/gate handoff.

- [ ] **Step 3: Verify documentation and credential hygiene**

```powershell
git diff --check
rg -n "T[B]D|T[O]DO|implement[ ]later|fill[ ]in[ ]details" docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md
rg -n --glob '!docs/superpowers/plans/*.md' "OPERCERTA_DATABASE_URL=.*@|postgresql.*://.*:.*@" docs README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md
git status --short
```

Expected: diff check exits `0`; both scans return no matches; status lists only intended Task 5 documentation files.

- [ ] **Step 4: Commit the evidence checkpoint**

```powershell
git add DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/development-log docs/release-evidence/langgraph-restart-recovery.md docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md
git diff --cached --check
git commit -m "docs: record restart recovery evidence"
git status --short --branch
```

Expected: documentation commit succeeds and working tree is clean. Do not create a tag, deploy, open the release gate or start another project.

## Plan Self-Review

- Spec coverage: Tasks 1–5 cover the frozen snapshot, stable errors, five state transitions, same-target event verification, checkpointer isolation/setup, JSON-only graph, approved/rejected normal paths, four restart points, A/B object release, ten independent processes and infrastructure-failure preservation.
- Schema boundary: no business migration or column is added; existing `operations.request_payload`, `public` business tables and `langgraph` Schema remain distinct.
- Type consistency: `OperationSnapshot`, `ApprovalResume`, `RecoveryView`, `OperationTransitionResult`, `ReliabilityState`, `ReliabilityGraph` and `RecoveryCoordinator.recover()` have one definition and identical downstream names.
- Side-effect ordering: approval is only written by `ApprovalRepository`; graph interrupt occurs before work-order execution; work-order replay remains delegated to Task 4; terminal state writes remain delegated to `OperationStateRepository`.
- Truthfulness: planned commands contain no prefilled pass count, rate or latency; evidence is written only after fresh output exists.
- Scope: FastAPI, SSE, UI, MCP, real tools/models, Docker/Linux, multi-Worker and public release remain explicitly outside Task 5.

## Execution Decision

The user previously selected Inline Execution for this tightly coupled PostgreSQL/LangGraph slice. Execute this plan in the current session with `superpowers:executing-plans`, one RED/GREEN and one atomic Git checkpoint at a time; do not request repeated user confirmation for internal interfaces.
