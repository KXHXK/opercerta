# OperCerta Reliability Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以严格 TDD 建立 OperCerta 的可靠性内核，依次证明非法输入被拒绝、恢复决策确定、审批竞态只接受一次、并发幂等写入只产生一个模拟工单，并用 PostgreSQL LangGraph 检查点验证四个重启点。

**Architecture:** 领域契约与恢复决策保持纯 Python/Pydantic；审批、工单和审计的事务语义由 PostgreSQL Repository 保证；LangGraph 只保存可序列化控制流状态，并通过独立 `langgraph` Schema 的 `AsyncPostgresSaver` 恢复。节点允许至少执行一次，唯一约束、行锁和可重入 Repository 保证业务效果有效一次。

**Tech Stack:** Python 3.12.13、uv、Pydantic v2、SQLAlchemy 2 Core、Psycopg 3、Alembic、PostgreSQL 18、LangGraph 1.2、LangGraph PostgreSQL Checkpointer、Pytest/pytest-asyncio。

## Global Constraints

- 只实施 `D:\CODEX\agent-portfolio\opercerta`，本计划结束后发布门禁仍保持关闭，不启动 ForenTrail 或其他项目。
- 全部代码、标识、规则和测试数据从零编写，只使用合成数据，不导入旧公司源码、表结构、接口、规则值、截图或品牌材料。
- 性能、准确率、成本、稳定性数字只有在固定数据集和脚本实测后才能作为结果；本计划只报告测试事实。
- Python 固定为 `>=3.12,<3.13`；本机安装 `3.12.13`，依赖由 `uv.lock` 完整锁定。
- LangGraph 检查点位于 `langgraph` Schema；业务事实位于 `public` Schema；不宣称跨 Schema exactly-once。
- `LANGGRAPH_STRICT_MSGPACK=true`；检查点首次使用必须执行 `setup()`。
- 写操作必须已有原子落库的批准决定；重复审批返回冲突；同一 operation 的模拟工单最多一行。
- 每个生产行为先写一个能因缺失行为而失败的测试，观察 RED 后只写使其通过的最小代码，再做保持全绿的重构。
- 当前工作站已核验：Windows 原生 PostgreSQL `18.4` 服务 `postgresql-x64-18` 运行于 `127.0.0.1:55432`，普通 IPv4 回环连接使用 SCRAM；Task 3–6 的本地前置条件是 `pg_isready -h 127.0.0.1 -p 55432` 成功及已忽略 `.env.local` 提供 `OPERCERTA_DATABASE_URL`。Docker/Redis 不作为当前开发前置条件，Linux/Docker 一致性验证保留为发布门禁。

## Official Dependency Lock Decision (verified 2026-07-14)

| Dependency | Selected version | Decision |
| --- | ---: | --- |
| Python | 3.12.13 | 保持冻结规格的 3.12 系列；该版本是当前 3.12 安全发布 |
| uv | 0.11.28 | 用统一 lock/sync；本机 0.11.27 在执行前升级一补丁 |
| FastAPI | 0.139.0 | 当前稳定发布；要求 Pydantic `>=2.9.0` |
| Pydantic | 2.13.4 | 同时满足 FastAPI、LangGraph 和 MCP v1 |
| pydantic-settings | 2.14.2 | 满足 FastAPI/MCP 设置契约 |
| Uvicorn | 0.51.0 | 独立锁定 `standard` extra，避免依赖隐式漂移 |
| LangGraph | 1.2.9 | 当前稳定线，支持 Python 3.12、持久化和 interrupt/resume |
| langgraph-checkpoint-postgres | 3.1.0 | 与 LangGraph 共同要求 `langgraph-checkpoint>=4.1,<5` |
| MCP Python SDK | 1.28.1 | 唯一生产推荐稳定线；使用 `mcp.server.fastmcp.FastMCP`，固定 `<2` |
| standalone fastmcp | 不安装 | 3.4.4 是独立项目，不替换冻结设计指定的官方 MCP SDK |
| SQLAlchemy | 2.0.51 | 稳定 2.0 线；不采用 2.1 beta |
| Alembic | 1.18.5 | 当前稳定线，支持 SQLAlchemy 2.0 和 Python 3.12 |
| Psycopg | 3.3.4 | 使用 `[binary,pool]`；checkpoint 包要求 `>=3.2.0` |
| redis-py | 8.0.1 | 当前客户端；支持 Redis 8.8 |
| HTTPX | 0.28.1 | 满足 MCP `>=0.27.1,<1` |
| PyJWT | 2.13.0 | 演示 JWT 的稳定实现；认证不进入本计划行为代码 |
| sse-starlette | 3.4.5 | 后续审计 SSE 使用，先进入锁文件 |
| prometheus-client | 0.25.0 | 后续业务/技术指标使用，先进入锁文件 |
| pytest | 9.1.1 | Python 3.12 支持 |
| pytest-asyncio | 1.4.0 | 严格 asyncio 测试模式 |
| Ruff | 0.15.21 | 格式与静态规则 |
| mypy | 2.3.0 | 严格类型检查 |
| PostgreSQL local development | `18.4` Windows x86-64 installer | 当前本机服务仅监听 `127.0.0.1:55432`；凭据仅在已忽略 `.env.local` |
| PostgreSQL release image | `postgres:18.4-bookworm` | 后续 Linux/Docker 发布门禁使用；不是当前 Task 3 前置条件 |
| Redis image | `redis:8.8.0-trixie` | 后续发布阶段再启用；不在当前 Task 3 启动 |

