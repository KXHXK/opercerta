# OperCerta Inventory Replenishment Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实 FastMCP Streamable HTTP 工具、确定性库存规则、人工审批、幂等模拟工单、回读验证和 FastAPI 接口，贯通“库存不足 → 补货工单”的第一个 OperCerta 后端纵向业务闭环。

**Architecture:** FastAPI 持久化请求并驱动 `OperationRunner`，LangGraph 通过固定 allowlist 的 `McpToolGateway` 调用独立 FastMCP 服务；业务事实位于 PostgreSQL `public` Schema，控制流快照位于 `langgraph` Schema。Mock 模型只提供受约束说明，库存、规则、补货量、审批和写权限全部由确定性领域服务与现有可靠性内核控制。

**Tech Stack:** Python 3.12.13、Pydantic 2.13.4、SQLAlchemy 2.0.51 Core async、Psycopg 3.3.4、PostgreSQL 18.4、Alembic 1.18.5、MCP Python SDK 1.28.1、FastAPI 0.139.0、HTTPX 0.28.1、LangGraph 1.2.9、langgraph-checkpoint-postgres 3.1.0、Pytest 9.1.1、pytest-asyncio 1.4.0、Ruff 0.15.21、mypy 2.3.0。

## Global Constraints

- 只修改 `D:\CODEX\agent-portfolio\opercerta`；不复用旧公司源码、数据、规则、截图、模型、品牌或内部指标。
- 当前官方 PyPI 稳定版本与锁定版本一致；保持 `uv.lock` 和 `pyproject.toml` 的现有精确版本，不在本计划中升级依赖。
- MCP 使用 v1.x 稳定线 `mcp==1.28.1`，传输固定为 Streamable HTTP，工具路径固定为 `/mcp`。
- 本计划只实施库存不足到补货工单的后端纵向切片；不实现设备工具、React、SSE、JWT/RBAC、真实模型、Redis、可观测性、Docker/Linux 或公开部署。
- 四个工具名称固定为 `inventory.get_snapshot`、`policy.list_constraints`、`work_order.create`、`work_order.get`；服务端与客户端各自使用同一显式 allowlist。
- 所有写动作强制人工审批；审批前、拒绝后、过期后、快照失配后和证据失败后，工单新增数必须为零。
- `available_quantity = on_hand_quantity - reserved_quantity`；不足条件固定为 `available_quantity < reorder_point`；建议量固定为 `target_stock - available_quantity`。
- 建议量超出规则上下限时返回 `replenishment_quantity_out_of_policy`，不得静默截断、扩大或让模型改写。
- 证据缺失、超时、格式错误或过期时安全关闭；规则工具不可用时绝不进入审批或写工具。
- 审批绑定库存 evidence ID、规则 evidence ID、规则版本、decision facts hash、plan hash 和建议量；写入前必须重新取证并比较业务事实。
- PostgreSQL `0001_reliability_kernel` 不得修改；所有新列和 `evidence` 表只能由 `0002_inventory_replenishment` 增加，并支持 downgrade 回 `0001`。
- 新迁移中 `approvals` 绑定列允许 `NULL`，仅用于兼容已验证的 Task 3–5 历史路径；新的 bound approval 路径必须要求全部字段非空。
- checkpoint state 只允许 plain JSON；Engine、Repository、ClientSession、Secret、Exception、datetime 对象和原始 MCP 错误不得进入 checkpoint。
- 数据库连接继续使用 SecretStr、无密码 URL 和临时 `PGPASSWORD` 边界；测试、日志、API 和文档不得回显连接密码或完整连接串。
- API 测试使用 `httpx.AsyncClient` 与 `ASGITransport`，不使用已产生弃用警告的 `fastapi.testclient.TestClient`。
- 每个 Task 必须亲自观察 RED，再写最小 GREEN；出现意外失败先使用 `superpowers:systematic-debugging`，不得猜测修复。
- 每个 Task 都运行 focused 测试、相关回归、Ruff、format 和 mypy，并形成独立原子 Git commit。
- 测试计数、耗时和重复次数只记录实际命令输出；不得解释为生产成功率、SLA 或 exactly-once。
- 本计划完成后只能声明“库存补货后端纵向切片本地验证”，发布门禁仍为 `CLOSED`，不得启动 ForenTrail。

## File Responsibility Map

| Path | Responsibility |
| --- | --- |
| `src/opercerta/domain/replenishment.py` | 库存/规则证据、评估、计划、审批绑定、结果模型与确定性计算 |
| `src/opercerta/domain/model_gateway.py` | `ModelGateway` Protocol、`MockModelGateway` 和受约束说明模型 |
| `src/opercerta/domain/errors.py` | 库存、证据、审批绑定、MCP、过期和验证稳定错误 |
| `migrations/versions/0002_inventory_replenishment.py` | evidence 表、operations 结果/过期列、approvals binding 列 |
| `src/opercerta/infrastructure/db/schema.py` | 与 `0002` 一致的 SQLAlchemy Core metadata |
| `src/opercerta/infrastructure/db/evidence_repository.py` | 已校验证据的原子写入与按 operation 查询 |
| `src/opercerta/infrastructure/db/replenishment_operation_repository.py` | operation 创建、快照替换、状态/结果/错误/审计原子迁移和查询 |
| `src/opercerta/domain/approvals.py` | `BoundApprovalCommand` 与绑定记录模型 |
| `src/opercerta/infrastructure/db/approval_repository.py` | 保留 legacy submit，并新增绑定、过期和竞态安全提交 |
| `src/opercerta/application/approval_expiry.py` | 可注入时钟的单 Worker 审批过期服务 |
| `data/synthetic/inventory.json` | 五个从零创建的合成库存 SKU |
| `data/synthetic/replenishment_policies.json` | 对应的版本化补货规则 |
| `src/opercerta/tools/catalog.py` | 启动时严格加载与测试时可控替换的合成事实目录 |
| `src/opercerta/tools/server.py` | 四个 FastMCP 工具、稳定 ToolError 与独立服务入口 |
| `src/opercerta/infrastructure/db/work_order_repository.py` | 保留幂等写入并增加按 ID 回读 |
| `src/opercerta/infrastructure/mcp_gateway.py` | MCP 客户端 allowlist、超时、两次传输尝试和 Pydantic 复验 |
| `tests/integration/mcp/conftest.py` | 本机随机端口真实 uvicorn/FastMCP 服务 fixture |
| `src/opercerta/workflow/replenishment_graph.py` | JSON-only 库存补货 LangGraph 全流程 |
| `src/opercerta/application/operation_runner.py` | 创建运行、审批恢复、启动恢复和过期扫描协调 |
| `src/opercerta/workflow/replenishment_recovery.py` | 纵向闭环业务事实与 checkpoint 联合恢复 |
| `src/opercerta/api/models.py` | 创建、查询、审批和稳定错误 API 模型 |
| `src/opercerta/api/app.py` | FastAPI app factory、路由、lifespan 和错误映射 |
| `tests/unit/domain/test_replenishment.py` | 领域非法输入、规则、哈希和 Mock 模型 |
| `tests/integration/db/test_inventory_replenishment_migration.py` | `0002` Schema 升降级 |
| `tests/integration/db/test_evidence_repository.py` | evidence 落库与唯一约束 |
| `tests/integration/db/test_bound_approval.py` | binding、过期和十路竞态 |
| `tests/integration/mcp/test_tool_server.py` | 四工具真实传输契约 |
| `tests/integration/mcp/test_gateway.py` | allowlist、重试、超时和坏结构复验 |
| `tests/integration/workflow/test_replenishment_graph.py` | 正常、失败、interrupt、批准、拒绝和回读 |
| `tests/integration/workflow/test_replenishment_restart.py` | A/B 重启、快照变化、预写工单和过期恢复 |
| `tests/integration/api/test_operations_api.py` | 创建、查询、审批、HTTP 状态和安全响应 |
| `.env.example` | 非秘密的 MCP URL、超时、Mock 模式和审批 TTL |

---

### Task 1: Replenishment domain contracts, deterministic rules and Mock model

**Files:**
- Create: `src/opercerta/domain/replenishment.py`
- Create: `src/opercerta/domain/model_gateway.py`
- Create: `tests/unit/domain/test_replenishment.py`
- Modify: `src/opercerta/domain/errors.py`

**Interfaces:**
- Produces: `InventoryEvidence`, `PolicyEvidence`, `EvidenceBundle`, `InventoryPosition`, `ReplenishmentAssessment`, `ReplenishmentPlan`, `ApprovalBinding`, `OperationResult`, `OperationError`.
- Produces: `assess_replenishment(bundle: EvidenceBundle, now: datetime) -> ReplenishmentAssessment`.
- Produces: `build_plan(assessment: ReplenishmentAssessment, explanation: ModelPlanExplanation, rule_version: str) -> ReplenishmentPlan`.
- Produces: `build_approval_binding(bundle: EvidenceBundle, plan: ReplenishmentPlan) -> ApprovalBinding`.
- Produces: `ModelGateway.explain_plan(assessment: ReplenishmentAssessment) -> ModelPlanExplanation` and `MockModelGateway`.
- Invariant: model output never supplies quantity, risk, evidence IDs, rule version, action or approval requirement.

