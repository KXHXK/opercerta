# OperCerta Idempotent Work-Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用严格 TDD 实现 OperCerta 模拟工单的确定性 payload 指纹、授权后原子创建、安全重放、冲突分类和十路并发有效一次写入。

**Architecture:** 纯 Python/Pydantic 领域模块负责 JSON 边界、稳定幂等键和 canonical payload hash；PostgreSQL Repository 在 operation 行锁保护下先识别已有结果，再校验首次写入授权，并把工单、审计序号和创建事件放在一个事务中。数据库唯一约束是最终碰撞防线，正常并发路径由 operation 行锁串行化。

**Tech Stack:** Python 3.12.13、Pydantic 2.13.4、SQLAlchemy 2.0.51 Core async、Psycopg 3.3.4、PostgreSQL 18.4、Pytest 9.1.1、pytest-asyncio 1.4.0、Ruff 0.15.21、mypy 2.3.0。

## Global Constraints

- 只修改 `D:\CODEX\agent-portfolio\opercerta`，不复用旧公司源码、数据、截图、规则、模型或品牌材料。
- 只实现 Task 4；不实现 HTTP/API、真实外部执行、LangGraph 恢复、`created` 之后的工单状态或其他项目。
- `WorkOrderCommand.payload` 只接受顶层 JSON object；空 object 合法，非字符串 key、非 JSON 值、`NaN` 和正负无穷必须拒绝。
- 幂等键固定为 `work-order:v1:<canonical-lowercase-uuid>`；canonical JSON 固定使用 `ensure_ascii=False`、`sort_keys=True`、`separators=(",", ":")`、`allow_nan=False`。
- 首次写入只允许已有 `approved` 决定且 operation 状态属于 `resuming`、`executing`、`verifying`；已有相同工单的安全重放必须先于当前状态授权检查。
- 工单、`operations.next_audit_sequence` 和 `work_order_created` 事件必须同事务提交或回滚；审计 payload 只记录 `work_order_id`、`idempotency_key`、`payload_hash`。
- 只把实际运行命令的输出写入证据；不得预填通过数量、成功率、耗时或效果指标。
- `.env.local` 和数据库密码不得显示在终端输出、计划、日志、测试错误或 Git 中。
- Task 4 完成后发布门禁仍为 `CLOSED`，不启动 Task 5 或其他项目。

## File Responsibility Map

| Path | Responsibility |
| --- | --- |
| `src/opercerta/domain/work_orders.py` | JSON 边界、不可额外赋值的领域模型、稳定幂等键、canonical JSON 和 SHA-256 |
| `src/opercerta/domain/errors.py` | 新增稳定的 `IdempotencyConflict` 与 `WriteNotAuthorized` 异常 |
| `src/opercerta/infrastructure/db/work_order_repository.py` | operation 行锁、已有记录重放、首次授权、工单与审计同事务写入、唯一冲突翻译 |
| `tests/unit/domain/test_work_orders.py` | 非法输入、模型约束、确定性 key/hash 的纯单元 RED/GREEN |
| `tests/integration/conftest.py` | 共享且不回显密码的 PostgreSQL async Engine fixture |
| `tests/integration/db/test_approval_race.py` | 改用共享 Engine fixture，审批基线行为不变 |
| `tests/integration/db/test_work_order_idempotency.py` | 授权、回放、冲突、零写入和十路并发数据库事实 |
| `docs/release-evidence/work-order-idempotency.md` | 只记录本轮实际执行的 RED/GREEN 与门禁输出 |

---

### Task 1: Work-order domain contract and deterministic fingerprint

**Files:**
- Create: `tests/unit/domain/test_work_orders.py`
- Create: `src/opercerta/domain/work_orders.py`
- Modify: `src/opercerta/domain/errors.py`