Primary sources:

- https://www.python.org/downloads/release/python-31213/
- https://pypi.org/project/uv/
- https://pypi.org/project/fastapi/
- https://pypi.org/project/pydantic/
- https://pypi.org/project/langgraph/
- https://pypi.org/project/langgraph-checkpoint-postgres/
- https://pypi.org/project/mcp/
- https://github.com/modelcontextprotocol/python-sdk
- https://pypi.org/project/SQLAlchemy/
- https://pypi.org/project/alembic/
- https://pypi.org/project/psycopg/
- https://www.postgresql.org/download/windows/
- https://www.enterprisedb.com/docs/supported-open-source/postgresql/installing/windows/
- https://hub.docker.com/_/postgres/
- https://hub.docker.com/_/redis/

## File Map

| Path | Responsibility |
| --- | --- |
| `pyproject.toml`, `.python-version`, `uv.lock` | Python 版本、直接依赖、测试/格式/类型配置与完整解析结果 |
| `src/opercerta/domain/contracts.py` | API/模型进入领域前的严格输入契约 |
| `src/opercerta/domain/errors.py` | 稳定领域错误码和异常类型 |
| `src/opercerta/domain/recovery.py` | 不访问数据库的恢复决策矩阵 |
| `src/opercerta/infrastructure/db/schema.py` | SQLAlchemy Core 表声明 |
| `src/opercerta/infrastructure/db/engine.py` | 业务库 Engine 生命周期 |
| `src/opercerta/infrastructure/db/approval_repository.py` | 行锁、唯一决定、状态和审计同事务 |
| `src/opercerta/infrastructure/db/work_order_repository.py` | 参数哈希、唯一幂等键、重复回放与审批校验 |
| `src/opercerta/infrastructure/checkpoints.py` | 独立 Schema 的 AsyncPostgresSaver 初始化 |
| `src/opercerta/workflow/reliability_graph.py` | 最小 interrupt → execute → verify/reject 图 |
| `src/opercerta/workflow/recovery_coordinator.py` | 组合业务事实、图快照和恢复动作 |
| `migrations/versions/0001_reliability_kernel.py` | 业务表、约束、索引和 `langgraph` Schema |
| `tests/unit/domain/` | 非法输入和恢复矩阵的纯单元测试 |
| `tests/integration/db/` | PostgreSQL 审批竞态与幂等写入测试 |
| `tests/integration/workflow/` | 四个重启点与检查点/业务事实协同测试 |
| `docs/release-evidence/reliability-kernel.md` | RED/GREEN 命令、测试数量、环境与未通过门禁 |

---

### Task 1: Dependency lock and illegal-input contracts

**Files:**
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `src/opercerta/__init__.py`
- Create: `src/opercerta/domain/__init__.py`
- Create: `src/opercerta/domain/contracts.py`
- Test: `tests/unit/domain/test_operation_request.py`

**Interfaces:**
- Produces: `ActionType`, `ObjectType`, `OperationRequest`.
- `OperationRequest.model_validate(payload)` either returns a frozen validated model or raises `pydantic.ValidationError`.

- [ ] **Step 1: Install the exact interpreter and create the lock configuration**

Run:

```powershell
uv self update
uv python install 3.12.13
```

Expected: `uv --version` reports `0.11.28`; `uv run python --version` reports `Python 3.12.13` after the following files exist.

Write `.python-version`:

```text
3.12.13
```

Write `pyproject.toml` with these exact direct constraints:

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "opercerta"
version = "0.1.0"
description = "Controlled, auditable operations workflow agent"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic==1.18.5",
  "fastapi==0.139.0",
  "httpx==0.28.1",
  "langgraph==1.2.9",
  "langgraph-checkpoint-postgres==3.1.0",
  "mcp==1.28.1",
  "prometheus-client==0.25.0",
  "psycopg[binary,pool]==3.3.4",
  "pydantic==2.13.4",
  "pydantic-settings==2.14.2",
  "pyjwt[crypto]==2.13.0",
  "redis[hiredis]==8.0.1",
  "sqlalchemy==2.0.51",
  "sse-starlette==3.4.5",
  "uvicorn[standard]==0.51.0",
]

[dependency-groups]
dev = [
  "mypy==2.3.0",
  "pytest==9.1.1",
  "pytest-asyncio==1.4.0",
  "ruff==0.15.21",
]

[tool.hatch.build.targets.wheel]
packages = ["src/opercerta"]

[tool.pytest.ini_options]
addopts = "-ra --strict-config --strict-markers"
asyncio_mode = "strict"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
packages = ["opercerta"]
```

Create only empty package marker files, then run:

```powershell
uv lock
uv sync --all-groups
uv run python -c "from importlib.metadata import version; names=['fastapi','pydantic','langgraph','langgraph-checkpoint-postgres','mcp','sqlalchemy','psycopg']; print({name: version(name) for name in names})"
```

Expected: resolution succeeds and the printed versions exactly match the table above.

- [ ] **Step 2: RED — reject a blank natural-language request**

Write the first test so a missing contract is an assertion failure rather than a collection error:

```python
from importlib import import_module

import pytest
from pydantic import ValidationError


def operation_request_type():
    try:
        return import_module("opercerta.domain.contracts").OperationRequest
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"OperationRequest is unavailable: {exc}", pytrace=False)


def test_blank_message_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate({"message": "   "})
```

Run:

```powershell
uv run pytest tests/unit/domain/test_operation_request.py::test_blank_message_is_rejected -q
```

Expected RED: `FAILED` with `OperationRequest is unavailable`.

- [ ] **Step 3: GREEN — implement only the constrained message**

Write `src/opercerta/domain/contracts.py`:

```python
from typing import Annotated