- [ ] **Step 1: Write the failing domain tests**

Create `tests/unit/domain/test_replenishment.py` with these concrete fixtures and assertions:

```python
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.errors import (
    EvidenceExpired,
    ReplenishmentQuantityOutOfPolicy,
)
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.domain.replenishment import (
    EvidenceBundle,
    InventoryEvidence,
    PolicyEvidence,
    assess_replenishment,
    build_approval_binding,
    build_plan,
)

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
INVENTORY_ID = UUID("00000000-0000-4000-8000-000000000101")
POLICY_ID = UUID("00000000-0000-4000-8000-000000000102")


def bundle(
    *,
    on_hand: int = 20,
    reserved: int = 8,
    reorder: int = 15,
    target: int = 30,
    minimum: int = 1,
    maximum: int = 100,
    captured_at: datetime = NOW,
) -> EvidenceBundle:
    return EvidenceBundle(
        inventory=InventoryEvidence(
            evidence_id=INVENTORY_ID,
            sku="SKU-LOW-001",
            on_hand_quantity=on_hand,
            reserved_quantity=reserved,
            captured_at=captured_at,
            source_version="inventory-seed-v1",
        ),
        policy=PolicyEvidence(
            evidence_id=POLICY_ID,
            action="replenish_inventory",
            sku="SKU-LOW-001",
            reorder_point=reorder,
            target_stock=target,
            minimum_order_quantity=minimum,
            maximum_order_quantity=maximum,
            evidence_ttl_seconds=300,
            approval_required=True,
            rule_version="replenishment-v1",
            captured_at=captured_at,
        ),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("sku", ""),
        ("on_hand_quantity", -1),
        ("reserved_quantity", -1),
        ("captured_at", datetime(2026, 7, 16, 8, 0)),
    ],
)
def test_inventory_evidence_rejects_invalid_input(field: str, value: object) -> None:
    data = bundle().inventory.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        InventoryEvidence.model_validate(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"target_stock": 15, "reorder_point": 15},
        {"minimum_order_quantity": 0},
        {"maximum_order_quantity": 0, "minimum_order_quantity": 1},
        {"evidence_ttl_seconds": 0},
        {"approval_required": False},
        {"action": "repair_equipment"},
    ],
)
def test_policy_rejects_unsafe_contracts(changes: dict[str, object]) -> None:
    data = bundle().policy.model_dump()
    data.update(changes)
    with pytest.raises(ValidationError):
        PolicyEvidence.model_validate(data)


def test_low_inventory_calculates_exact_replenishment() -> None:
    result = assess_replenishment(bundle(), NOW + timedelta(seconds=30))
    assert result.available_quantity == 12
    assert result.replenishment_required is True
    assert result.recommended_quantity == 18


def test_normal_inventory_requires_no_approval_or_order() -> None:
    result = assess_replenishment(
        bundle(on_hand=40, reserved=5, reorder=20, target=50),
        NOW + timedelta(seconds=30),
    )
    assert result.available_quantity == 35
    assert result.replenishment_required is False
    assert result.recommended_quantity is None


def test_over_reserved_inventory_keeps_negative_available_quantity() -> None:
    result = assess_replenishment(
        bundle(on_hand=2, reserved=7, reorder=5, target=10),
        NOW + timedelta(seconds=30),
    )
    assert result.available_quantity == -5
    assert result.recommended_quantity == 15


def test_quantity_outside_policy_is_rejected_not_clamped() -> None:
    with pytest.raises(
        ReplenishmentQuantityOutOfPolicy,
        match="replenishment_quantity_out_of_policy",
    ):
        assess_replenishment(
            bundle(on_hand=0, reserved=0, reorder=10, target=100, maximum=20),
            NOW + timedelta(seconds=30),
        )


def test_expired_inventory_or_policy_is_rejected() -> None:
    with pytest.raises(EvidenceExpired, match="evidence_expired"):
        assess_replenishment(bundle(), NOW + timedelta(seconds=301))


@pytest.mark.asyncio
async def test_mock_model_cannot_supply_deterministic_fields() -> None:
    current_bundle = bundle()
    assessment = assess_replenishment(
        current_bundle,
        NOW + timedelta(seconds=30),
    )
    explanation = await MockModelGateway().explain_plan(assessment)
    assert explanation.summary
    assert set(explanation.model_fields_set) == {"summary", "rationale"}
    plan = build_plan(
        assessment,
        explanation,
        current_bundle.policy.rule_version,
    )
    binding = build_approval_binding(current_bundle, plan)
    assert plan.action == "replenish_inventory"
    assert plan.recommended_quantity == 18
    assert binding.recommended_quantity == 18
    assert len(binding.decision_facts_hash) == 64
    assert len(binding.plan_hash) == 64
```

- [ ] **Step 2: Run focused RED**

```powershell
uv run pytest tests/unit/domain/test_replenishment.py -q
```

Expected RED: collection fails because `opercerta.domain.replenishment`, `model_gateway` and the new stable errors do not exist.

- [ ] **Step 3: Implement the minimal domain contracts**

Create `src/opercerta/domain/replenishment.py` with frozen Pydantic models and these public signatures:

```python
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000),
]


class InventoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: UUID
    sku: Sku
    on_hand_quantity: int
    reserved_quantity: int
    captured_at: datetime
    source_version: Version


class PolicyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: UUID
    action: Literal["replenish_inventory"]
    sku: Sku
    reorder_point: int
    target_stock: int
    minimum_order_quantity: int
    maximum_order_quantity: int
    evidence_ttl_seconds: int
    approval_required: Literal[True]
    rule_version: Version
    captured_at: datetime


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    inventory: InventoryEvidence
    policy: PolicyEvidence


class InventoryPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sku: Sku
    available_quantity: int


class ReplenishmentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sku: Sku
    available_quantity: int
    reorder_point: int
    target_stock: int
    replenishment_required: bool
    recommended_quantity: int | None
    decision_facts_hash: Digest


class ModelPlanExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    summary: SafeText
    rationale: SafeText


class ReplenishmentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["replenish_inventory"]
    sku: Sku
    recommended_quantity: int
    decision_facts_hash: Digest
    rule_version: Version
    summary: SafeText
    rationale: SafeText
    plan_hash: Digest


class ApprovalBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    inventory_evidence_id: UUID
    policy_evidence_id: UUID
    rule_version: Version
    decision_facts_hash: Digest
    plan_hash: Digest
    recommended_quantity: int


class OperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: Literal["replenishment_not_required", "work_order_completed"]
    message: SafeText
    work_order_id: UUID | None = None


class OperationError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$"),
    ]
    message: SafeText
```

Public function interfaces:

```text
assess_replenishment(
    bundle: EvidenceBundle,
    now: datetime,
) -> ReplenishmentAssessment

build_plan(
    assessment: ReplenishmentAssessment,
    explanation: ModelPlanExplanation,
    rule_version: str,
) -> ReplenishmentPlan

build_approval_binding(
    bundle: EvidenceBundle,
    plan: ReplenishmentPlan,
) -> ApprovalBinding
```

Implementation requirements:

- validators reject negative integer fields and timezone-naive timestamps;
- bundle validator requires matching SKU;
- policy validator enforces the relationships from the spec;
- expiration uses each captured time plus policy TTL;
- canonical JSON uses existing compact, sorted, `allow_nan=False` semantics;
- quantity outside `[minimum, maximum]` raises `ReplenishmentQuantityOutOfPolicy`;
- normal inventory returns `recommended_quantity=None`;
- `decision_facts_hash` excludes evidence IDs and captured times;
- `plan_hash` includes action, SKU, quantity, facts hash and rule version.

Create `src/opercerta/domain/model_gateway.py`:

```python
from typing import Protocol

from opercerta.domain.replenishment import (
    ModelPlanExplanation,
    ReplenishmentAssessment,
)


class ModelGateway(Protocol):
    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        raise NotImplementedError


class MockModelGateway:
    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        return ModelPlanExplanation(
            summary=f"建议为 {assessment.sku} 创建补货计划。",
            rationale="数量由已验证库存事实和版本化规则确定。",
        )
```

Append stable errors to `src/opercerta/domain/errors.py`; each constructor stores only safe identifiers and `str(error)` equals its code:

```python
class InventoryNotFound(LookupError):
    code = "inventory_not_found"


class EvidenceUnavailable(RuntimeError):
    code = "evidence_unavailable"


class EvidenceConflict(RuntimeError):
    code = "evidence_conflict"


class EvidenceExpired(RuntimeError):
    code = "evidence_expired"


class InvalidInventoryEvidence(ValueError):
    code = "invalid_inventory_evidence"


class InvalidPolicyEvidence(ValueError):
    code = "invalid_policy_evidence"


class ReplenishmentQuantityOutOfPolicy(ValueError):
    code = "replenishment_quantity_out_of_policy"


class ApprovalExpired(RuntimeError):
    code = "approval_expired"


class ApprovalSnapshotMismatch(RuntimeError):
    code = "approval_snapshot_mismatch"


class UnknownTool(RuntimeError):
    code = "unknown_tool"


class WorkOrderNotFound(LookupError):
    code = "work_order_not_found"


class WorkOrderVerificationFailed(RuntimeError):
    code = "work_order_verification_failed"


class WorkOrderStorageFailed(RuntimeError):
    code = "work_order_storage_failed"


class DependencyUnavailable(RuntimeError):
    code = "dependency_unavailable"
```

- [ ] **Step 4: Verify GREEN and existing domain regression**

```powershell
uv run pytest tests/unit/domain/test_replenishment.py -q
uv run pytest tests/unit -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Expected: every command exits `0`; record actual counts only.

- [ ] **Step 5: Commit the domain boundary**

```powershell
git add src/opercerta/domain/errors.py src/opercerta/domain/model_gateway.py src/opercerta/domain/replenishment.py tests/unit/domain/test_replenishment.py
git diff --cached --check
git commit -m "feat: define replenishment domain"
```

---

### Task 2: `0002` migration, evidence persistence and operation lifecycle repository

**Files:**
- Create: `migrations/versions/0002_inventory_replenishment.py`
- Create: `src/opercerta/infrastructure/db/evidence_repository.py`
- Create: `src/opercerta/infrastructure/db/replenishment_operation_repository.py`
- Create: `tests/integration/db/test_inventory_replenishment_migration.py`
- Create: `tests/integration/db/test_evidence_repository.py`
- Create: `tests/integration/db/test_replenishment_operation_repository.py`
- Modify: `src/opercerta/infrastructure/db/schema.py`
- Modify: `tests/integration/db/test_migration.py`

**Interfaces:**
- Produces: SQLAlchemy `evidence` table and new nullable columns matching revision `0002_inventory_replenishment`.
- Produces: `EvidenceRepository.save_bundle`, `save_refresh`, `list_for_operation` and immutable `EvidenceRecord`.
- Produces: `ReplenishmentOperationRepository.create`, transition methods, snapshot replacement, terminal result/error writes, `load_detail` and immutable `OperationDetail`.
- Invariant: each state change, next sequence and audit event commit in one transaction.

- [ ] **Step 1: Write migration and repository RED tests**

Create migration tests that execute:

```python
command.upgrade(config, "0001_reliability_kernel")
assert "evidence" not in inspect(engine).get_table_names()
command.upgrade(config, "0002_inventory_replenishment")
assert "evidence" in inspect(engine).get_table_names()
assert {"result_payload", "error_code", "approval_expires_at"} <= operation_columns
assert {
    "inventory_evidence_id",
    "policy_evidence_id",
    "rule_version",
    "decision_facts_hash",
    "plan_hash",
    "recommended_quantity",
} <= approval_columns
command.downgrade(config, "0001_reliability_kernel")
assert "evidence" not in inspect(engine).get_table_names()
command.upgrade(config, "head")
```

Modify the existing `tests/integration/db/test_migration.py` expected public-table subset to include `"evidence"` while preserving all existing reliability-kernel assertions.

Create evidence tests with real PostgreSQL:

```python
saved = await repository.save_bundle(operation_id, bundle())
rows = await repository.list_for_operation(operation_id)
assert [row.evidence_type for row in rows] == ["inventory", "policy"]
assert rows[0].content_hash == hash_json(rows[0].content)
assert all(row.expires_at == NOW + timedelta(seconds=300) for row in rows)

with pytest.raises(EvidenceConflict, match="evidence_conflict"):
    await repository.save_bundle(operation_id, changed_bundle_same_ids())
```

Create operation lifecycle tests:

```python
operation_id = await repository.create(operation_request())
view = await repository.load_detail(operation_id)
assert view.status is OperationStatus.RECEIVED
assert view.thread_id == str(operation_id)
assert view.snapshot.schema_version == 1
assert view.audit_events[0].event_type == "operation_received"

await repository.mark_gathering_evidence(operation_id)
await repository.record_evidence(
    operation_id,
    bundle=bundle(),
)
await repository.record_validated_plan(
    operation_id,
    assessment=assessment(),
    plan=plan(),
)
await repository.mark_awaiting_approval(
    operation_id,
    binding=binding(),
    approval_expires_at=NOW + timedelta(minutes=5),
)
view = await repository.load_detail(operation_id)
assert view.status is OperationStatus.AWAITING_APPROVAL
assert view.snapshot.plan["plan_hash"] == plan().plan_hash
assert view.approval_expires_at == NOW + timedelta(minutes=5)
assert [event.event_type for event in view.audit_events] == [
    "operation_received",
    "evidence_gathering_started",
    "evidence_recorded",
    "plan_validated",
    "approval_requested",
]
```

Also assert:

- `mark_reporting` followed by `complete_without_replenishment` stores `replenishment_not_required`;
- `mark_failed` stores a stable error code without traceback;
- same-target replay succeeds only with matching event payload;
- wrong-origin transition leaves status, sequence and audit unchanged.

- [ ] **Step 2: Run database RED**

```powershell
uv run pytest tests/integration/db/test_inventory_replenishment_migration.py tests/integration/db/test_evidence_repository.py tests/integration/db/test_replenishment_operation_repository.py -q
```

Expected RED: revision `0002`, `evidence_repository` and `replenishment_operation_repository` are missing.

- [ ] **Step 3: Implement revision `0002` and metadata**

Create `migrations/versions/0002_inventory_replenishment.py`:

```python
revision = "0002_inventory_replenishment"
down_revision = "0001_reliability_kernel"


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source_tool", sa.String(length=128), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operations.id"],
            name="fk_evidence_operation_id_operations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.UniqueConstraint(
            "operation_id",
            "evidence_id",
            name="uq_evidence_operation_evidence_id",
        ),
    )
    op.add_column("operations", sa.Column("result_payload", postgresql.JSONB()))
    op.add_column("operations", sa.Column("error_code", sa.String(length=64)))
    op.add_column(
        "operations",
        sa.Column("approval_expires_at", sa.DateTime(timezone=True)),
    )
    for name, column in (
        ("inventory_evidence_id", postgresql.UUID(as_uuid=True)),
        ("policy_evidence_id", postgresql.UUID(as_uuid=True)),
        ("rule_version", sa.String(length=128)),
        ("decision_facts_hash", sa.String(length=64)),
        ("plan_hash", sa.String(length=64)),
        ("recommended_quantity", sa.BigInteger()),
    ):
        op.add_column("approvals", sa.Column(name, column, nullable=True))


def downgrade() -> None:
    for name in (
        "recommended_quantity",
        "plan_hash",
        "decision_facts_hash",
        "rule_version",
        "policy_evidence_id",
        "inventory_evidence_id",
    ):
        op.drop_column("approvals", name)
    op.drop_column("operations", "approval_expires_at")
    op.drop_column("operations", "error_code")
    op.drop_column("operations", "result_payload")
    op.drop_table("evidence")
```

Mirror the exact table and columns in `schema.py`. Keep the four existing table objects and their constraints unchanged.

- [ ] **Step 4: Implement repositories with explicit atomic methods**

Define immutable `EvidenceRecord` in `evidence_repository.py` with `id`, `operation_id`, `evidence_id`, `evidence_type`, `source_tool`, `source_version`, `captured_at`, `expires_at`, `content`, `content_hash` and `created_at`.

`EvidenceRepository` exact public interfaces:

```text
save_bundle(operation_id: UUID, bundle: EvidenceBundle)
  -> tuple[EvidenceRecord, EvidenceRecord]
save_refresh(operation_id: UUID, bundle: EvidenceBundle)
  -> tuple[EvidenceRecord, EvidenceRecord]
list_for_operation(operation_id: UUID)
  -> list[EvidenceRecord]