**Interfaces:**
- Consumes: Python `UUID`, JSON-compatible values, timezone-aware `datetime`.
- Produces: `WorkOrderCommand`, `WorkOrderRecord`, `WorkOrderWriteResult`, `derive_idempotency_key(operation_id: UUID) -> str`, `canonical_payload_json(payload: dict[str, JsonValue]) -> str`, `hash_payload(payload: dict[str, JsonValue]) -> str`.
- Produces: `IdempotencyConflict(operation_id: UUID, idempotency_key: str)` and `WriteNotAuthorized(operation_id: UUID, status: str)`.

- [x] **Step 1: RED — write illegal-input and deterministic-function tests**

Create `tests/unit/domain/test_work_orders.py` with the complete test boundary:

```python
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.errors import IdempotencyConflict, WriteNotAuthorized
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    canonical_payload_json,
    derive_idempotency_key,
    hash_payload,
)

OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")
WORK_ORDER_ID = UUID("00000000-0000-4000-8000-000000000002")


def valid_record_data() -> dict[str, object]:
    now = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    return {
        "id": WORK_ORDER_ID,
        "operation_id": OPERATION_ID,
        "idempotency_key": derive_idempotency_key(OPERATION_ID),
        "payload": {"quantity": 4, "sku": "SKU-DEMO-001"},
        "payload_hash": hash_payload({"quantity": 4, "sku": "SKU-DEMO-001"}),
        "status": "created",
        "created_at": now,
        "updated_at": now,
    }


def test_command_accepts_an_empty_json_object() -> None:
    command = WorkOrderCommand(operation_id=OPERATION_ID, payload={})

    assert command.payload == {}


@pytest.mark.parametrize(
    "data",
    [
        {"payload": {}},
        {"operation_id": OPERATION_ID},
        {"operation_id": "not-a-uuid", "payload": {}},
        {"operation_id": OPERATION_ID, "payload": []},
        {"operation_id": OPERATION_ID, "payload": {1: "value"}},
        {"operation_id": OPERATION_ID, "payload": {"items": ("a", "b")}},
        {"operation_id": OPERATION_ID, "payload": {"value": object()}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("nan")}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("inf")}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("-inf")}},
        {"operation_id": OPERATION_ID, "payload": {}, "extra": True},
    ],
)
def test_command_rejects_invalid_input(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WorkOrderCommand.model_validate(data)


def test_command_fields_cannot_be_reassigned() -> None:
    command = WorkOrderCommand(operation_id=OPERATION_ID, payload={})

    with pytest.raises(ValidationError):
        command.operation_id = WORK_ORDER_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idempotency_key", ""),
        ("idempotency_key", "x" * 129),
        ("payload_hash", "A" * 64),
        ("payload_hash", "0" * 63),
        ("status", "executing"),
        ("created_at", datetime(2026, 7, 16, 0, 0)),
        ("updated_at", datetime(2026, 7, 16, 0, 0)),
    ],
)
def test_record_rejects_invalid_fields(field: str, value: object) -> None:
    data = valid_record_data()
    data[field] = value

    with pytest.raises(ValidationError):
        WorkOrderRecord.model_validate(data)


def test_write_result_preserves_record_and_replay_flag() -> None:
    record = WorkOrderRecord.model_validate(valid_record_data())

    result = WorkOrderWriteResult(work_order=record, replayed=True)

    assert result.work_order.id == WORK_ORDER_ID
    assert result.replayed is True


def test_record_forbids_extra_fields_and_reassignment() -> None:
    data = valid_record_data()
    data["extra"] = True
    with pytest.raises(ValidationError):
        WorkOrderRecord.model_validate(data)

    record = WorkOrderRecord.model_validate(valid_record_data())
    with pytest.raises(ValidationError):
        record.status = "created"


def test_idempotency_key_is_stable_for_operation() -> None:
    assert derive_idempotency_key(OPERATION_ID) == (
        "work-order:v1:00000000-0000-4000-8000-000000000001"
    )


def test_canonical_payload_is_compact_sorted_and_unicode_preserving() -> None:
    assert canonical_payload_json({"sku": "设备-01", "quantity": 4}) == (
        '{"quantity":4,"sku":"设备-01"}'
    )


def test_payload_hash_is_independent_of_dictionary_order() -> None:
    assert hash_payload({"quantity": 4, "sku": "SKU-DEMO-001"}) == hash_payload(
        {"sku": "SKU-DEMO-001", "quantity": 4}
    )


def test_payload_hash_changes_with_content() -> None:
    assert hash_payload({"quantity": 4}) != hash_payload({"quantity": 5})


def test_domain_errors_keep_safe_location_fields() -> None:
    conflict = IdempotencyConflict(
        OPERATION_ID,
        derive_idempotency_key(OPERATION_ID),
    )
    unauthorized = WriteNotAuthorized(OPERATION_ID, "planning")

    assert conflict.code == "idempotency_conflict"
    assert conflict.operation_id == OPERATION_ID
    assert conflict.idempotency_key == derive_idempotency_key(OPERATION_ID)
    assert unauthorized.code == "write_not_authorized"
    assert unauthorized.operation_id == OPERATION_ID
    assert unauthorized.status == "planning"
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
uv run pytest tests/unit/domain/test_work_orders.py -q
```