from pydantic import BaseModel, StringConstraints

Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]


class OperationRequest(BaseModel):
    message: Message
```

Run the same test. Expected GREEN: `1 passed`.

- [ ] **Step 4: RED/GREEN — forbid undeclared fields**

Add:

```python
def test_undeclared_field_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate({"message": "check stock", "shell": "whoami"})
```

Expected RED before implementation: the model accepts and ignores `shell`.

Add to `OperationRequest`:

```python
from pydantic import ConfigDict


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: Message
```

Expected GREEN: both tests pass.

- [ ] **Step 5: RED/GREEN — allow only declared actions and object types**

Add tests in this order: a known action is accepted; then an unknown action is rejected.

```python
def test_known_action_is_accepted() -> None:
    operation_request = operation_request_type()

    request = operation_request.model_validate(
        {"message": "create a repair order", "requested_action": "create_work_order"}
    )

    assert request.requested_action.value == "create_work_order"


def test_unknown_action_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate(
            {"message": "delete inventory", "requested_action": "delete_inventory"}
        )
```

Expected first RED: `requested_action` is forbidden. Add `ActionType` and the field; then observe the second test RED if the field is temporarily `str`; replace it with the enum:

```python
from enum import StrEnum


class ActionType(StrEnum):
    QUERY = "query"
    CREATE_WORK_ORDER = "create_work_order"


class ObjectType(StrEnum):
    INVENTORY = "inventory"
    EQUIPMENT = "equipment"


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: Message
    requested_action: ActionType | None = None
    object_type: ObjectType | None = None
    object_id: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    ] | None = None
```

Expected GREEN: known action accepted, unknown action rejected.

- [ ] **Step 6: RED/GREEN — require object type and identifier as a pair**

Add:

```python
@pytest.mark.parametrize(
    "payload",
    [
        {"message": "check stock", "object_type": "inventory"},
        {"message": "check stock", "object_id": "SKU-DEMO-001"},
    ],
)
def test_partial_object_reference_is_rejected(payload: dict[str, str]) -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate(payload)
```

Expected RED: both payloads validate. Add:

```python
from typing import Self

from pydantic import model_validator


@model_validator(mode="after")
def require_complete_object_reference(self: Self) -> Self:
    if (self.object_type is None) != (self.object_id is None):
        raise ValueError("object_type and object_id must be provided together")
    return self
```

Place the validator inside `OperationRequest`. Run:

```powershell
uv run pytest tests/unit/domain/test_operation_request.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit the independently testable contract**

```powershell
git add .python-version pyproject.toml uv.lock src/opercerta tests/unit/domain/test_operation_request.py
git commit -m "feat: add strict operation input contract"
```

---

### Task 2: Deterministic recovery decision matrix

**Files:**
- Create: `src/opercerta/domain/errors.py`
- Create: `src/opercerta/domain/recovery.py`
- Test: `tests/unit/domain/test_recovery.py`

**Interfaces:**
- Consumes: persisted operation status, checkpoint phase, optional approval and optional work-order ID.
- Produces: `RecoveryAction` from `choose_recovery_action(facts: RecoveryFacts) -> RecoveryAction`.

- [ ] **Step 1: RED — encode every frozen-spec recovery case as a table**

```python
from importlib import import_module

import pytest


def recovery_module():
    try:
        return import_module("opercerta.domain.recovery")
    except ImportError as exc:
        pytest.fail(f"recovery module is unavailable: {exc}", pytrace=False)


@pytest.mark.parametrize(
    ("status", "checkpoint", "has_approval", "has_work_order", "expected"),
    [
        ("received", "missing", False, False, "rebuild_from_business_facts"),
        ("awaiting_approval", "interrupted", False, False, "keep_waiting"),
        ("resuming", "interrupted", True, False, "resume_decision"),
        ("executing", "runnable", True, False, "replay_idempotent_execution"),
        ("verifying", "runnable", True, True, "verify_existing_work_order"),
        ("planning", "runnable", False, False, "continue_checkpoint"),
        ("completed", "runnable", True, True, "no_op"),
        ("rejected", "missing", True, False, "no_op"),
        ("expired", "interrupted", False, False, "no_op"),
        ("failed", "runnable", False, False, "no_op"),
    ],
)
def test_recovery_matrix(
    status: str,
    checkpoint: str,
    has_approval: bool,
    has_work_order: bool,
    expected: str,
) -> None:
    recovery = recovery_module()
    facts = recovery.RecoveryFacts(
        status=recovery.OperationStatus(status),
        checkpoint=recovery.CheckpointPhase(checkpoint),
        has_approval=has_approval,
        has_work_order=has_work_order,
    )

    assert recovery.choose_recovery_action(facts).value == expected
```

Run the first parameter only. Expected RED: module unavailable.

- [ ] **Step 2: GREEN — implement exhaustive, side-effect-free routing**