```

Define immutable `AuditEventView` and `OperationDetail` in `replenishment_operation_repository.py`. `OperationDetail` contains operation ID, thread ID, status, `OperationSnapshot`, optional result/error/expiry, evidence records, optional approval row, optional work-order row, ordered audit events and convenience properties `assessment`, `plan`, `approval_binding`, `last_audit_sequence` and `event_types`.

`ReplenishmentOperationRepository` exact public interfaces:

```text
create(request: OperationRequest) -> UUID
mark_gathering_evidence(operation_id: UUID) -> None
record_evidence(
  operation_id: UUID,
  bundle: EvidenceBundle,
) -> None
record_validated_plan(
  operation_id: UUID,
  assessment: ReplenishmentAssessment,
  plan: ReplenishmentPlan | None,
) -> None
mark_reporting(operation_id: UUID) -> None
mark_awaiting_approval(
  operation_id: UUID,
  binding: ApprovalBinding,
  approval_expires_at: datetime,
) -> None
mark_executing(operation_id: UUID, approval_id: UUID) -> None
mark_verifying(operation_id: UUID, work_order_id: UUID) -> None
mark_completed(
  operation_id: UUID,
  result: OperationResult,
  work_order_id: UUID,
) -> None
mark_rejected(operation_id: UUID, approval_id: UUID) -> None
complete_without_replenishment(
  operation_id: UUID,
  result: OperationResult,
) -> None
mark_failed(operation_id: UUID, error: OperationError) -> None
mark_expired(operation_id: UUID, now: datetime) -> bool
load_detail(operation_id: UUID) -> OperationDetail
list_recoverable_ids() -> list[UUID]
list_due_approval_ids(now: datetime, limit: int) -> list[UUID]
```

Use one private `_transition()` that:

1. locks operation with `FOR UPDATE`;
2. validates current state;
3. increments `next_audit_sequence`;
4. updates snapshot/result/error/status;
5. inserts one audit row;
6. commits all writes together.

The initial snapshot is:

```python
OperationSnapshot(
    schema_version=1,
    request=request.model_dump(mode="json"),
    risk={},
    plan={},
    work_order_payload={},
)
```

Keep `schema_version=1` for legacy compatibility and use the existing fields with one explicit layout:

```text
risk = {
  "evidence": EvidenceBundle JSON,
  "assessment": ReplenishmentAssessment JSON,
  "approval_binding": ApprovalBinding JSON,
}
plan = ReplenishmentPlan JSON or {}
work_order_payload = approved candidate payload or {}
```

`record_evidence()` replaces only `risk.evidence`; `record_validated_plan()` adds `risk.assessment`, replaces `plan`, and prepares `work_order_payload` only for a valid low-inventory plan; `mark_awaiting_approval()` adds `risk.approval_binding`. Each method reconstructs and validates the full `OperationSnapshot` before updating `request_payload`. `OperationDetail` convenience properties parse these exact locations and return `None` for absent optional values.

- [ ] **Step 5: Verify migration, repositories and legacy regression**

```powershell
uv run pytest tests/integration/db/test_inventory_replenishment_migration.py tests/integration/db/test_evidence_repository.py tests/integration/db/test_replenishment_operation_repository.py -q
uv run pytest tests/integration/db -q
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run mypy src
```

- [ ] **Step 6: Commit the data boundary**

```powershell
git add migrations/versions/0002_inventory_replenishment.py src/opercerta/infrastructure/db/schema.py src/opercerta/infrastructure/db/evidence_repository.py src/opercerta/infrastructure/db/replenishment_operation_repository.py tests/integration/db/test_migration.py tests/integration/db/test_inventory_replenishment_migration.py tests/integration/db/test_evidence_repository.py tests/integration/db/test_replenishment_operation_repository.py
git diff --cached --check
git commit -m "feat: persist replenishment evidence"
```

---

### Task 3: Bound approval, snapshot mismatch and persistent expiry

**Files:**
- Modify: `src/opercerta/domain/approvals.py`
- Modify: `src/opercerta/infrastructure/db/approval_repository.py`
- Create: `src/opercerta/application/__init__.py`
- Create: `src/opercerta/application/approval_expiry.py`
- Create: `tests/integration/db/test_bound_approval.py`
- Create: `tests/unit/application/test_approval_expiry.py`

**Interfaces:**
- Produces: `BoundApprovalCommand` containing expected `ApprovalBinding`.
- Produces: `ApprovalRepository.submit_bound_once(command, now) -> ApprovalRecord`.
- Produces: `ApprovalExpiryService.expire_operation(operation_id: UUID) -> bool` and `expire_due(limit: int = 100) -> list[UUID]`.
- Preserves: existing `submit_once()` behavior and Task 3–5 tests.

- [ ] **Step 1: Write binding, expiry and race RED tests**

Use an operation prepared by Task 2 and assert:

```python
record = await repository.submit_bound_once(
    BoundApprovalCommand(
        operation_id=operation_id,
        approver_id="approver-1",
        decision=ApprovalDecision.APPROVED,
        reason="synthetic approval",
        expected_binding=binding(),
    ),
    now=NOW,
)
assert record.operation_id == operation_id
facts = await approval_facts(engine, operation_id)
assert facts.status == "resuming"
assert facts.approval_count == 1
assert facts.binding.plan_hash == binding().plan_hash
assert facts.event_types[-1] == "approval_recorded"
```

Mismatch:

```python
with pytest.raises(ApprovalSnapshotMismatch, match="approval_snapshot_mismatch"):
    await repository.submit_bound_once(
        command_with(plan_hash="0" * 64),
        now=NOW,
    )
assert await approval_count(engine, operation_id) == 0
assert await operation_status(engine, operation_id) == "awaiting_approval"
```

Expiry:

```python
with pytest.raises(ApprovalExpired, match="approval_expired"):
    await repository.submit_bound_once(command(), now=EXPIRES_AT)
assert await approval_count(engine, operation_id) == 0
assert await operation_status(engine, operation_id) == "expired"
assert await terminal_events(engine, operation_id) == ["approval_expired"]
```

Concurrency:

```python
results = await asyncio.gather(
    *[
        repository.submit_bound_once(command_for(index), now=NOW)
        for index in range(10)
    ],
    return_exceptions=True,
)
assert sum(isinstance(item, ApprovalRecord) for item in results) == 1
assert sum(isinstance(item, ApprovalAlreadyDecided) for item in results) == 9
assert await approval_count(engine, operation_id) == 1
```

Expiry service unit test injects a fake repository and fixed clock; it must call the repository with the exact aware `now` value and never sleep.

- [ ] **Step 2: Run focused RED**

```powershell
uv run pytest tests/integration/db/test_bound_approval.py tests/unit/application/test_approval_expiry.py -q
```

Expected RED: `BoundApprovalCommand`, `submit_bound_once` and `ApprovalExpiryService` are missing.

- [ ] **Step 3: Implement bound approval without breaking legacy calls**

Extend `approvals.py`:

```python
class BoundApprovalCommand(ApprovalCommand):
    expected_binding: ApprovalBinding
```

Implement `submit_bound_once()` with one operation row lock:

1. missing operation → `OperationNotFound`;
2. existing approval or status not `awaiting_approval` → `ApprovalAlreadyDecided`;
3. `now >= approval_expires_at` → atomically status `expired`, insert `approval_expired`, raise `ApprovalExpired` after transaction commits;
4. compare all six binding fields against the current snapshot and operation facts;
5. mismatch → `ApprovalSnapshotMismatch` with no write;
6. match → insert binding columns, status `resuming`, sequence increment and `approval_recorded` in one transaction.

Do not route `submit_once()` through binding logic; legacy tests intentionally store nullable binding columns.

Create `ApprovalExpiryService` with these exact interfaces:

```text
ApprovalExpiryService(
  repository: ReplenishmentOperationRepository,
  clock: Callable[[], datetime],
)
expire_operation(operation_id: UUID) -> bool
expire_due(limit: int = 100) -> list[UUID]
```

`expire_due()` reads due IDs and calls the same atomic repository method. It is a single Worker local scanner, not a distributed scheduler.

- [ ] **Step 4: Verify GREEN, legacy approvals and static gates**

```powershell
uv run pytest tests/integration/db/test_bound_approval.py tests/unit/application/test_approval_expiry.py -q
uv run pytest tests/integration/db/test_approval_race.py tests/integration/workflow/test_restart_recovery.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Repeat the bound approval race in fresh processes**

```powershell
1..10 | ForEach-Object {
    uv run pytest tests/integration/db/test_bound_approval.py -q -k ten_concurrent
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Record the observed completion count only.

- [ ] **Step 6: Commit the authorization boundary**

```powershell
git add src/opercerta/domain/approvals.py src/opercerta/infrastructure/db/approval_repository.py src/opercerta/application/__init__.py src/opercerta/application/approval_expiry.py tests/integration/db/test_bound_approval.py tests/unit/application/test_approval_expiry.py
git diff --cached --check
git commit -m "feat: bind approvals to evidence"
```

---

### Task 4: Versioned synthetic catalog and real FastMCP tool service

**Files:**
- Create: `data/synthetic/inventory.json`
- Create: `data/synthetic/replenishment_policies.json`
- Create: `src/opercerta/tools/__init__.py`
- Create: `src/opercerta/tools/catalog.py`
- Create: `src/opercerta/tools/server.py`
- Create: `tests/unit/tools/test_catalog.py`
- Create: `tests/integration/mcp/__init__.py`
- Create: `tests/integration/mcp/conftest.py`
- Create: `tests/integration/mcp/test_tool_server.py`
- Modify: `src/opercerta/infrastructure/db/work_order_repository.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `SyntheticCatalog.load(inventory_path, policy_path)`.
- Produces: `build_mcp_server(catalog, engine, clock) -> FastMCP`.
- Produces: four dotted-name tools with structured output.
- Produces: `WorkOrderRepository.get(work_order_id) -> WorkOrderRecord`.
- Invariant: tool exceptions expose only stable codes through `ToolError`.