Expected RED: collection fails because `opercerta.domain.work_orders` and the two new error classes do not exist. No database is accessed.

- [x] **Step 3: GREEN — add the stable error types**

Append these classes to `src/opercerta/domain/errors.py` without changing existing errors:

```python
class IdempotencyConflict(RuntimeError):
    code = "idempotency_conflict"

    def __init__(self, operation_id: UUID, idempotency_key: str) -> None:
        self.operation_id = operation_id
        self.idempotency_key = idempotency_key
        super().__init__(self.code)


class WriteNotAuthorized(RuntimeError):
    code = "write_not_authorized"

    def __init__(self, operation_id: UUID, status: str) -> None:
        self.operation_id = operation_id
        self.status = status
        super().__init__(self.code)
```

- [x] **Step 4: GREEN — implement the minimal domain module**

Create `src/opercerta/domain/work_orders.py`:

```python
import hashlib
import json
import math
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    StringConstraints,
    field_validator,
)

IdempotencyKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
]
PayloadHash = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


def _require_json_value(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _require_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            _require_json_value(item)
        return
    raise ValueError("payload must contain only JSON values")


class WorkOrderCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    payload: dict[str, JsonValue]

    @field_validator("payload", mode="before")
    @classmethod
    def require_json_object(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise ValueError("payload must be a JSON object")
        _require_json_value(value)
        return value


class WorkOrderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    operation_id: UUID
    idempotency_key: IdempotencyKey
    payload: dict[str, JsonValue]
    payload_hash: PayloadHash
    status: Literal["created"]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("work-order timestamps must include timezone")
        return value


class WorkOrderWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    work_order: WorkOrderRecord
    replayed: bool


def derive_idempotency_key(operation_id: UUID) -> str:
    return f"work-order:v1:{operation_id}"


def canonical_payload_json(payload: dict[str, JsonValue]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def hash_payload(payload: dict[str, JsonValue]) -> str:
    canonical_json = canonical_payload_json(payload)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
```

- [x] **Step 5: Verify focused GREEN and static gates**

Run:

```powershell
uv run pytest tests/unit/domain/test_work_orders.py -q
uv run pytest tests/unit -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Expected: every command exits `0`; record the observed test counts only after the commands finish.

- [x] **Step 6: Commit the domain boundary**

```powershell
git add src/opercerta/domain/errors.py src/opercerta/domain/work_orders.py tests/unit/domain/test_work_orders.py
git diff --cached --check
git commit -m "feat: define idempotent work order contract"
```

---

### Task 2: Shared secret-safe async PostgreSQL Engine fixture

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `tests/integration/db/test_approval_race.py`

**Interfaces:**
- Consumes: session-scoped `migrated_database_url: SecretStr` and pytest `MonkeyPatch`.
- Produces: function-scoped `engine: AsyncEngine` for all async PostgreSQL integration tests.
- Preserves: password removed from the SQLAlchemy URL and supplied only through the temporary `PGPASSWORD` environment variable.

- [x] **Step 1: Move the Engine fixture to shared integration configuration**

Add these imports to `tests/integration/conftest.py`:

```python
from collections.abc import AsyncIterator