```python
from dataclasses import dataclass
from enum import StrEnum


class OperationStatus(StrEnum):
    RECEIVED = "received"
    GATHERING_EVIDENCE = "gathering_evidence"
    PLANNING = "planning"
    VALIDATING = "validating"
    REPORTING = "reporting"
    AWAITING_APPROVAL = "awaiting_approval"
    RESUMING = "resuming"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class CheckpointPhase(StrEnum):
    MISSING = "missing"
    INTERRUPTED = "interrupted"
    RUNNABLE = "runnable"


class RecoveryAction(StrEnum):
    REBUILD_FROM_BUSINESS_FACTS = "rebuild_from_business_facts"
    KEEP_WAITING = "keep_waiting"
    RESUME_DECISION = "resume_decision"
    REPLAY_IDEMPOTENT_EXECUTION = "replay_idempotent_execution"
    VERIFY_EXISTING_WORK_ORDER = "verify_existing_work_order"
    CONTINUE_CHECKPOINT = "continue_checkpoint"
    NO_OP = "no_op"


TERMINAL_STATUSES = frozenset(
    {
        OperationStatus.COMPLETED,
        OperationStatus.REJECTED,
        OperationStatus.EXPIRED,
        OperationStatus.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class RecoveryFacts:
    status: OperationStatus
    checkpoint: CheckpointPhase
    has_approval: bool
    has_work_order: bool


def choose_recovery_action(facts: RecoveryFacts) -> RecoveryAction:
    if facts.status in TERMINAL_STATUSES:
        return RecoveryAction.NO_OP
    if facts.checkpoint is CheckpointPhase.MISSING:
        return RecoveryAction.REBUILD_FROM_BUSINESS_FACTS
    if facts.checkpoint is CheckpointPhase.INTERRUPTED:
        return (
            RecoveryAction.RESUME_DECISION
            if facts.has_approval
            else RecoveryAction.KEEP_WAITING
        )
    if facts.has_work_order:
        return RecoveryAction.VERIFY_EXISTING_WORK_ORDER
    if facts.status in {OperationStatus.RESUMING, OperationStatus.EXECUTING, OperationStatus.VERIFYING}:
        return RecoveryAction.REPLAY_IDEMPOTENT_EXECUTION
    return RecoveryAction.CONTINUE_CHECKPOINT
```

Run the entire test table. Expected GREEN: `10 passed`.

- [ ] **Step 3: RED/GREEN — reject impossible recovery facts**

Add tests that an approval cannot exist in `received`, and a work order cannot exist without approval. Add `InvalidRecoveryFacts` in `domain/errors.py`, validate these combinations in `RecoveryFacts.__post_init__`, and keep terminal rows valid. Error messages must include `approval_without_approval_state` or `work_order_without_approval` so the coordinator can audit the exact reason.

Run:

```powershell
uv run pytest tests/unit/domain/test_recovery.py -q
uv run ruff check src tests
uv run mypy src
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit the pure recovery policy**

```powershell
git add src/opercerta/domain tests/unit/domain/test_recovery.py
git commit -m "feat: add deterministic recovery policy"
```

---

### Task 3: PostgreSQL schema and atomic approval race

**Precondition:** `C:\Program Files\PostgreSQL\18\bin\pg_isready.exe -h 127.0.0.1 -p 55432` must report `accepting connections`, and ignored `.env.local` must contain `OPERCERTA_DATABASE_URL`. If either check fails, stop here without writing database production code; unit Task 1–2 remain valid but the concurrency claim is unproven.

**Files:**
- Create: `src/opercerta/domain/approvals.py`
- Modify: `src/opercerta/domain/errors.py`
- Test: `tests/unit/domain/test_approvals.py`
- Create: `.env.example`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_reliability_kernel.py`
- Create: `src/opercerta/infrastructure/db/schema.py`
- Create: `src/opercerta/infrastructure/db/engine.py`
- Create: `src/opercerta/infrastructure/db/approval_repository.py`
- Test: `tests/integration/conftest.py`
- Test: `tests/integration/db/test_migration.py`
- Test: `tests/integration/db/test_approval_race.py`

**Interfaces:**
- Produces: `ApprovalDecision(StrEnum)` with exactly `APPROVED = "approved"` and `REJECTED = "rejected"`.
- Produces: immutable `ApprovalCommand(operation_id: UUID, approver_id: str, decision: ApprovalDecision, reason: str)`; extra fields are forbidden, identifiers/reasons are stripped and non-empty.
- Produces: immutable `ApprovalRecord` with the command fields plus `id: UUID` and timezone-aware `created_at: datetime`.
- Produces: `OperationNotFound(operation_id)` with code `operation_not_found` and `ApprovalAlreadyDecided(operation_id)` with code `approval_already_decided`.
- Produces: `ApprovalRepository.submit_once(command: ApprovalCommand) -> ApprovalRecord`.
- Atomic postcondition: one `approvals` row, operation state `resuming`, one ordered `approval_recorded` audit event.
- Conflict: `ApprovalAlreadyDecided` with code `approval_already_decided`.

The approved contract source of truth is `docs/superpowers/specs/2026-07-15-approval-domain-contract-design.md`. Both approved and rejected decisions first enter `resuming`; the later workflow recovery node routes the stored decision to `executing` or `rejected`.

- [x] **Step 1: Verify the isolated native PostgreSQL service**

Run without printing `.env.local`:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 55432
$line = Get-Content -LiteralPath .env.local |
    Where-Object { $_.StartsWith('OPERCERTA_DATABASE_URL=') } |
    Select-Object -First 1