- [ ] **Step 1: Add exact synthetic data and failing catalog tests**

Create inventory JSON:

```json
{
  "source_version": "inventory-seed-v1",
  "items": [
    {"sku": "SKU-NORMAL-001", "on_hand_quantity": 40, "reserved_quantity": 5},
    {"sku": "SKU-LOW-001", "on_hand_quantity": 20, "reserved_quantity": 8},
    {"sku": "SKU-BACKORDER-001", "on_hand_quantity": 2, "reserved_quantity": 7},
    {"sku": "SKU-LIMIT-001", "on_hand_quantity": 0, "reserved_quantity": 0},
    {"sku": "SKU-MUTABLE-001", "on_hand_quantity": 20, "reserved_quantity": 8}
  ]
}
```

Create policy JSON:

```json
{
  "source_version": "replenishment-policy-seed-v1",
  "rule_version": "replenishment-v1",
  "items": [
    {"sku": "SKU-NORMAL-001", "reorder_point": 20, "target_stock": 50, "minimum_order_quantity": 1, "maximum_order_quantity": 100, "evidence_ttl_seconds": 300, "approval_required": true},
    {"sku": "SKU-LOW-001", "reorder_point": 15, "target_stock": 30, "minimum_order_quantity": 1, "maximum_order_quantity": 100, "evidence_ttl_seconds": 300, "approval_required": true},
    {"sku": "SKU-BACKORDER-001", "reorder_point": 5, "target_stock": 10, "minimum_order_quantity": 1, "maximum_order_quantity": 100, "evidence_ttl_seconds": 300, "approval_required": true},
    {"sku": "SKU-LIMIT-001", "reorder_point": 10, "target_stock": 100, "minimum_order_quantity": 1, "maximum_order_quantity": 20, "evidence_ttl_seconds": 300, "approval_required": true},
    {"sku": "SKU-MUTABLE-001", "reorder_point": 15, "target_stock": 30, "minimum_order_quantity": 1, "maximum_order_quantity": 100, "evidence_ttl_seconds": 300, "approval_required": true}
  ]
}
```

Catalog tests assert exact SKUs, strict startup rejection for duplicate/invalid data, `InventoryNotFound`, aware captured times, new evidence UUID on each call and a test-only `replace_inventory()` that changes only an existing SKU.

- [ ] **Step 2: Add real MCP transport RED tests**

`tests/integration/mcp/conftest.py` must:

- allocate a free `127.0.0.1` TCP port;
- build `FastMCP(host="127.0.0.1", port=port, streamable_http_path="/mcp", json_response=True, stateless_http=True)`;
- run `uvicorn.Server` as an async background task;
- wait for the listening socket with a bounded polling loop;
- yield the full `http://127.0.0.1:{port}/mcp` URL and catalog;
- stop and await the server in fixture cleanup.

Transport test:

```python
async with streamable_http_client(mcp_url) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        listed = await session.list_tools()
        assert {tool.name for tool in listed.tools} == {
            "inventory.get_snapshot",
            "policy.list_constraints",
            "work_order.create",
            "work_order.get",
        }
        result = await session.call_tool(
            "inventory.get_snapshot",
            {"sku": "SKU-LOW-001"},
        )
        assert result.isError is False
        parsed = InventoryEvidence.model_validate(result.structuredContent)
        assert parsed.on_hand_quantity == 20
        assert parsed.reserved_quantity == 8
```

Also assert:

- unknown SKU returns `isError=True` and text exactly `inventory_not_found`;
- policy tool returns the expected version and `approval_required=True`;
- create before approval returns a safe error;
- after seeding approved executing operation, create and get return the same work-order ID;
- no response includes a database URL or password.

- [ ] **Step 3: Run catalog and MCP RED**

```powershell
uv run pytest tests/unit/tools/test_catalog.py tests/integration/mcp/test_tool_server.py -q
```

Expected RED: tools package, catalog and FastMCP server are missing.

- [ ] **Step 4: Implement catalog, server and work-order read**

Create `SyntheticCatalog` with these exact public interfaces:

```text
SyntheticCatalog.load(
  inventory_path: Path,
  policy_path: Path,
  *,
  id_factory: Callable[[], UUID] = uuid4,
) -> SyntheticCatalog
inventory_snapshot(
  sku: str,
  captured_at: datetime,
) -> InventoryEvidence
policy_constraints(
  sku: str,
  captured_at: datetime,
) -> PolicyEvidence
replace_inventory(
  sku: str,
  *,
  on_hand_quantity: int,
  reserved_quantity: int,
) -> None
```

Each read allocates a fresh evidence ID through `id_factory`; the catalog data files contain facts and source versions, not approval-bound evidence IDs. Tests inject a deterministic ID sequence. `replace_inventory()` is not exposed as MCP and exists only for deterministic test control.

Build the FastMCP server with an injectable loopback address for integration tests:

```python
def build_mcp_server(
    catalog: SyntheticCatalog,
    engine: AsyncEngine,
    clock: Callable[[], datetime],
    *,
    host: str = "127.0.0.1",
    port: int = 8001,
) -> FastMCP:
    server = FastMCP(
        "OperCerta Tools",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @server.tool(name="inventory.get_snapshot", structured_output=True)
    async def inventory_get_snapshot(sku: str) -> InventoryEvidence:
        try:
            return catalog.inventory_snapshot(sku, clock())
        except InventoryNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("inventory.get_snapshot", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="policy.list_constraints", structured_output=True)
    async def policy_list_constraints(
        action: Literal["replenish_inventory"],
        sku: str,
    ) -> PolicyEvidence:
        try:
            return catalog.policy_constraints(sku, clock())
        except InventoryNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("policy.list_constraints", error)
            raise ToolError(EvidenceUnavailable.code) from None

    @server.tool(name="work_order.create", structured_output=True)
    async def work_order_create(
        operation_id: UUID,
        sku: str,
        quantity: int,
        idempotency_key: str,
        approved_plan_hash: str,
    ) -> WorkOrderWriteResult:
        expected_key = derive_idempotency_key(operation_id)
        if idempotency_key != expected_key:
            raise ToolError(IdempotencyConflict.code)
        command = WorkOrderCommand(
            operation_id=operation_id,
            payload={
                "sku": sku,
                "quantity": quantity,
                "approved_plan_hash": approved_plan_hash,
            },
        )
        try:
            return await WorkOrderRepository(engine).create_or_get(command)
        except (WriteNotAuthorized, IdempotencyConflict) as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("work_order.create", error)
            raise ToolError(WorkOrderStorageFailed.code) from None

    @server.tool(name="work_order.get", structured_output=True)
    async def work_order_get(work_order_id: UUID) -> WorkOrderRecord:
        try:
            return await WorkOrderRepository(engine).get(work_order_id)
        except WorkOrderNotFound as error:
            raise ToolError(error.code) from error
        except Exception as error:
            log_safe_tool_failure("work_order.get", error)
            raise ToolError(WorkOrderStorageFailed.code) from None

    return server
```

`log_safe_tool_failure()` records only tool name, exception class and a generated correlation ID; it must not log `str(error)`, exception args, payloads, DSNs or secrets. Known domain errors become `ToolError(error.code)`. Unknown exceptions are logged through that safe helper and translated to `evidence_unavailable` or `work_order_storage_failed` without traceback text.

Extend `WorkOrderRepository`:

```text
get(work_order_id: UUID) -> WorkOrderRecord
```

It raises `WorkOrderNotFound` for no row and validates timestamps/payload through `WorkOrderRecord`.

The real-transport fixture allocates an unused loopback port, calls `build_mcp_server(catalog, engine, clock, host="127.0.0.1", port=allocated_port)`, passes `server.streamable_http_app()` to a hidden `uvicorn.Server`, waits on a bounded readiness probe, yields the `/mcp` URL, and always shuts the server down in fixture cleanup.

Add non-secret `.env.example` entries:

```text
OPERCERTA_MODEL_MODE=mock
OPERCERTA_MCP_URL=http://127.0.0.1:8001/mcp
OPERCERTA_MCP_TIMEOUT_SECONDS=2
OPERCERTA_APPROVAL_TTL_SECONDS=300
```

- [ ] **Step 5: Verify real transport GREEN**