import pytest_asyncio
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
```

Append the exact shared fixture:

```python
@pytest_asyncio.fixture
async def engine(
    migrated_database_url: SecretStr,
    monkeypatch: MonkeyPatch,
) -> AsyncIterator[AsyncEngine]:
    parsed_url = make_url(migrated_database_url.get_secret_value())
    if parsed_url.password:
        monkeypatch.setenv("PGPASSWORD", parsed_url.password)
    database_engine = create_async_engine(
        parsed_url.set(password=None),
        pool_pre_ping=True,
    )
    try:
        yield database_engine
    finally:
        await database_engine.dispose()
```

In `tests/integration/db/test_approval_race.py`, delete the module-local `engine` fixture and remove only these now-unused imports:

```python
from collections.abc import AsyncIterator

import pytest_asyncio
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
```

Keep this import because test function annotations still use it:

```python
from sqlalchemy.ext.asyncio import AsyncEngine
```

- [x] **Step 2: Verify the approval baseline is unchanged**

Run:

```powershell
uv run pytest tests/integration/db/test_approval_race.py -q
uv run ruff check tests/integration
uv run ruff format --check tests/integration
```

Expected: every command exits `0`; approval race assertions remain exactly one accepted decision, nine classified conflicts and one approval audit event.

- [x] **Step 3: Commit the shared fixture refactor**

```powershell
git add tests/integration/conftest.py tests/integration/db/test_approval_race.py
git diff --cached --check
git commit -m "test: share postgres integration engine"
```

---

### Task 3: Atomic create-or-get Repository and concurrency proof

**Files:**
- Create: `tests/integration/db/test_work_order_idempotency.py`
- Create: `src/opercerta/infrastructure/db/work_order_repository.py`

**Interfaces:**
- Consumes: `AsyncEngine`, `WorkOrderCommand`, existing `operations`, `approvals`, `work_orders`, `audit_events` tables.
- Produces: `WorkOrderRepository(engine: AsyncEngine)` and `async create_or_get(command: WorkOrderCommand) -> WorkOrderWriteResult`.
- Invariant: an existing row is compared before first-write authorization; same hash replays, changed hash conflicts, and only a new row requires approval/status authorization.

- [x] **Step 1: RED — add authorization, replay, conflict and concurrency integration tests**

Create `tests/integration/db/test_work_order_idempotency.py`:

```python
import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.domain.errors import (
    IdempotencyConflict,
    OperationNotFound,
    WriteNotAuthorized,
)
from opercerta.domain.work_orders import WorkOrderCommand, WorkOrderWriteResult
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    operations,
    work_orders,
)
from opercerta.infrastructure.db.work_order_repository import WorkOrderRepository


async def seed_operation(
    engine: AsyncEngine,
    *,
    status: str,
    decision: str | None,
) -> UUID:
    operation_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(operations).values(
                id=operation_id,
                thread_id=f"thread-{operation_id}",
                request_payload={"message": "synthetic work-order test"},
                status=status,
                next_audit_sequence=0,
            )
        )
        if decision is not None:
            await connection.execute(
                insert(approvals).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    approver_id="synthetic-approver",
                    decision=decision,
                    reason="synthetic work-order authorization",
                )
            )
    return operation_id


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


def command_for(operation_id: UUID, quantity: int = 4) -> WorkOrderCommand:
    return WorkOrderCommand(
        operation_id=operation_id,
        payload={"quantity": quantity, "sku": "SKU-DEMO-001"},
    )