if (-not $line) { throw 'OPERCERTA_DATABASE_URL is missing from .env.local.' }
$env:OPERCERTA_DATABASE_URL = $line.Substring('OPERCERTA_DATABASE_URL='.Length)
uv run python -c "import os; from sqlalchemy import create_engine, text; e=create_engine(os.environ['OPERCERTA_DATABASE_URL']); c=e.connect(); print(c.execute(text('select current_database(), current_user, inet_server_addr()::text, inet_server_port()')).one()); c.close(); e.dispose()"
Remove-Item Env:OPERCERTA_DATABASE_URL
```

Expected: PostgreSQL reports `accepting connections`; the SQL probe returns `opercerta_test`, `opercerta`, `127.0.0.1/32`, and `55432`. Redis and Docker are not started in this task.

- [x] **Step 2: RED — define the approval domain contract**

Create `tests/unit/domain/test_approvals.py`:

```python
from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.approvals import (
    ApprovalCommand,
    ApprovalDecision,
    ApprovalRecord,
)
from opercerta.domain.errors import ApprovalAlreadyDecided, OperationNotFound


OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")
APPROVAL_ID = UUID("00000000-0000-4000-8000-000000000002")


def valid_command_data() -> dict[str, object]:
    return {
        "operation_id": OPERATION_ID,
        "approver_id": "approver-1",
        "decision": ApprovalDecision.APPROVED,
        "reason": "synthetic approval reason",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approver_id", "   "),
        ("approver_id", "a" * 129),
        ("decision", "unknown"),
        ("reason", "   "),
        ("reason", "r" * 1_001),
    ],
)
def test_approval_command_rejects_invalid_fields(field: str, value: object) -> None:
    data = valid_command_data()
    data[field] = value

    with pytest.raises(ValidationError):
        ApprovalCommand.model_validate(data)


def test_approval_command_rejects_extra_fields() -> None:
    data = valid_command_data()
    data["role"] = "approver"

    with pytest.raises(ValidationError):
        ApprovalCommand.model_validate(data)


def test_approval_command_strips_human_text() -> None:
    command = ApprovalCommand(
        operation_id=OPERATION_ID,
        approver_id="  approver-1  ",
        decision=ApprovalDecision.REJECTED,
        reason="  synthetic rejection reason  ",
    )

    assert command.approver_id == "approver-1"
    assert command.reason == "synthetic rejection reason"


def test_approval_command_is_immutable() -> None:
    command = ApprovalCommand.model_validate(valid_command_data())

    with pytest.raises(ValidationError, match="Instance is frozen"):
        command.reason = "changed after validation"


def test_approval_record_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValidationError, match="created_at must include timezone"):
        ApprovalRecord(
            id=APPROVAL_ID,
            **valid_command_data(),
            created_at=datetime(2026, 7, 15, 12, 0),
        )


def test_approval_errors_expose_stable_codes() -> None:
    not_found = OperationNotFound(OPERATION_ID)
    conflict = ApprovalAlreadyDecided(OPERATION_ID)

    assert not_found.code == "operation_not_found"
    assert not_found.operation_id == OPERATION_ID
    assert conflict.code == "approval_already_decided"
    assert conflict.operation_id == OPERATION_ID
```

- [x] **Step 3: Run the domain contract test to verify RED**

Run:

```powershell
uv run pytest tests/unit/domain/test_approvals.py -q
```

Expected RED: collection fails because `opercerta.domain.approvals` and the two stable errors do not exist. Fix only test syntax/import mistakes if the failure is unrelated; do not write production code until the missing-contract failure is observed.

- [x] **Step 4: GREEN — implement the minimal immutable contract and stable errors**

Create `src/opercerta/domain/approvals.py`:

```python
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


ApproverId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
ApprovalReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    approver_id: ApproverId
    decision: ApprovalDecision
    reason: ApprovalReason


class ApprovalRecord(ApprovalCommand):
    id: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include timezone")
        return value
```

Add the imports and two classes to `src/opercerta/domain/errors.py` without changing `InvalidRecoveryFacts`:

```python
from uuid import UUID


class OperationNotFound(LookupError):
    code = "operation_not_found"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)


class ApprovalAlreadyDecided(RuntimeError):
    code = "approval_already_decided"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)
```

- [x] **Step 5: Verify the domain contract is GREEN and commit it**

Run:

```powershell
uv run pytest tests/unit/domain/test_approvals.py -q
uv run pytest tests/unit -q
uv run ruff check src/opercerta/domain tests/unit/domain
uv run mypy
```

Expected: every command exits 0, with no warnings. Then commit only this contract slice:

```powershell
git add src/opercerta/domain/approvals.py src/opercerta/domain/errors.py tests/unit/domain/test_approvals.py
git commit -m "feat: define approval domain contract"
```

- [ ] **Step 6: RED — prove the database migration contract is absent**

Create `tests/integration/conftest.py` with a secret-safe local URL fixture:

```python
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    configured = os.getenv("OPERCERTA_DATABASE_URL")
    if configured:
        return configured

    local_env = ROOT / ".env.local"
    if local_env.is_file():
        for raw_line in local_env.read_text(encoding="utf-8").splitlines():
            name, separator, value = raw_line.partition("=")
            if name == "OPERCERTA_DATABASE_URL" and separator and value:
                return value

    pytest.fail("OPERCERTA_DATABASE_URL is not configured for integration tests")


@pytest.fixture(scope="session")
def database_url() -> str:
    return _database_url()
```

Create `tests/integration/db/test_migration.py`:

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[3]


def test_reliability_kernel_migration_creates_required_schema(
    database_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPERCERTA_DATABASE_URL", database_url)
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {
            "operations",
            "approvals",
            "work_orders",
            "audit_events",
        } <= set(inspector.get_table_names(schema="public"))
        assert "langgraph" in inspector.get_schema_names()
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("approvals")
        } == {"uq_approvals_operation_id"}
    finally:
        engine.dispose()
```