```powershell
uv run pytest tests/unit/tools/test_catalog.py tests/integration/mcp/test_tool_server.py -q
uv run pytest tests/integration/db/test_work_order_idempotency.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 6: Commit the tool service boundary**

```powershell
git add .env.example data/synthetic src/opercerta/tools src/opercerta/infrastructure/db/work_order_repository.py tests/unit/tools tests/integration/mcp
git diff --cached --check
git commit -m "feat: serve replenishment mcp tools"
```

---

### Task 5: MCP client allowlist, timeout, retry and output validation

**Files:**
- Create: `src/opercerta/infrastructure/mcp_gateway.py`
- Create: `tests/integration/mcp/test_gateway.py`

**Interfaces:**
- Produces: `McpToolGateway`.
- Produces: typed methods `get_inventory`, `get_policy`, `create_work_order`, `get_work_order`.
- Invariant: unknown tool fails before a network call; only transport failures retry; invalid structured output never reaches workflow.

- [ ] **Step 1: Write gateway RED tests**

Concrete tests:

```python
gateway = McpToolGateway(mcp_url, timeout_seconds=2, max_attempts=2)
inventory = await gateway.get_inventory("SKU-LOW-001")
policy = await gateway.get_policy("SKU-LOW-001")
assert inventory.sku == policy.sku == "SKU-LOW-001"

no_network = NoNetworkSessionFactory()
guarded_gateway = McpToolGateway(
    mcp_url,
    timeout_seconds=2,
    session_factory=no_network,
)
with pytest.raises(UnknownTool, match="unknown_tool"):
    await guarded_gateway.call_raw("inventory.delete", {})
assert no_network.calls == 0
```

Retry tests use an injected `McpSessionFactory`:

```python
factory = FailingThenSuccessfulSessionFactory()
gateway = McpToolGateway(
    "http://127.0.0.1:1/mcp",
    timeout_seconds=0.1,
    max_attempts=2,
    session_factory=factory,
)
result = await gateway.get_inventory("SKU-LOW-001")
assert result.sku == "SKU-LOW-001"
assert factory.attempts == 2
```

Also assert:

- two transport timeouts become `EvidenceUnavailable`;
- stable `inventory_not_found` is not retried;
- invalid `structuredContent` becomes `InvalidInventoryEvidence`;
- `isError=True` unknown text becomes `EvidenceUnavailable` rather than exposing text;
- create retry uses identical operation ID, idempotency key and arguments;
- returned work order validates through `WorkOrderWriteResult`.

- [ ] **Step 2: Run gateway RED**

```powershell
uv run pytest tests/integration/mcp/test_gateway.py -q
```

Expected RED: `opercerta.infrastructure.mcp_gateway` is missing.

- [ ] **Step 3: Implement a bounded typed gateway**

Define `McpSessionFactory` as an async-context-manager callable that receives `(url: str, timeout_seconds: float)` and yields an initialized `ClientSession`. Implement `default_session_factory` in the same file with `@asynccontextmanager`.

```python
ALLOWED_TOOLS = frozenset(
    {
        "inventory.get_snapshot",
        "policy.list_constraints",
        "work_order.create",
        "work_order.get",
    }
)
```

`McpToolGateway` exact public interfaces:

```text
McpToolGateway(
  url: str,
  *,
  timeout_seconds: float,
  max_attempts: int = 2,
  session_factory: McpSessionFactory = default_session_factory,
)
get_inventory(sku: str) -> InventoryEvidence
get_policy(sku: str) -> PolicyEvidence
create_work_order(
  command: WorkOrderCommand,
  *,
  plan_hash: str,
) -> WorkOrderWriteResult
get_work_order(work_order_id: UUID) -> WorkOrderRecord
call_raw(
  name: str,
  arguments: dict[str, object],
) -> CallToolResult
```

The default session factory uses:

```python
async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as http_client:
    async with streamable_http_client(url, http_client=http_client) as (read, write, _):
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timedelta(seconds=timeout_seconds),
        ) as session:
            await session.initialize()
            yield session
```

Retry only `httpx.TransportError`, `TimeoutError` and MCP transport closure errors. Parse `structuredContent` with the expected Pydantic model. Map only known stable tool codes; never include arbitrary server text in raised error messages.

- [ ] **Step 4: Verify GREEN and transport regression**

```powershell
uv run pytest tests/integration/mcp/test_gateway.py tests/integration/mcp/test_tool_server.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the MCP client boundary**

```powershell
git add src/opercerta/infrastructure/mcp_gateway.py tests/integration/mcp/test_gateway.py
git diff --cached --check
git commit -m "feat: validate mcp tool calls"
```

---

### Task 6: Replenishment workflow through normal completion and approval interrupt

**Files:**
- Create: `src/opercerta/workflow/replenishment_graph.py`
- Create: `tests/integration/workflow/test_replenishment_graph.py`
- Modify: `src/opercerta/workflow/__init__.py`

**Interfaces:**
- Produces: `ReplenishmentState`, `ReplenishmentGraph`, `build_replenishment_graph`, `build_replenishment_initial_state`.
- Consumes: repositories, `McpToolGateway`, `ModelGateway`, checkpointer and an aware clock.
- At this Task boundary: normal inventory completes; evidence errors fail; low inventory interrupts before approval; approved execution is completed in Task 7.

- [ ] **Step 1: Write workflow RED for pre-approval paths**

Use real PostgreSQL, real checkpointer and real MCP transport:

```python
normal_id = await operations.create(request_for("SKU-NORMAL-001"))
await graph.ainvoke(
    build_replenishment_initial_state(normal_id, request_for("SKU-NORMAL-001")),
    config=config(normal_id),
)
normal = await operations.load_detail(normal_id)
assert normal.status is OperationStatus.COMPLETED
assert normal.result.outcome == "replenishment_not_required"
assert normal.approval is None
assert normal.work_order is None

low_id = await operations.create(request_for("SKU-LOW-001"))
await graph.ainvoke(
    build_replenishment_initial_state(low_id, request_for("SKU-LOW-001")),
    config=config(low_id),
)
snapshot = await graph.aget_state(config(low_id))
low = await operations.load_detail(low_id)
assert snapshot.interrupts
assert low.status is OperationStatus.AWAITING_APPROVAL
assert low.assessment.recommended_quantity == 18
assert low.approval is None
assert low.work_order is None
```

Failure cases are parametrized:

```python
[
    ("SKU-MISSING-001", "inventory_not_found"),
    ("SKU-LIMIT-001", "replenishment_quantity_out_of_policy"),
]
```

For each: final status `failed`, exact stable error, zero approvals, zero work orders, one terminal failure audit.

Add a fake gateway returning invalid or expired evidence and assert `invalid_inventory_evidence` / `evidence_expired` without interrupt.

- [ ] **Step 2: Run workflow RED**

```powershell
uv run pytest tests/integration/workflow/test_replenishment_graph.py -q
```

Expected RED: replenishment graph module is missing.

- [ ] **Step 3: Implement JSON-only nodes through interrupt**

State fields are JSON-compatible only:

```python
class ReplenishmentState(TypedDict):
    operation_id: str
    request: dict[str, JsonValue]
    evidence: dict[str, JsonValue] | None
    assessment: dict[str, JsonValue] | None
    plan: dict[str, JsonValue] | None
    approval_binding: dict[str, JsonValue] | None
    approval: dict[str, JsonValue] | None
    work_order: dict[str, JsonValue] | None
    result: dict[str, JsonValue] | None
    error: dict[str, JsonValue] | None
    replayed: bool
```

Node order:

```text
START
→ parse_request
→ mark_gathering
→ gather_evidence
→ calculate_assessment
→ route_assessment
   ├─ normal → record_validated_plan(plan=None)
   │          → mark_reporting
   │          → complete_without_replenishment → END
   ├─ failure → mark_failed → END
   └─ low → explain_plan
          → build_and_validate_plan
          → record_validated_plan(plan)
          → prepare_approval
          → request_approval(interrupt)
```

Requirements:

- `parse_request` accepts only explicit create-work-order inventory requests;
- `gather_evidence` runs inventory and policy reads with `asyncio.gather`;
- `gather_evidence` saves both validated tool returns through `EvidenceRepository`, then calls `record_evidence`; a crash between those commits is recoverable by re-gathering immutable evidence IDs;
- Pydantic models are dumped with `mode="json"` before state assignment;
- repositories receive typed models, not raw state dicts;
- stable tool/validation errors are converted to `OperationError` and terminal `failed`;
- the Mock model is called only on the low-inventory branch and never chooses action or quantity;
- `prepare_approval` stores complete snapshot, binding and TTL before interrupt;
- interrupt payload contains only operation ID, assessment, plan, binding and expiry;
- no approval row or work-order call exists before resume.

- [ ] **Step 4: Verify pre-approval GREEN and checkpoint JSON**