async def work_order_facts(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[list[RowMapping], list[RowMapping], int]:
    async with engine.connect() as connection:
        order_rows = list(
            (
                await connection.execute(
                    select(work_orders).where(work_orders.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
        event_rows = list(
            (
                await connection.execute(
                    select(audit_events)
                    .where(
                        audit_events.c.operation_id == operation_id,
                        audit_events.c.event_type == "work_order_created",
                    )
                    .order_by(audit_events.c.sequence)
                )
            )
            .mappings()
            .all()
        )
        next_sequence = (
            await connection.execute(
                select(operations.c.next_audit_sequence).where(
                    operations.c.id == operation_id
                )
            )
        ).scalar_one()
    return order_rows, event_rows, next_sequence


@pytest.mark.asyncio
async def test_missing_operation_is_rejected_without_writes(engine: AsyncEngine) -> None:
    operation_id = uuid4()

    with pytest.raises(OperationNotFound, match="operation_not_found"):
        await WorkOrderRepository(engine).create_or_get(command_for(operation_id))

    order_rows, event_rows, _ = await work_order_facts_for_missing(engine, operation_id)
    assert order_rows == []
    assert event_rows == []


async def work_order_facts_for_missing(
    engine: AsyncEngine,
    operation_id: UUID,
) -> tuple[list[RowMapping], list[RowMapping], None]:
    async with engine.connect() as connection:
        order_rows = (
            (
                await connection.execute(
                    select(work_orders).where(work_orders.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
        event_rows = (
            (
                await connection.execute(
                    select(audit_events).where(audit_events.c.operation_id == operation_id)
                )
            )
            .mappings()
            .all()
        )
    return list(order_rows), list(event_rows), None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "decision"),
    [
        ("resuming", None),
        ("resuming", "rejected"),
        ("planning", "approved"),
    ],
)
async def test_first_write_requires_approved_authorized_operation(
    engine: AsyncEngine,
    status: str,
    decision: str | None,
) -> None:
    operation_id = await seed_operation(engine, status=status, decision=decision)

    try:
        with pytest.raises(WriteNotAuthorized, match="write_not_authorized"):
            await WorkOrderRepository(engine).create_or_get(command_for(operation_id))

        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )
        assert order_rows == []
        assert event_rows == []
        assert next_sequence == 0
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["resuming", "executing", "verifying"])
async def test_first_write_accepts_each_authorized_status(
    engine: AsyncEngine,
    status: str,
) -> None:
    operation_id = await seed_operation(engine, status=status, decision="approved")

    try:
        result = await WorkOrderRepository(engine).create_or_get(command_for(operation_id))
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert result.replayed is False
        assert result.work_order.status == "created"
        assert result.work_order.created_at == result.work_order.updated_at
        assert result.work_order.created_at.utcoffset() is not None
        assert len(order_rows) == 1
        assert order_rows[0]["id"] == result.work_order.id
        assert len(event_rows) == 1
        assert event_rows[0]["payload"] == {
            "work_order_id": str(result.work_order.id),
            "idempotency_key": result.work_order.idempotency_key,
            "payload_hash": result.work_order.payload_hash,
        }
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_returned_nested_payload_is_independent_of_database_state(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id,
                payload={"items": [{"quantity": 4}]},
            )
        )
        returned_items = first.work_order.payload["items"]
        assert isinstance(returned_items, list)
        returned_item = returned_items[0]
        assert isinstance(returned_item, dict)
        returned_item["quantity"] = 99

        replay = await repository.create_or_get(
            WorkOrderCommand(
                operation_id=operation_id,
                payload={"items": [{"quantity": 4}]},
            )
        )

        assert replay.replayed is True
        assert replay.work_order.id == first.work_order.id
        assert replay.work_order.payload == {"items": [{"quantity": 4}]}
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_identical_replay_returns_same_id_without_second_audit(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id))
        second = await repository.create_or_get(command_for(operation_id))
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert first.replayed is False
        assert second.replayed is True
        assert second.work_order.id == first.work_order.id
        assert len(order_rows) == 1
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_replay_still_works_after_operation_status_advances(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id))
        async with engine.begin() as connection:
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(status="completed")
            )

        replay = await repository.create_or_get(command_for(operation_id))

        assert replay.replayed is True
        assert replay.work_order.id == first.work_order.id
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_changed_payload_raises_classified_conflict_without_mutation(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        first = await repository.create_or_get(command_for(operation_id, quantity=4))

        with pytest.raises(IdempotencyConflict, match="idempotency_conflict"):
            await repository.create_or_get(command_for(operation_id, quantity=5))

        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )
        assert len(order_rows) == 1
        assert order_rows[0]["id"] == first.work_order.id
        assert order_rows[0]["payload"] == {"quantity": 4, "sku": "SKU-DEMO-001"}
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)