Run:

```powershell
uv run pytest tests/integration/db/test_migration.py -q
```

Expected RED: Alembic raises `CommandError: No 'script_location' key found in configuration` because `alembic.ini` and the migration do not exist. The fixture must not print or embed the database URL.

- [ ] **Step 7: GREEN — add the migration before the race implementation**

The migration must create `public.operations`, `public.approvals`, `public.work_orders`, `public.audit_events`, and `langgraph` Schema. Exact constraints:

```python
op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
op.create_unique_constraint("uq_operations_thread_id", "operations", ["thread_id"])
op.create_unique_constraint("uq_approvals_operation_id", "approvals", ["operation_id"])
op.create_unique_constraint("uq_work_orders_operation_id", "work_orders", ["operation_id"])
op.create_unique_constraint("uq_work_orders_idempotency_key", "work_orders", ["idempotency_key"])
op.create_unique_constraint(
    "uq_audit_events_operation_sequence", "audit_events", ["operation_id", "sequence"]
)
```

Use PostgreSQL UUID, JSONB and timezone-aware timestamps. `operations` contains `id`, `thread_id`, `request_payload`, `status`, `next_audit_sequence`, `created_at`, `updated_at`; `approvals` contains one decision per operation; `work_orders` contains payload plus SHA-256; `audit_events` is append-only by application policy.

Run:

```powershell
$line = Get-Content -LiteralPath .env.local |
    Where-Object { $_.StartsWith('OPERCERTA_DATABASE_URL=') } |
    Select-Object -First 1
if (-not $line) { throw 'OPERCERTA_DATABASE_URL is missing from .env.local.' }
$env:OPERCERTA_DATABASE_URL = $line.Substring('OPERCERTA_DATABASE_URL='.Length)
uv run alembic upgrade head
uv run alembic current
Remove-Item Env:OPERCERTA_DATABASE_URL
```

Expected: current revision is `0001_reliability_kernel`.

- [ ] **Step 8: RED — race ten decisions through independent connections**

Create an `awaiting_approval` operation, then start ten tasks with five approvals and five rejections:

```python
results = await asyncio.gather(
    *[
        repository.submit_once(
            ApprovalCommand(
                operation_id=operation_id,
                approver_id=f"approver-{index}",
                decision=ApprovalDecision.APPROVED if index % 2 == 0 else ApprovalDecision.REJECTED,
                reason=f"synthetic decision {index}",
            )
        )
        for index in range(10)
    ],
    return_exceptions=True,
)

accepted = [result for result in results if isinstance(result, ApprovalRecord)]
conflicts = [result for result in results if isinstance(result, ApprovalAlreadyDecided)]
assert len(accepted) == 1
assert len(conflicts) == 9
assert len(accepted) + len(conflicts) == len(results)
assert await count_rows(engine, "approvals", operation_id) == 1
assert await operation_status(engine, operation_id) == "resuming"
assert await audit_types(engine, operation_id) == ["approval_recorded"]
```

Run the test. Expected RED: repository import is unavailable.

- [ ] **Step 9: GREEN — serialize on the operation row and commit all effects together**

Implement `submit_once` with one `engine.begin()` transaction:

```python
async with self._engine.begin() as connection:
    operation = (
        await connection.execute(
            select(operations)
            .where(operations.c.id == command.operation_id)
            .with_for_update()
        )
    ).mappings().one_or_none()
    if operation is None:
        raise OperationNotFound(command.operation_id)

    existing = (
        await connection.execute(
            select(approvals).where(approvals.c.operation_id == command.operation_id)
        )
    ).mappings().one_or_none()
    if existing is not None or operation["status"] != "awaiting_approval":
        raise ApprovalAlreadyDecided(command.operation_id)

    approval_id = uuid4()
    created_at = datetime.now(UTC)
    sequence = operation["next_audit_sequence"] + 1
    await connection.execute(insert(approvals).values(
        id=approval_id,
        operation_id=command.operation_id,
        approver_id=command.approver_id,
        decision=command.decision.value,
        reason=command.reason,
        created_at=created_at,
    ))
    await connection.execute(
        update(operations)
        .where(operations.c.id == command.operation_id)
        .values(status="resuming", next_audit_sequence=sequence, updated_at=created_at)
    )
    await connection.execute(insert(audit_events).values(
        id=uuid4(),
        operation_id=command.operation_id,
        sequence=sequence,
        event_type="approval_recorded",
        payload={"approval_id": str(approval_id), "decision": command.decision.value},
        created_at=created_at,
    ))
```

Map `ApprovalAlreadyDecided` to a stable code in `domain/errors.py`; do not catch and retry it.

Run the race test 20 times:

```powershell
1..20 | ForEach-Object { uv run pytest tests/integration/db/test_approval_race.py -q; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
```

Expected GREEN: every run reports one passed test; no deadlock or duplicate row.

- [ ] **Step 10: Commit the approval transaction**

```powershell
git add .env.example alembic.ini migrations src/opercerta/infrastructure tests/integration docs/development-log DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md
git commit -m "feat: make approval decisions atomic"
```

---

### Task 4: Idempotent work-order write under concurrency

**Files:**
- Create: `src/opercerta/domain/work_orders.py`
- Create: `src/opercerta/infrastructure/db/work_order_repository.py`
- Test: `tests/integration/db/test_work_order_idempotency.py`