```powershell
uv run pytest tests/integration/workflow/test_replenishment_graph.py -q -k "normal or interrupt or failure or checkpoint"
uv run pytest tests/integration/workflow/test_checkpoints.py -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the pre-approval workflow**

```powershell
git add src/opercerta/workflow/__init__.py src/opercerta/workflow/replenishment_graph.py tests/integration/workflow/test_replenishment_graph.py
git diff --cached --check
git commit -m "feat: plan inventory replenishment"
```

---

### Task 7: Approved execution, rejection, verification, expiry and restart recovery

**Files:**
- Modify: `src/opercerta/workflow/replenishment_graph.py`
- Create: `src/opercerta/workflow/replenishment_recovery.py`
- Create: `src/opercerta/application/operation_runner.py`
- Extend: `tests/integration/workflow/test_replenishment_graph.py`
- Create: `tests/integration/workflow/test_replenishment_restart.py`

**Interfaces:**
- Produces: approved/rejected graph branches and MCP write/read verification.
- Produces: `ReplenishmentRecoveryCoordinator.recover(operation_id) -> RecoveryAction`.
- Produces: `OperationRunner.start`, `submit_approval`, `recover_all`, `expire_due`.
- Invariant: approved facts are re-read before write; one business work order survives retries and A/B restarts.

- [ ] **Step 1: Add approved, rejected and mismatch RED tests**

Approved:

```python
await interrupt_operation(graph_a, operation_id)
approval = await approvals.submit_bound_once(bound_approval(operation_id), now=NOW)
await graph_a.ainvoke(
    Command(
        resume={
            "approval_id": str(approval.id),
            "decision": "approved",
        }
    ),
    config=config(operation_id),
)
detail = await operations.load_detail(operation_id)
assert detail.status is OperationStatus.COMPLETED
assert detail.work_order.payload == {
    "approved_plan_hash": detail.plan.plan_hash,
    "quantity": 18,
    "sku": "SKU-LOW-001",
}
assert detail.result.outcome == "work_order_completed"
assert detail.event_types[-4:] == [
    "execution_started",
    "work_order_created",
    "verification_started",
    "operation_completed",
]
```

Rejected:

```python
assert detail.status is OperationStatus.REJECTED
assert detail.work_order is None
assert work_order_create_call_count == 0
```

Changed facts:

```python
catalog.replace_inventory(
    "SKU-MUTABLE-001",
    on_hand_quantity=25,
    reserved_quantity=8,
)
approval = await approvals.submit_bound_once(
    bound_approval(operation_id),
    now=NOW,
)
await graph_b.ainvoke(
    Command(
        resume={
            "approval_id": str(approval.id),
            "decision": "approved",
        }
    ),
    config=config(operation_id),
)
detail = await operations.load_detail(operation_id)
assert detail.status is OperationStatus.FAILED
assert detail.error.code == "approval_snapshot_mismatch"
assert detail.work_order is None
```

Read mismatch uses a gateway wrapper returning a different payload hash and expects `work_order_verification_failed`.

- [ ] **Step 2: Add A/B restart RED matrix**

Each case must close saver A and create saver B:

| Case | Expected action | Final status | approvals | work orders |
| --- | --- | --- | ---: | ---: |
| business row before first checkpoint | `REBUILD_FROM_BUSINESS_FACTS` | `awaiting_approval` | 0 | 0 |
| waiting interrupt | `KEEP_WAITING` | `awaiting_approval` | 0 | 0 |
| bound approval committed | `RESUME_DECISION` | `completed` | 1 | 1 |
| rejection committed | `RESUME_DECISION` | `rejected` | 1 | 0 |
| work order prewritten | safe replay/verify | `completed` | 1 | 1 |
| approval expired during downtime | terminal expiry | `expired` | 0 | 0 |

Prewritten assertion:

```python
assert final_work_order_id == prewritten_work_order_id
assert work_order_row_count == 1
assert work_order_created_event_count == 1
assert final_state["replayed"] is True
```

- [ ] **Step 3: Run execution and recovery RED**

```powershell
uv run pytest tests/integration/workflow/test_replenishment_graph.py tests/integration/workflow/test_replenishment_restart.py -q
```

Expected RED: graph has no post-approval branch and recovery/runner modules are missing.

- [ ] **Step 4: Implement revalidation, write, read and terminal branches**

Extend graph:

```text
request_approval
→ route_decision
   ├─ rejected → mark_rejected → END
   └─ approved → revalidate_evidence
       ├─ mismatch/expired → mark_failed → END
       └─ match → mark_executing
           → execute_work_order
           → mark_verifying
           → verify_work_order
           → mark_completed
           → END