@pytest.mark.asyncio
async def test_ten_concurrent_identical_commands_create_effectively_once(
    engine: AsyncEngine,
) -> None:
    operation_id = await seed_operation(engine, status="resuming", decision="approved")
    repository = WorkOrderRepository(engine)

    try:
        results = await asyncio.gather(
            *[repository.create_or_get(command_for(operation_id)) for _ in range(10)]
        )
        typed_results = [
            result for result in results if isinstance(result, WorkOrderWriteResult)
        ]
        order_rows, event_rows, next_sequence = await work_order_facts(
            engine,
            operation_id,
        )

        assert len(typed_results) == 10
        assert sum(not result.replayed for result in typed_results) == 1
        assert sum(result.replayed for result in typed_results) == 9
        assert len({result.work_order.id for result in typed_results}) == 1
        assert len(order_rows) == 1
        assert len(event_rows) == 1
        assert next_sequence == 1
    finally:
        await cleanup_operation(engine, operation_id)
```

- [x] **Step 2: Run the focused integration test and verify RED**

Run:

```powershell
uv run pytest tests/integration/db/test_work_order_idempotency.py -q
```

Expected RED: collection fails because `opercerta.infrastructure.db.work_order_repository` does not exist. The database fixture may migrate first, but no Task 4 work-order row is committed.

- [x] **Step 3: GREEN — implement create-or-get, audit atomicity and collision translation**

Create `src/opercerta/infrastructure/db/work_order_repository.py`:

```python
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from opercerta.domain.errors import (
    IdempotencyConflict,
    OperationNotFound,
    WriteNotAuthorized,
)
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    canonical_payload_json,
    derive_idempotency_key,
)
from opercerta.infrastructure.db.schema import (
    approvals,
    audit_events,
    operations,
    work_orders,
)

AUTHORIZED_STATUSES = frozenset({"resuming", "executing", "verifying"})


class WorkOrderRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create_or_get(self, command: WorkOrderCommand) -> WorkOrderWriteResult:
        canonical_json = canonical_payload_json(command.payload)
        payload_snapshot = cast(dict[str, JsonValue], json.loads(canonical_json))
        payload_hash = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        idempotency_key = derive_idempotency_key(command.operation_id)

        try:
            return await self._create_or_get_once(
                operation_id=command.operation_id,
                idempotency_key=idempotency_key,
                payload_snapshot=payload_snapshot,
                payload_hash=payload_hash,
            )
        except IntegrityError:
            async with self._engine.connect() as connection:
                existing = await self._find_existing(connection, idempotency_key)
            if existing is None:
                raise
            return self._existing_result(
                existing,
                operation_id=command.operation_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )

    async def _create_or_get_once(
        self,
        *,
        operation_id: UUID,
        idempotency_key: str,
        payload_snapshot: dict[str, JsonValue],
        payload_hash: str,
    ) -> WorkOrderWriteResult:
        async with self._engine.begin() as connection:
            operation = (
                (
                    await connection.execute(
                        select(operations)
                        .where(operations.c.id == operation_id)
                        .with_for_update()
                    )
                )
                .mappings()
                .one_or_none()
            )
            if operation is None:
                raise OperationNotFound(operation_id)

            existing = await self._find_existing(connection, idempotency_key)
            if existing is not None:
                return self._existing_result(
                    existing,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    payload_hash=payload_hash,
                )

            approved = (
                await connection.execute(
                    select(approvals.c.id).where(
                        approvals.c.operation_id == operation_id,
                        approvals.c.decision == "approved",
                    )
                )
            ).scalar_one_or_none()
            status = str(operation["status"])
            if approved is None or status not in AUTHORIZED_STATUSES:
                raise WriteNotAuthorized(operation_id, status)

            work_order_id = uuid4()
            created_at = datetime.now(UTC)
            sequence = int(operation["next_audit_sequence"]) + 1
            await connection.execute(
                insert(work_orders).values(
                    id=work_order_id,
                    operation_id=operation_id,
                    idempotency_key=idempotency_key,
                    payload=payload_snapshot,
                    payload_hash=payload_hash,
                    status="created",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                update(operations)
                .where(operations.c.id == operation_id)
                .values(
                    next_audit_sequence=sequence,
                    updated_at=created_at,
                )
            )
            await connection.execute(
                insert(audit_events).values(
                    id=uuid4(),
                    operation_id=operation_id,
                    sequence=sequence,
                    event_type="work_order_created",
                    payload={
                        "work_order_id": str(work_order_id),
                        "idempotency_key": idempotency_key,
                        "payload_hash": payload_hash,
                    },
                    created_at=created_at,
                )
            )

        return WorkOrderWriteResult(
            work_order=WorkOrderRecord(
                id=work_order_id,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                payload=payload_snapshot,
                payload_hash=payload_hash,
                status="created",
                created_at=created_at,
                updated_at=created_at,
            ),
            replayed=False,
        )

    async def _find_existing(
        self,
        connection: AsyncConnection,
        idempotency_key: str,
    ) -> Mapping[str, Any] | None:
        return (
            (
                await connection.execute(
                    select(work_orders).where(
                        work_orders.c.idempotency_key == idempotency_key
                    )
                )
            )
            .mappings()
            .one_or_none()
        )

    def _existing_result(
        self,
        existing: Mapping[str, Any],
        *,
        operation_id: UUID,
        idempotency_key: str,
        payload_hash: str,
    ) -> WorkOrderWriteResult:
        if existing["payload_hash"] != payload_hash:
            raise IdempotencyConflict(operation_id, idempotency_key)
        payload_snapshot = cast(
            dict[str, JsonValue],
            json.loads(
                canonical_payload_json(cast(dict[str, JsonValue], existing["payload"]))
            ),
        )
        return WorkOrderWriteResult(
            work_order=WorkOrderRecord(
                id=existing["id"],
                operation_id=existing["operation_id"],
                idempotency_key=existing["idempotency_key"],
                payload=payload_snapshot,
                payload_hash=existing["payload_hash"],
                status=existing["status"],
                created_at=existing["created_at"],
                updated_at=existing["updated_at"],
            ),
            replayed=True,
        )
```

- [x] **Step 4: Verify focused GREEN and all authorization/replay facts**

Run:

```powershell
uv run pytest tests/integration/db/test_work_order_idempotency.py -q
uv run pytest tests/integration/db -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Expected: every command exits `0`; the focused tests prove missing operation and unauthorized paths write zero rows, safe replay preserves one ID/audit, changed payload is classified, and each allowed status can create exactly one record.

- [x] **Step 5: Repeat the target race with fresh processes**

Run exactly twenty independent invocations:

```powershell
1..20 | ForEach-Object {
    uv run pytest tests/integration/db/test_work_order_idempotency.py::test_ten_concurrent_identical_commands_create_effectively_once -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Expected: all twenty invocations exit `0`; every invocation asserts one first creation, nine safe replays, one shared work-order ID, one database row and one creation audit. Do not convert this local deterministic repetition into a production success-rate claim.

- [x] **Step 6: Run the complete fresh verification gate**

Run:

```powershell
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
git diff --check
```

Expected: every command exits `0`. If any command fails or behaves unexpectedly, stop feature editing and use `superpowers:systematic-debugging` before changing implementation.

- [x] **Step 7: Commit the idempotent database boundary**

```powershell
git add src/opercerta/infrastructure/db/work_order_repository.py tests/integration/db/test_work_order_idempotency.py
git diff --cached --check
git commit -m "feat: make simulated work orders idempotent"
```

---

### Task 4: Record reproducible evidence and keep the release gate closed

**Files:**
- Create: `docs/release-evidence/work-order-idempotency.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-16.md`
- Modify: `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md`
- Modify: `docs/superpowers/plans/2026-07-16-work-order-idempotency.md`

**Interfaces:**
- Consumes: fresh terminal output from Task 3 only.
- Produces: a Chinese-first evidence record containing environment, commands, observed outcomes, transaction guarantees, limitations and rollback commit.
- Preserves: release gate `CLOSED`; Task 5 remains unstarted.

- [x] **Step 1: Write evidence from observed output only**

Create `docs/release-evidence/work-order-idempotency.md` with these exact sections and fill each section only with values copied from the completed commands:

```markdown
# OperCerta 幂等工单原子性证据

## 验证范围

说明本证据只覆盖 Task 4 的领域契约、PostgreSQL 首次授权写入、安全重放、payload 冲突和十路并发数据库事实。

## 环境

记录实际 Python、PostgreSQL、Pydantic、SQLAlchemy、Psycopg 和测试工具版本；不记录连接 URL 或密码。

## RED 证据

逐条记录领域模块缺失和 Repository 模块缺失时执行的命令、退出状态与失败原因。

## GREEN 证据

逐条记录 focused unit、focused integration、数据库集成、完整 Pytest、Ruff、format check 和 mypy 的实际命令摘要。

## 并发复验

记录二十次独立进程命令的实际完成情况，以及每次测试内部断言的一次创建、九次重放、同一 ID、一行工单和一条创建审计。

## 一致性结论

说明数据库写入边界达到 effectively-once；明确不把网络、消息队列或第三方外部执行描述为 exactly-once。

## 限制与发布门禁

列出未覆盖的 Task 5 LangGraph 重启恢复、真实外部动作、Linux/Docker 发布环境；发布门禁保持 CLOSED。

## 回滚点

记录 Task 4 开始前和完成后的真实 Git commit。
```

- [x] **Step 2: Synchronize plan, index, handoff and Chinese development log**

Apply these factual state changes:

```text
DOCUMENT_INDEX.md
- Add the focused Task 4 plan and work-order evidence paths.
- Mark Task 4 implemented only if every Task 3 verification command exited 0.

IMPLEMENTATION_HANDOFF.md
- Record the final Task 4 commit and observed test summaries.
- State that Task 5 is the next candidate but has not started.

docs/development-log/current-state.md
- Separate observed facts, remaining risks and the next smallest step.
- Keep Linux/Docker release verification and the global release gate unresolved.

docs/development-log/daily/2026-07-16.md
- Add RED, GREEN, race repetition, diagnosis/fixes if any, commits and next step in chronological order.

docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md
- Mark Task 4 checkboxes complete only for steps actually executed.
- Link this focused plan as the normative detailed execution source.

docs/superpowers/plans/2026-07-16-work-order-idempotency.md
- Mark each checkbox complete only after its command or edit is verified.
```

- [x] **Step 3: Verify documentation integrity and repository hygiene**

Run:

```powershell
git diff --check
rg -n --glob '!docs/superpowers/plans/2026-07-16-work-order-idempotency.md' "OPERCERTA_DATABASE_URL=.*@|postgresql.*://.*:.*@" docs README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md
git status --short
```

Expected: `git diff --check` exits `0`; the credential-pattern scan returns no matches; `git status --short` lists only the intended Task 4 evidence, index, handoff, log and plan files.

- [ ] **Step 4: Commit the evidence checkpoint**

```powershell
git add DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/development-log docs/release-evidence/work-order-idempotency.md docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md docs/superpowers/plans/2026-07-16-work-order-idempotency.md
git diff --cached --check
git commit -m "docs: record idempotent work order evidence"
git status --short
```

Expected: commit succeeds and final `git status --short` is empty. This is a documentation/evidence checkpoint, not authorization to deploy or begin another project.