**Interfaces:**
- Produces: `derive_idempotency_key(operation_id: UUID) -> str`.
- Produces: `WorkOrderRepository.create_or_get(command: WorkOrderCommand) -> WorkOrderWriteResult`.
- `WorkOrderWriteResult.replayed` is false for exactly one first insert and true for safe repeats.
- Same key with a different canonical payload raises `IdempotencyConflict`; missing approved decision raises `WriteNotAuthorized`.

- [ ] **Step 1: RED — define deterministic key and canonical payload tests**

```python
def test_idempotency_key_is_stable_for_operation() -> None:
    operation_id = UUID("00000000-0000-4000-8000-000000000001")

    assert derive_idempotency_key(operation_id) == (
        "work-order:v1:00000000-0000-4000-8000-000000000001"
    )


def test_payload_hash_is_independent_of_dictionary_order() -> None:
    assert hash_payload({"quantity": 4, "sku": "SKU-DEMO-001"}) == hash_payload(
        {"sku": "SKU-DEMO-001", "quantity": 4}
    )
```

Expected RED: module unavailable. Implement the key and SHA-256 over UTF-8 JSON using `sort_keys=True`, `separators=(",", ":")`, and `allow_nan=False`. Expected GREEN: 2 passed.

- [ ] **Step 2: RED — ten simultaneous identical writes produce one row**

Seed an approved `resuming` operation. Open ten independent transactions through the repository and assert:

```python
results = await asyncio.gather(
    *[repository.create_or_get(command) for _ in range(10)]
)

assert sum(not result.replayed for result in results) == 1
assert sum(result.replayed for result in results) == 9
assert len({result.work_order.id for result in results}) == 1
assert await count_work_orders(engine, operation_id) == 1
```

Expected RED: repository unavailable.

- [ ] **Step 3: GREEN — lock the operation, return an existing row, then authorize a new insert**

Inside one `engine.begin()` transaction:

1. Execute `select(operations).where(operations.c.id == command.operation_id).with_for_update()` on the current transaction connection.
2. Query by derived idempotency key.
3. If present, compare `payload_hash`; return it with `replayed=True`, or raise `IdempotencyConflict`.
4. If absent, require exactly one `approved` approval and status in `resuming`, `executing`, `verifying`.
5. Insert one `work_orders` row and one `work_order_created` audit event; advance `next_audit_sequence` in the same transaction.
6. Return `replayed=False`.

Use the database unique constraints as the final collision guard; translate `IntegrityError` by re-reading the existing row in a new transaction and applying the same hash comparison.

Run the concurrency test 20 times. Expected GREEN: exactly one row and one creation event every run.

- [ ] **Step 4: RED/GREEN — distinguish safe replay, payload conflict and approval bypass**

Add three tests:

- identical replay returns the same ID and does not append a second creation audit event;
- same operation/key with changed `quantity` raises `IdempotencyConflict`;
- operation without an approved decision raises `WriteNotAuthorized`, leaves work-order count zero, and appends no write-success event.

Run:

```powershell
uv run pytest tests/integration/db/test_work_order_idempotency.py -q
uv run pytest tests/integration/db -q
```

Expected: all tests pass; the bypass count is zero by row-count assertion, not by a claimed metric.

- [ ] **Step 5: Commit the idempotent write boundary**

```powershell
git add src/opercerta/domain src/opercerta/infrastructure/db tests/integration/db
git commit -m "feat: make simulated work orders idempotent"
```

---

### Task 5: LangGraph interrupt and four-point restart recovery

**Files:**
- Create: `src/opercerta/infrastructure/checkpoints.py`
- Create: `src/opercerta/workflow/__init__.py`
- Create: `src/opercerta/workflow/reliability_graph.py`
- Create: `src/opercerta/workflow/recovery_coordinator.py`
- Test: `tests/integration/workflow/test_restart_recovery.py`

**Interfaces:**
- Produces: `build_reliability_graph(checkpointer, work_orders) -> CompiledStateGraph`.
- Produces: `RecoveryCoordinator.recover(operation_id: UUID) -> RecoveryAction`.
- Uses the operation UUID string as both stable `thread_id` and business lookup key; it stays under the documented 255-character checkpoint limit.

- [ ] **Step 1: RED — pause before every external write**

Create an `awaiting_approval` operation, invoke the graph with its business facts and assert `__interrupt__` exists, operation status remains `awaiting_approval`, and work-order count remains zero.

Expected RED: graph builder unavailable.

- [ ] **Step 2: GREEN — build the smallest JSON-only graph**

Use a `TypedDict` containing only strings, booleans and dictionaries. The approval node performs no side effect before `interrupt()`:

```python
def request_approval(state: ReliabilityState) -> dict[str, object]:
    decision = interrupt(
        {
            "operation_id": state["operation_id"],
            "risk": state["risk"],
            "plan": state["plan"],
        }
    )
    return {"approval": decision}
```

Route an approved decision to async `execute_work_order`, a rejected decision to `mark_rejected`, then verify by re-reading the repository result. Never place Engine, connection, exception, secret or client objects in state.

Expected GREEN: graph pauses, no write occurs.

- [ ] **Step 3: Configure the durable checkpointer exactly once per database**

Derive the checkpointer DSN from ignored `.env.local` without printing the base URL:

```powershell
$line = Get-Content -LiteralPath .env.local |
    Where-Object { $_.StartsWith('OPERCERTA_DATABASE_URL=') } |
    Select-Object -First 1
if (-not $line) { throw 'OPERCERTA_DATABASE_URL is missing from .env.local.' }
$checkpointDsn = ($line.Substring('OPERCERTA_DATABASE_URL='.Length) -replace '^postgresql\+psycopg://', 'postgresql://') + '?options=-c%20search_path%3Dlanggraph'
```