```

`revalidate_evidence`:

- gets fresh inventory and policy through MCP;
- persists both refresh rows;
- recomputes assessment and rebuilds the plan with the originally approved summary/rationale; the model is not called again;
- builds a fresh binding for comparison while retaining the original evidence IDs as immutable approval provenance;
- compares rule version, decision facts hash, plan hash and quantity;
- on mismatch records `approval_snapshot_mismatch`;
- does not overwrite the original approved plan.

`execute_work_order` sends:

```python
WorkOrderCommand(
    operation_id=operation_id,
    payload={
        "sku": plan.sku,
        "quantity": plan.recommended_quantity,
        "approved_plan_hash": plan.plan_hash,
    },
)
```

`verify_work_order` calls MCP `work_order.get` and compares ID, operation ID, payload and payload hash.

- [ ] **Step 5: Implement runner and replenishment recovery coordinator**

`OperationRunner` receives the compiled replenishment graph, `ApprovalRepository`, `ReplenishmentOperationRepository`, `ReplenishmentRecoveryCoordinator`, `ApprovalExpiryService` and an injectable aware clock. Its exact public interfaces are:

```text
start(request: OperationRequest) -> UUID
submit_approval(
  command: BoundApprovalCommand,
  now: datetime,
) -> UUID
recover_all() -> list[UUID]
expire_due() -> list[UUID]
```

`start()` creates the business row before invoking the graph. `submit_approval()` calls `ApprovalRepository.submit_bound_once()` first, then resumes the graph with the persisted approval ID and decision; its return value is the operation ID. `recover_all()` first expires due approvals, then recovers nonterminal IDs one by one. Stable unrecoverable business/checkpoint conflicts are recorded as terminal failures; unexpected transport or infrastructure failures are safely logged, left nonterminal for a later retry, and never converted to success.

`ReplenishmentRecoveryCoordinator` follows the existing recovery matrix but reads business facts through `ReplenishmentOperationRepository`, uses the replenishment initial state and graph type, and delegates all replenishment state changes to that repository. It validates checkpoint operation ID and refuses a pending checkpoint for terminal business states. The legacy `OperationStateRepository` and `RecoveryCoordinator` remain unchanged for Task 3–5 regression coverage.

- [ ] **Step 6: Verify GREEN and repeat restart matrix**

```powershell
uv run pytest tests/integration/workflow/test_replenishment_graph.py tests/integration/workflow/test_replenishment_restart.py -q
1..10 | ForEach-Object {
    uv run pytest tests/integration/workflow/test_replenishment_restart.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
uv run pytest tests/integration/workflow -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

Record only observed counts.

- [ ] **Step 7: Commit the complete workflow**

```powershell
git add src/opercerta/workflow/replenishment_graph.py src/opercerta/workflow/replenishment_recovery.py src/opercerta/application/operation_runner.py tests/integration/workflow/test_replenishment_graph.py tests/integration/workflow/test_replenishment_restart.py
git diff --cached --check
git commit -m "feat: execute approved replenishment"
```

---

### Task 8: FastAPI create, query and approval boundary

**Files:**
- Create: `src/opercerta/api/__init__.py`
- Create: `src/opercerta/api/models.py`
- Create: `src/opercerta/api/app.py`
- Create: `tests/integration/api/__init__.py`
- Create: `tests/integration/api/test_operations_api.py`

**Interfaces:**
- Produces: `create_app(runtime: AppRuntime) -> FastAPI`.
- Produces: `POST /api/v1/operations`, `GET /api/v1/operations/{id}`, `POST /api/v1/operations/{id}/approval`.
- Produces: safe error envelope `{code, message}` and documented status mapping.
- Invariant: API never directly calls write tools or exposes connection, traceback or MCP internals.

- [ ] **Step 1: Write API RED tests using HTTPX ASGITransport**

Create fixture:

```python
app = create_app(runtime)
transport = ASGITransport(app=app)
async with AsyncClient(
    transport=transport,
    base_url="http://testserver",
) as client:
    yield client
```

Create operation:

```python
response = await client.post(
    "/api/v1/operations",
    json={
        "message": "为低库存物料生成补货工单",
        "requested_action": "create_work_order",
        "object_type": "inventory",
        "object_id": "SKU-LOW-001",
    },
)
assert response.status_code == 202
body = response.json()
assert body["status"] == "awaiting_approval"
assert set(body) == {"operation_id", "status", "created_at"}
```

Query:

```python
response = await client.get(f"/api/v1/operations/{operation_id}")
assert response.status_code == 200
body = response.json()
assert body["assessment"]["recommended_quantity"] == 18
assert body["approval"] is None
assert body["work_order"] is None
assert body["last_audit_sequence"] > 0
```

Approve using exact binding returned by query, then assert `202` and final `completed`. Reject and assert `rejected`, zero work order.

Error mapping assertions:

| Condition | HTTP |
| --- | ---: |
| request validation | 422 |
| operation missing | 404 |
| duplicate approval | 409 |
| approval expired | 409 |
| snapshot mismatch | 409 |
| inventory missing | accepted operation later reports failed; query is 200 |
| unexpected dependency error | 503 with `dependency_unavailable` |

Security scan:

```python
serialized = json.dumps(all_response_bodies, ensure_ascii=False)
assert "postgresql" not in serialized.lower()
assert "password" not in serialized.lower()
assert "traceback" not in serialized.lower()
assert "127.0.0.1:55432" not in serialized
```

- [ ] **Step 2: Run API RED**

```powershell
uv run pytest tests/integration/api/test_operations_api.py -q
```

Expected RED: API package and app factory are missing.

- [ ] **Step 3: Implement strict models and routes**

API models:

```python
class OperationAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: UUID
    status: OperationStatus
    created_at: datetime


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    approver_id: ApproverId
    decision: ApprovalDecision
    reason: ApprovalReason
    expected_inventory_evidence_id: UUID
    expected_policy_evidence_id: UUID
    expected_rule_version: str
    expected_decision_facts_hash: str
    expected_plan_hash: str
    expected_recommended_quantity: int


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str
```

Define the immutable test/runtime dependency container in `api/app.py`:

```python
@dataclass(frozen=True, slots=True)
class AppRuntime:
    runner: OperationRunner
    operations: ReplenishmentOperationRepository
```

Routes call only runner/repository query interfaces. Error handlers map safe domain errors to fixed Chinese messages and never include `str(unexpected_exception)`.

`create_app(runtime: AppRuntime) -> FastAPI` receives an already constructed runtime for tests. A separate production factory/lifespan creates engine, checkpointer, catalog, gateway and runner from environment, requires migrations/readiness to have been run externally rather than automatically mutating Schema, runs startup recovery once, and closes all clients/engine on shutdown.

No JWT dependency is introduced. README and API OpenAPI description state that actor IDs are untrusted local demo fields.

- [ ] **Step 4: Verify API GREEN and complete application regression**

```powershell
uv run pytest tests/integration/api/test_operations_api.py -q
uv run pytest tests/integration/mcp tests/integration/workflow tests/integration/api -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

- [ ] **Step 5: Commit the API boundary**

```powershell
git add src/opercerta/api tests/integration/api
git diff --cached --check
git commit -m "feat: expose replenishment api"
```

---

### Task 9: Fresh full gate, evidence, documentation and OperCerta-only handoff

**Files:**
- Create: `docs/release-evidence/inventory-replenishment-vertical-slice.md`
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-16.md`
- Modify: `docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md`

**Interfaces:**
- Consumes: observed commands, commits and database facts from Tasks 1–8.
- Produces: reproducible evidence, rollback points, unverified scope and next OperCerta boundary.
- Preserves: `OperCerta release gate: CLOSED`.

- [x] **Step 1: Run the fresh dependency and full code gate**

```powershell
uv sync --frozen --all-groups
uv run pytest -q
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run mypy src
git diff --check
git status --short
```

Expected: commands through diff check exit `0`; record exact observed counts and timings.

- [x] **Step 2: Run secret-safe migration downgrade and upgrade**

Use the established SecretStr, passwordless URL and temporary `PGPASSWORD` boundary to execute:

```text
alembic downgrade 0001_reliability_kernel
alembic upgrade head
alembic current
pytest tests/integration -q
```

Expected final revision: `0002_inventory_replenishment (head)`. Do not print the connection URL.

- [x] **Step 3: Run independent concurrency and restart repetitions**

```powershell
1..10 | ForEach-Object {
    uv run pytest tests/integration/db/test_bound_approval.py -q -k ten_concurrent
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
1..10 | ForEach-Object {
    uv run pytest tests/integration/workflow/test_replenishment_restart.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Record completion counts only as local repeat evidence.

- [x] **Step 4: Exercise the four tools and API over real local transports**

Start FastMCP on an unused loopback port and FastAPI on a separate loopback port. From a separate client process:

1. list MCP tools and confirm the four exact names;
2. create a low-inventory operation through HTTP;
3. query and capture binding;
4. approve through HTTP;
5. query final completed result;
6. repeat the approval and observe `409`;
7. query PostgreSQL and assert one approval, one work order and ordered terminal audit;
8. stop both services.

Do not record ports as permanent architecture or expose credentials.

- [x] **Step 5: Create observed-facts evidence**

Use these exact sections:

```markdown
# OperCerta 库存补货后端纵向闭环证据

## 验证范围与结论
## 环境、锁定版本与 Git 基线
## TDD RED/GREEN 记录
## `0002` 迁移与数据库不变量
## 四个真实 MCP 工具与传输证据
## 正常库存与安全失败路径
## 批准、拒绝、过期与快照变化
## 幂等写入、回读与 A/B 重启
## FastAPI 创建、查询与审批
## 完整测试与静态检查
## 凭据与响应安全扫描
## 未验证范围与发布门禁
## Git 回滚点
```

The conclusion must state:

```text
OperCerta release gate: CLOSED
Verified scope: inventory replenishment backend vertical slice only
Unverified scope: equipment scenario, React, SSE, JWT/RBAC, real model, Redis, observability, Docker/Linux, public deployment
Next project permitted: no
```

- [x] **Step 6: Synchronize repository and learning records**

Update README, index, handoff, current state and daily log with actual commits and commands. Append relevant user questions and interview explanations to `C:\Users\Administrator\Desktop\agent术语.md` without adding the desktop file to Git.

Do not mark future equipment, frontend, model or release work complete.

- [x] **Step 7: Verify documentation hygiene**

```powershell
git diff --check
rg -n "T[B]D|T[O]DO|implement[ ]later|fill[ ]in[ ]details" docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md docs/release-evidence/inventory-replenishment-vertical-slice.md
rg --pcre2 -n --glob '!docs/superpowers/plans/*.md' "postgresql[^\s]*://[^\s]*:[^\s]*@|OPERCERTA_DATABASE_URL\s*=|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|(?<![A-Za-z])sk-[A-Za-z0-9_-]{16,}" docs README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md
git status --short
```

Expected: diff check exits `0`; scans have no matches; status lists only intended evidence and documentation files.

- [x] **Step 8: Commit the evidence checkpoint**

```powershell
git add README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/development-log docs/release-evidence/inventory-replenishment-vertical-slice.md docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md
git diff --cached --check
git commit -m "docs: record replenishment slice evidence"
git status --short --branch
```

Expected: clean `main`. Do not create a release tag, deploy publicly, open the release gate or start another project.

## Plan Self-Review

- Spec coverage: Task 1 covers strict evidence/rule/plan models, deterministic formulas, hashes and Mock model; Tasks 2–3 cover `0002`, evidence, result/error, bound approval, expiry and atomic audit; Tasks 4–5 cover four real MCP tools, allowlist, transport, retry and validation; Tasks 6–7 cover full workflow, all terminal branches, approval revalidation, write/read, expiry and A/B restart; Task 8 covers all three APIs and safe errors; Task 9 covers migrations, repetitions, evidence and boundaries.
- Scope: equipment, UI, SSE, identity, real model, Redis, observability, Docker/Linux and deployment remain explicitly outside this plan.
- Type consistency: `InventoryEvidence`, `PolicyEvidence`, `EvidenceBundle`, `ReplenishmentAssessment`, `ReplenishmentPlan`, `ApprovalBinding`, `BoundApprovalCommand`, `McpToolGateway`, `ReplenishmentState`, `OperationRunner` and API binding fields have one spelling and one owner.
- Side-effect ordering: business row precedes graph; evidence precedes plan; binding precedes interrupt; approval commits before resume; fresh evidence comparison precedes write; MCP create precedes MCP get; verified read precedes completed.
- Legacy compatibility: `0001` remains unchanged, new approval columns are nullable for old paths, `submit_once()` remains available, existing reliable graph and recovery tests stay in the full gate.
- Failure safety: unknown tools fail locally; evidence and policy errors close writes; quantity is never clamped; expiry and mismatch insert no approval or work order; unexpected infrastructure errors do not become successful business states.
- Truthfulness: plan contains expected behaviors and test cases but no prefilled pass count, latency, quality score or public-release claim.
- Environment: real MCP and API tests bind only loopback and choose ephemeral ports; production deployment topology remains unverified.

## Execution Decision

This slice is tightly coupled through one PostgreSQL Schema, one checkpoint model, one MCP tool contract and one end-to-end workflow. Inline Execution minimizes handoff drift and preserves the continuous Chinese learning log; Subagent-Driven remains available if the user prefers extra per-task isolation and review at higher token cost.