Use:

```python
async with AsyncPostgresSaver.from_conn_string(checkpoint_dsn) as checkpointer:
    await checkpointer.setup()
```

Set `LANGGRAPH_STRICT_MSGPACK=true` in `.env.example` and the integration test process. Do not share the business SQLAlchemy transaction with checkpoint writes.

- [ ] **Step 4: RED/GREEN — restart while awaiting approval**

1. Build graph instance A and invoke to interrupt.
2. Dispose instance A.
3. Build graph instance B against the same database.
4. Call recovery with no decision.
5. Assert action `keep_waiting`, no automatic approval and no work order.

Expected RED before coordinator logic: it attempts to continue or cannot classify the checkpoint. Implement snapshot inspection plus `choose_recovery_action`; expected GREEN: waiting is preserved.

- [ ] **Step 5: RED/GREEN — restart after approval commit but before graph resume**

Record an approval through Task 3, dispose all graph objects, create a new coordinator, and recover. It must read the original decision and invoke:

```python
await graph.ainvoke(
    Command(resume={"decision": approval.decision.value, "approval_id": str(approval.id)}),
    config={"configurable": {"thread_id": str(operation_id)}},
)
```

Assert one work order, status `completed`, and no second approval. Expected RED before resume logic; GREEN after it uses the stored decision.

- [ ] **Step 6: RED/GREEN — restart after the work-order write but before its graph checkpoint**

From an interrupted graph:

1. Commit approval.
2. Call `WorkOrderRepository.create_or_get` directly to represent a crash after the external effect.
3. Dispose graph/checkpointer.
4. Resume from the stale interrupt with a new process-equivalent graph instance.
5. Assert the execute node returns the original work-order ID with `replayed=True` and total rows remain one.

This test must fail if the execute node uses a random idempotency key.

- [ ] **Step 7: RED/GREEN — rebuild when the business row exists before the first checkpoint**

Insert an operation business row with persisted request/risk/plan and do not invoke the graph. Recovery must choose `rebuild_from_business_facts`, construct the initial JSON state from those persisted fields, and reach the approval interrupt. It must not call a model or fabricate missing fields.

- [ ] **Step 8: Run the complete restart matrix repeatedly**

```powershell
1..10 | ForEach-Object { uv run pytest tests/integration/workflow/test_restart_recovery.py -q; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
uv run pytest tests/unit tests/integration -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Expected: every command exits 0; every repeated run keeps one approval and at most one work order.

- [ ] **Step 9: Commit the recovery integration**

```powershell
git add src/opercerta/infrastructure/checkpoints.py src/opercerta/workflow tests/integration/workflow .env.example
git commit -m "feat: recover approval workflows after restart"
```

---

### Task 6: Reliability-kernel evidence and gate handoff

**Files:**
- Create: `docs/release-evidence/reliability-kernel.md`
- Modify: `README.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`

**Interfaces:**
- Produces: a reproducible command record; it does not mark OperCerta released.
- Produces: the next OperCerta-only implementation boundary: MCP tools and the full event → evidence → plan → approval → write → audit API slice.

- [ ] **Step 1: Run fresh full verification**

```powershell
uv sync --frozen --all-groups
uv run pytest tests/unit tests/integration -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run alembic downgrade base
uv run alembic upgrade head
uv run pytest tests/integration -q
git diff --check
git status --short
```

Expected: commands through `git diff --check` exit 0. `git status --short` may list only the documentation changes made in this task.

- [ ] **Step 2: Record only observed facts**

Write the exact timestamp, Git commit, OS/Python/PostgreSQL versions, commands, exit codes, collected/passed test counts, and the four restart scenarios. State explicitly:

```text
OperCerta release gate: CLOSED
Verified scope: reliability kernel only
Unverified scope: full five-tool MCP service, complete workflow, API/SSE, React UI, fixed 30-case evaluation, real-model representative paths, public deployment
Next project permitted: no
```

Do not copy planned thresholds into a results column.

- [ ] **Step 3: Update repository status without claiming release**

README must say “可靠性内核已验证” only if Step 1 passed freshly. HANDOFF must point to the evidence file and state that the next work remains OperCerta MCP/full vertical slice.

- [ ] **Step 4: Commit documentation and stop at the OperCerta boundary**

```powershell
git add README.md IMPLEMENTATION_HANDOFF.md docs/release-evidence/reliability-kernel.md
git commit -m "docs: record reliability kernel evidence"
git status --short --branch
```

Expected: clean working tree on `main`. Do not create a release tag, public deployment claim, portfolio metric or another project directory from this plan.

## Plan Self-Review

- Spec coverage: the plan maps directly to illegal input, state recovery, approval race and idempotent write requirements, plus all four documented restart points.
- Scope: MCP tool implementation, complete API/UI, 30-case evaluation and public release are deliberately outside this independently testable increment; their absence keeps the release gate closed.
- Type consistency: `OperationStatus`, `RecoveryAction`, `ApprovalCommand`, `ApprovalRecord`, `WorkOrderCommand` and `WorkOrderWriteResult` are defined once and consumed by later tasks under the same names.
- Truthfulness: every numerical statement is a test cardinality or official dependency version; no performance or quality target is presented as achieved.
- Environment: native PostgreSQL 18.4 at `127.0.0.1:55432` is the local Task 3 prerequisite; Linux/Docker verification remains a release-gate requirement and is surfaced before any release claim.
