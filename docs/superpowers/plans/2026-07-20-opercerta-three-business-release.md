# OperCerta Three-Business Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不回退现有库存补货可靠性证据的前提下，完成库存补货、设备维修、作业异常恢复三个真实业务闭环，并补齐求职发布所需的前端、Redis、OpenTelemetry、真实模型代表性验证、跨业务评测、部署和中文学习材料。

**Architecture:** 把当前补货专用 LangGraph、审批绑定和仓储提炼为一个受控动作图与三个类型化场景适配器；FastAPI、六个 FastMCP 工具、PostgreSQL 业务事实/checkpointer、Redis 只读证据缓存和 React/SSE 控制台共享。每个任务保持可测试、可回滚和可演示，新增业务不能绕过批准后重新取证、原子审批、幂等写入和写后读验证。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、LangGraph、MCP Python SDK/FastMCP、PostgreSQL 18、SQLAlchemy/Alembic、Redis、OpenTelemetry、Prometheus、React/TypeScript/Vite、SSE、WSL2 Ubuntu、Docker Compose、GitHub Actions。

## Global Constraints

- 只实施 OperCerta；三业务求职演示门禁通过并完成复盘前不启动 ForenTrail。
- 全部业务数据、规则和编号从零合成；不复用旧公司源码、数据、表结构、截图、品牌、接口或专有规则。
- 不虚构通过率、性能、成本、SLA 或上线状态；所有数字只来自固定数据、脚本、原始报告和对应 Git Commit。
- 新增或修改行为一律先观察 RED，再写最小 GREEN；禁止删除现有补货失败样本迎合结果。
- LLM 不决定权威事实、风险、审批、数量、严重度、超时阈值或数据库写入；工具结果和模型输出均二次 Pydantic 校验。
- 写动作必须经过 RBAC、审批绑定、批准后重新取证、幂等写入和写后读；Redis 不进入批准后重取或写路径。
- 保留“节点至少执行一次、业务效果有效一次”语义，不宣称 exactly-once。
- 密钥只来自已忽略环境文件或进程环境，不进入命令输出、日志、文档、测试夹具或 Git。
- 本计划使用 Inline Execution；不启用 subagent，不创建并行项目工作树。
- 用户自有 `.gitignore` 修改不纳入本计划提交，除非用户另行授权。

---

## File Structure

| 路径 | 责任 |
| --- | --- |
| `src/opercerta/domain/scenarios.py` | 三业务公共判别式类型、通用审批绑定和场景协议 |
| `src/opercerta/domain/replenishment.py` | 库存证据、规则、评估和计划；对外适配公共场景协议 |
| `src/opercerta/domain/maintenance.py` | 设备证据、维修规则、评估、计划和工单参数 |
| `src/opercerta/domain/task_recovery.py` | 作业证据、超时/阻塞规则、评估、计划和工单参数 |
| `src/opercerta/application/scenario_registry.py` | `ObjectType` 到三个场景适配器的失败关闭注册表 |
| `src/opercerta/workflow/controlled_action_graph.py` | 三业务共享 LangGraph 节点、路由、interrupt 和写后读 |
| `src/opercerta/workflow/controlled_action_recovery.py` | 三业务公共检查点/业务事实恢复协调 |
| `src/opercerta/infrastructure/db/operation_repository.py` | 通用操作、证据、计划、终态和审计仓储 |
| `src/opercerta/infrastructure/cache.py` | Redis 只读证据缓存和失败旁路 |
| `src/opercerta/infrastructure/model_gateway.py` | OpenAI-compatible Real adapter；Mock 仍在领域端口实现 |
| `migrations/versions/0003_three_business_operations.py` | 通用审批绑定字段、回填、索引和可逆迁移 |
| `data/synthetic/*.json` | 三业务合成对象与版本化规则 |
| `data/evals/opercerta-three-business-v1.json` | 透明固定跨业务评测集 |
| `web/src/scenarios.ts` | 三业务前端类型化展示配置 |
| `scripts/verify_compose.py` | 三业务 Compose smoke、数据库断言和恢复检查 |
| `scripts/run_opercerta_evaluation.py` | 跨业务质量评测入口 |
| `scripts/run_performance_matrix.py` | 串/并行 × Redis 开/关固定对照入口 |
| `deploy/Caddyfile`、`compose.release.yaml` | HTTPS 单节点演示入口、内部依赖隔离和固定发布覆盖 |
| `docs/learning/*.md` | 中文核心技术、手动实验和面试讲解 |

## Task 1: 通用领域契约与可逆数据库迁移

**Files:**
- Create: `src/opercerta/domain/scenarios.py`
- Create: `migrations/versions/0003_three_business_operations.py`
- Modify: `src/opercerta/domain/contracts.py`
- Modify: `src/opercerta/domain/approvals.py`
- Modify: `src/opercerta/api/models.py`
- Modify: `src/opercerta/infrastructure/db/schema.py`
- Modify: `src/opercerta/infrastructure/db/approval_repository.py`
- Test: `tests/unit/domain/test_scenarios.py`
- Test: `tests/integration/db/test_three_business_migration.py`
- Test: `tests/integration/db/test_bound_approval.py`

**Interfaces:**
- Produces `ObjectType.INVENTORY | EQUIPMENT | TASK` and existing `ActionType.QUERY | CREATE_WORK_ORDER`.
- Produces `ScenarioKind`, three discriminated action-parameter models, generic `ApprovalBinding` and `ScenarioError`; concrete assessment/plan/result types remain in their domain modules.
- Produces database columns `subject_evidence_id UUID` and `binding_payload JSONB`; existing inventory columns remain readable during migration compatibility.
- Preserves one decision per operation and atomic expected-binding equality.

- [ ] **Step 1: Write failing contract and migration tests**

```python
def test_approval_binding_rejects_parameters_for_another_scenario() -> None:
    with pytest.raises(ValidationError):
        ApprovalBinding.model_validate({
            "scenario": "equipment",
            "subject_evidence_id": str(uuid4()),
            "policy_evidence_id": str(uuid4()),
            "rule_version": "rules-v1",
            "decision_facts_hash": "a" * 64,
            "plan_hash": "b" * 64,
            "parameters": {
                "kind": "replenishment",
                "recommended_quantity": 10,
            },
        })

def test_operation_request_accepts_task_query() -> None:
    request = OperationRequest(
        message="查询阻塞作业",
        requested_action="query",
        object_type="task",
        object_id="TASK-BLOCKED-001",
    )
    assert request.object_type is ObjectType.TASK
```

Migration integration test must upgrade `0002 → 0003`, assert inventory approval rows are backfilled into the new binding columns, downgrade to `0002`, and upgrade again without changing the historical inventory decision.

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run pytest tests/unit/domain/test_scenarios.py tests/unit/domain/test_operation_request.py -q
uv run pytest tests/integration/db/test_three_business_migration.py tests/integration/db/test_bound_approval.py -q
```

Expected: failure because task object, generic binding types and migration do not exist; existing tests must still collect.

- [ ] **Step 3: Implement strict common contracts and migration**

`ApprovalBinding` uses a Pydantic discriminator:

```python
ActionParameters = Annotated[
    ReplenishmentParameters | RepairParameters | TaskRecoveryParameters,
    Field(discriminator="kind"),
]

class ApprovalBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario: ScenarioKind
    subject_evidence_id: UUID
    policy_evidence_id: UUID
    rule_version: Version
    decision_facts_hash: Digest
    plan_hash: Digest
    parameters: ActionParameters

    @model_validator(mode="after")
    def require_matching_scenario(self) -> Self:
        expected_kind = {
            ScenarioKind.INVENTORY: "replenishment",
            ScenarioKind.EQUIPMENT: "repair",
            ScenarioKind.TASK: "task_recovery",
        }[self.scenario]
        if self.parameters.kind != expected_kind:
            raise ValueError("approval parameters must match scenario")
        return self
```

The migration backfills `subject_evidence_id = inventory_evidence_id` and creates canonical inventory `binding_payload`; it must not drop the old columns in this release. `ApprovalRepository.submit_bound_once()` locks the operation and compares the full validated binding before inserting the decision.

- [ ] **Step 4: Run GREEN and full reliability regression**

```powershell
uv run pytest tests/unit/domain tests/integration/db/test_three_business_migration.py tests/integration/db/test_bound_approval.py tests/integration/db/test_approval_race.py tests/integration/db/test_work_order_idempotency.py -q
uv run ruff check src tests migrations
uv run mypy src
```

Expected: all selected tests pass; ten-way approval and idempotency tests remain unchanged in meaning.

- [ ] **Step 5: Commit**

```powershell
git add src/opercerta/domain/scenarios.py src/opercerta/domain/contracts.py src/opercerta/domain/approvals.py src/opercerta/api/models.py src/opercerta/infrastructure/db/schema.py src/opercerta/infrastructure/db/approval_repository.py migrations/versions/0003_three_business_operations.py tests/unit/domain/test_scenarios.py tests/unit/domain/test_operation_request.py tests/integration/db/test_three_business_migration.py tests/integration/db/test_bound_approval.py
git commit -m "refactor: generalize controlled action contracts"
```

## Task 2: 共享场景注册表与 LangGraph 内核，保持补货行为不变

**Files:**
- Create: `src/opercerta/application/scenario_registry.py`
- Create: `src/opercerta/workflow/controlled_action_graph.py`
- Create: `src/opercerta/workflow/controlled_action_recovery.py`
- Create: `src/opercerta/infrastructure/db/operation_repository.py`
- Modify: `src/opercerta/domain/replenishment.py`
- Modify: `src/opercerta/domain/model_gateway.py`
- Modify: `src/opercerta/application/operation_runner.py`
- Modify: `src/opercerta/api/app.py`
- Preserve as compatibility wrappers: `src/opercerta/workflow/replenishment_graph.py`, `src/opercerta/workflow/replenishment_recovery.py`, `src/opercerta/infrastructure/db/replenishment_operation_repository.py`
- Test: `tests/unit/application/test_scenario_registry.py`
- Test: `tests/integration/workflow/test_controlled_action_graph.py`
- Test: existing replenishment workflow/API/restart suites

**Interfaces:**
- `ScenarioRegistry.get(request: OperationRequest) -> ControlledActionScenario` fails closed on unsupported combinations.
- `ControlledActionScenario` provides `gather_evidence`, `assess`, `requires_action`, `build_plan`, `build_binding`, `revalidate`, `build_work_order_payload`, `no_action_result`.
- `OperationRunner` depends only on `ControlledActionGraph`, `OperationRepository` and `ControlledActionRecoveryCoordinator`.
- Compatibility wrappers keep current test imports working while callers migrate.

- [ ] **Step 1: Write RED tests for dispatch and inventory parity**

```python
def test_registry_dispatches_inventory_and_rejects_incomplete_request() -> None:
    registry = build_default_scenario_registry(...)
    assert registry.get(inventory_request()).kind is ScenarioKind.INVENTORY
    with pytest.raises(UnsupportedScenario):
        registry.get(OperationRequest(message="不完整"))

@pytest.mark.asyncio
async def test_shared_graph_preserves_inventory_approval_binding_and_result(...):
    result = await run_inventory_low_stock_through_approval(...)
    assert result.status is OperationStatus.COMPLETED
    assert result.work_order.payload["kind"] == "replenishment"
```

The test compares the existing inventory terminal audit sequence and verifies no equipment/task adapter is invoked.

- [ ] **Step 2: Run RED**

```powershell
uv run pytest tests/unit/application/test_scenario_registry.py tests/integration/workflow/test_controlled_action_graph.py -q
```

Expected: import/behavior failure because the registry and shared graph do not exist.

- [ ] **Step 3: Extract the shared graph without changing inventory outcomes**

The graph state keeps JSON only and uses the request discriminator on every recovery path. The shared routing is fixed:

```python
START -> parse_request -> mark_gathering -> gather_evidence -> assess
assess -> report_no_action | explain_plan
explain_plan -> validate_plan -> prepare_approval -> interrupt
interrupt -> reject | revalidate -> execute -> verify -> complete
any_safe_failure -> mark_failed -> END
```

`ReplenishmentScenario` wraps existing `assess_replenishment`, `build_plan` and binding logic. Do not delete existing tests or change stable API error codes during extraction.

- [ ] **Step 4: Run inventory parity, recovery and full backend GREEN**

```powershell
uv run pytest tests/integration/workflow/test_controlled_action_graph.py tests/integration/workflow/test_replenishment_graph.py tests/integration/workflow/test_replenishment_restart.py tests/integration/api/test_operations_api.py -q
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: the complete pre-existing suite remains green and new shared-graph tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/opercerta/application src/opercerta/workflow src/opercerta/infrastructure/db src/opercerta/domain/replenishment.py src/opercerta/domain/model_gateway.py src/opercerta/api/app.py tests/unit/application tests/integration/workflow tests/integration/api/test_operations_api.py
git commit -m "refactor: share controlled action workflow"
```

## Task 3: 设备状态查询与维修工单纵向闭环

**Files:**
- Create: `src/opercerta/domain/maintenance.py`
- Create: `data/synthetic/equipment.json`
- Create: `data/synthetic/maintenance_policies.json`
- Modify: `src/opercerta/domain/errors.py`
- Modify: `src/opercerta/tools/catalog.py`
- Modify: `src/opercerta/tools/server.py`
- Modify: `src/opercerta/infrastructure/mcp_gateway.py`
- Modify: `src/opercerta/application/scenario_registry.py`
- Test: `tests/unit/domain/test_maintenance.py`
- Test: `tests/unit/tools/test_catalog.py`
- Test: `tests/integration/mcp/test_tool_server.py`
- Test: `tests/integration/mcp/test_gateway.py`
- Test: `tests/integration/workflow/test_equipment_maintenance.py`
- Test: `tests/integration/workflow/test_equipment_restart.py`
- Test: `tests/integration/api/test_operations_api.py`

**Interfaces:**
- `EquipmentEvidence`: equipment ID, state, alert code/severity, last heartbeat, evidence ID, captured time, source version.
- `MaintenancePolicyEvidence`: allowed alert levels, maximum heartbeat age, priority mapping, TTL, approval required and rule version.
- `MaintenanceScenario`: query and `repair_equipment` action through the shared graph.
- MCP adds `equipment.get_status`; missing equipment maps to `equipment_not_found`.

- [ ] **Step 1: Write RED tests for illegal evidence, no-repair query and repair approval**

```python
def test_maintenance_rejects_naive_heartbeat() -> None:
    with pytest.raises(ValidationError):
        EquipmentEvidence(**valid_equipment(), last_heartbeat=datetime(2026, 7, 20))

def test_critical_alert_requires_repair() -> None:
    assessment = assess_maintenance(critical_bundle(), NOW)
    assert assessment.maintenance_required is True
    assert assessment.priority == "urgent"

@pytest.mark.asyncio
async def test_equipment_repair_requires_bound_approval_and_is_idempotent(...):
    operation = await create_equipment_operation(...)
    assert operation.status is OperationStatus.AWAITING_APPROVAL
    completed = await approve_and_reload(operation, ...)
    assert completed.work_order.payload["kind"] == "repair"
```

Add restart tests at waiting approval, after decision commit and after work-order commit; duplicate approval remains 409 and one work-order row.

- [ ] **Step 2: Run RED**

```powershell
uv run pytest tests/unit/domain/test_maintenance.py tests/integration/mcp/test_tool_server.py tests/integration/workflow/test_equipment_maintenance.py tests/integration/workflow/test_equipment_restart.py -q
```

Expected: failures for missing models, tool and registry entry.

- [ ] **Step 3: Implement minimal equipment adapter and tool**

The deterministic decision uses only versioned policy values. Heartbeat age is calculated in Python; model explanation receives the validated assessment and cannot change priority or alert evidence. The approval binding includes equipment evidence, policy evidence, rule version, facts hash, plan hash, alert code and priority. After approval, equipment and policy are re-read and compared before creating a typed `RepairWorkOrderPayload`.

- [ ] **Step 4: Run GREEN, MCP contract and restart repetitions**

```powershell
uv run pytest tests/unit/domain/test_maintenance.py tests/unit/tools/test_catalog.py tests/integration/mcp tests/integration/workflow/test_equipment_maintenance.py tests/integration/workflow/test_equipment_restart.py tests/integration/api/test_operations_api.py -q
1..5 | ForEach-Object { uv run pytest tests/integration/workflow/test_equipment_restart.py -q }
uv run ruff check .
uv run mypy src
```

Expected: each repetition passes; normal equipment query produces no approval/work order, critical alert produces exactly one repair order only after approval.

- [ ] **Step 5: Commit**

```powershell
git add src/opercerta/domain/maintenance.py src/opercerta/domain/errors.py src/opercerta/tools src/opercerta/infrastructure/mcp_gateway.py src/opercerta/application/scenario_registry.py data/synthetic/equipment.json data/synthetic/maintenance_policies.json tests/unit/domain/test_maintenance.py tests/unit/tools/test_catalog.py tests/integration/mcp tests/integration/workflow/test_equipment_maintenance.py tests/integration/workflow/test_equipment_restart.py tests/integration/api/test_operations_api.py
git commit -m "feat: add equipment maintenance workflow"
```

## Task 4: 作业阻塞/超时查询与异常恢复工单纵向闭环

**Files:**
- Create: `src/opercerta/domain/task_recovery.py`
- Create: `data/synthetic/tasks.json`
- Create: `data/synthetic/task_recovery_policies.json`
- Modify: `src/opercerta/domain/errors.py`
- Modify: `src/opercerta/tools/catalog.py`
- Modify: `src/opercerta/tools/server.py`
- Modify: `src/opercerta/infrastructure/mcp_gateway.py`
- Modify: `src/opercerta/application/scenario_registry.py`
- Test: `tests/unit/domain/test_task_recovery.py`
- Test: `tests/unit/tools/test_catalog.py`
- Test: `tests/integration/mcp/test_tool_server.py`
- Test: `tests/integration/mcp/test_gateway.py`
- Test: `tests/integration/workflow/test_task_recovery.py`
- Test: `tests/integration/workflow/test_task_restart.py`
- Test: `tests/integration/api/test_operations_api.py`

**Interfaces:**
- `TaskEvidence`: task ID, state, due time, last progress time, blocker code, retry count, captured time and source version.
- `TaskRecoveryPolicyEvidence`: blocked states, overdue grace seconds, maximum retry count, allowed recovery action, TTL and rule version.
- MCP adds `task.get_status`; missing task maps to `task_not_found`.
- `TaskRecoveryScenario` emits typed `TaskRecoveryWorkOrderPayload(kind="task_recovery", recovery_action="manual_requeue")` only after bound approval.

- [ ] **Step 1: Write RED tests for boundary time, retry cap and recovery binding**

```python
def test_task_is_not_overdue_at_exact_grace_boundary() -> None:
    assessment = assess_task_recovery(bundle(due_at=NOW - timedelta(seconds=300)), NOW)
    assert assessment.recovery_required is False

def test_blocked_task_over_retry_cap_fails_closed() -> None:
    with pytest.raises(TaskRecoveryOutOfPolicy):
        assess_task_recovery(bundle(state="blocked", retry_count=4), NOW)

@pytest.mark.asyncio
async def test_task_recovery_revalidates_blocker_after_approval(...):
    operation = await create_blocked_task_operation(...)
    mutate_task_to_running(operation.target_id)
    result = await approve(operation, ...)
    assert result.error.code == "approval_snapshot_mismatch"
    assert await count_work_orders(operation.id) == 0
```

- [ ] **Step 2: Run RED**

```powershell
uv run pytest tests/unit/domain/test_task_recovery.py tests/integration/workflow/test_task_recovery.py tests/integration/workflow/test_task_restart.py -q
```

Expected: missing domain/tool/adapter failures.

- [ ] **Step 3: Implement minimal task adapter and sixth MCP tool**

Use timezone-aware calculations and explicit inclusive/exclusive boundary tests. A task that recovered before approval must fail the original write via binding mismatch, not create an unnecessary recovery order. No automatic task retry or real scheduler is introduced.

- [ ] **Step 4: Run GREEN, six-tool allowlist and restart repetitions**

```powershell
uv run pytest tests/unit/domain/test_task_recovery.py tests/integration/mcp tests/integration/workflow/test_task_recovery.py tests/integration/workflow/test_task_restart.py tests/integration/api/test_operations_api.py -q
1..5 | ForEach-Object { uv run pytest tests/integration/workflow/test_task_restart.py -q }
uv run ruff check .
uv run mypy src
```

Expected: MCP list is exactly six approved names; task query and write terminal paths pass; restart never creates more than one order.

- [ ] **Step 5: Commit**

```powershell
git add src/opercerta/domain/task_recovery.py src/opercerta/domain/errors.py src/opercerta/tools src/opercerta/infrastructure/mcp_gateway.py src/opercerta/application/scenario_registry.py data/synthetic/tasks.json data/synthetic/task_recovery_policies.json tests/unit/domain/test_task_recovery.py tests/unit/tools/test_catalog.py tests/integration/mcp tests/integration/workflow/test_task_recovery.py tests/integration/workflow/test_task_restart.py tests/integration/api/test_operations_api.py
git commit -m "feat: add blocked task recovery workflow"
```

## Task 5: 三业务 React 控制台与真实 API 契约

**Files:**
- Create: `web/src/scenarios.ts`
- Modify: `web/src/api/contracts.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/OperationControls.tsx`
- Modify: `web/src/components/OperationDetail.tsx`
- Modify: `web/src/components/ApprovalPanel.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/showcase/showcase-content.ts`
- Modify: `web/src/styles.css`
- Test: `web/src/scenarios.test.ts`
- Test: `web/src/api/client.test.ts`
- Test: `web/src/components/OperationControls.test.tsx`
- Test: `web/src/components/ApprovalPanel.test.tsx`
- Test: `web/src/App.test.tsx`
- Test: `web/src/showcase/ShowcasePage.test.tsx`

**Interfaces:**
- `ScenarioDefinition` contains `objectType`, `objectId`, `label`, `message`, supported action and explanation.
- `ApiClient.createOperation(scenario, action)` sends the exact shared backend contract.
- Frontend `ApprovalBinding` mirrors the discriminated backend payload and submits it unchanged; UI does not reconstruct trusted parameters.

- [ ] **Step 1: Write RED component/API tests**

```typescript
it.each(["inventory", "equipment", "task"])(
  "creates a real %s operation request",
  async (objectType) => {
    render(<OperationControls {...props} />);
    await user.selectOptions(screen.getByLabelText("业务场景"), objectType);
    await user.click(screen.getByRole("button", { name: /创建处置/ }));
    expect(props.onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ objectType })
    );
  }
);
```

Add tests that the public showcase says three scenarios are implemented only after the actual console contract exists, and removes stale `Private GitHub` / `未完成设备场景` limitations.

- [ ] **Step 2: Run RED**

```powershell
Set-Location web
npm run test:run -- src/scenarios.test.ts src/api/client.test.ts src/components/OperationControls.test.tsx src/App.test.tsx
Set-Location ..
```

Expected: failures because only one SKU and inventory-specific binding exist.

- [ ] **Step 3: Implement one-page three-scenario interaction**

Use a single select/card area, not separate pages. Each scenario offers `查询状态` and `创建处置` where allowed. Evidence, deterministic assessment, model explanation, approval binding, work order and audit remain in the shared detail panels. Busy and permission states disable buttons; duplicate decisions show conflict without silently retrying.

- [ ] **Step 4: Run GREEN and production build**

```powershell
Set-Location web
npm run test:run
npm run build
Set-Location ..
```

Expected: all frontend tests and Vite build pass with no TypeScript errors.

- [ ] **Step 5: Commit**

```powershell
git add web/src web/package-lock.json
git commit -m "feat: expose three operation scenarios"
```

## Task 6: Redis 只读缓存、OpenTelemetry 与 Real model adapter

**Files:**
- Create: `src/opercerta/infrastructure/cache.py`
- Create: `src/opercerta/infrastructure/model_gateway.py`
- Create: `src/opercerta/observability/tracing.py`
- Modify: `src/opercerta/domain/model_gateway.py`
- Modify: `src/opercerta/workflow/controlled_action_graph.py`
- Modify: `src/opercerta/api/app.py`
- Modify: `src/opercerta/runtime/mcp.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `compose.yaml`
- Modify: `.env.compose.example`
- Test: `tests/unit/infrastructure/test_cache.py`
- Test: `tests/unit/infrastructure/test_model_gateway.py`
- Test: `tests/unit/observability/test_tracing.py`
- Test: `tests/integration/api/test_observability_api.py`
- Test: `tests/unit/runtime/test_container_assets.py`

**Interfaces:**
- `EvidenceCache.get(key)`, `set(key, value, ttl_seconds)` and `NullEvidenceCache`; failures return cache miss and increment a safe metric.
- `ModelGateway.explain_plan(ScenarioAssessment) -> ModelPlanExplanation` with `MockModelGateway` and `OpenAICompatibleModelGateway`.
- `Tracing` creates API, graph-node, MCP, Redis and DB spans while redacting secrets/content.
- Production settings add Redis URL, cache enabled/TTL, model mode `mock|real`, base URL, model name, API key and OTLP enable/endpoint; secrets use `SecretStr`.

- [ ] **Step 1: Write RED tests for cache safety, strict model output and span attributes**

```python
@pytest.mark.asyncio
async def test_cache_failure_becomes_miss_and_never_blocks_evidence() -> None:
    cache = RedisEvidenceCache(FailingRedis())
    assert await cache.get("inventory:SKU-1:v1") is None

@pytest.mark.asyncio
async def test_real_model_rejects_authoritative_fields() -> None:
    gateway = OpenAICompatibleModelGateway(client=client_returning({
        "summary": "维修",
        "rationale": "告警",
        "priority": "low",
    }))
    with pytest.raises(ModelOutputInvalid):
        await gateway.explain_plan(maintenance_assessment())
```

Tracing test asserts only low-cardinality scenario/node/error attributes, never JWT, API key, full message or evidence payload.

- [ ] **Step 2: Run RED**

```powershell
uv run pytest tests/unit/infrastructure/test_cache.py tests/unit/infrastructure/test_model_gateway.py tests/unit/observability/test_tracing.py tests/unit/runtime/test_container_assets.py -q
```

Expected: missing modules/settings/services.

- [ ] **Step 3: Implement minimal cache, trace and OpenAI-compatible adapter**

Cache is used only during initial/query evidence collection. `revalidate()` calls MCP directly. Real adapter uses `httpx`, strict JSON response validation, fixed timeout and limited retry; it never logs key or raw response. Compose adds Redis healthcheck and API dependency without exposing Redis port publicly. OpenTelemetry exporter is default-off; in tests use in-memory spans.

- [ ] **Step 4: Run GREEN and dependency gates**

```powershell
uv lock --check
uv run pytest tests/unit/infrastructure tests/unit/observability tests/integration/api/test_observability_api.py tests/unit/runtime/test_container_assets.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: cache bypass, strict model and trace redaction pass; lock is consistent.

- [ ] **Step 5: Commit**

```powershell
git add src/opercerta/infrastructure/cache.py src/opercerta/infrastructure/model_gateway.py src/opercerta/observability/tracing.py src/opercerta/domain/model_gateway.py src/opercerta/workflow/controlled_action_graph.py src/opercerta/api/app.py src/opercerta/runtime/mcp.py pyproject.toml uv.lock compose.yaml .env.compose.example tests/unit/infrastructure tests/unit/observability tests/integration/api/test_observability_api.py tests/unit/runtime/test_container_assets.py
git commit -m "feat: add cache tracing and real model adapter"
```

## Task 7: 跨业务固定评测、性能矩阵和三业务 Compose smoke

**执行状态：** 2026-07-20 已完成本地实现与证据；Task 8 本地发布候选和学习包随后完成，外部门禁仍待执行。

**Files:**
- Create: `data/evals/opercerta-three-business-v1.json`
- Create: `scripts/run_opercerta_evaluation.py`
- Create: `scripts/run_performance_matrix.py`
- Modify: `src/opercerta/evaluation/contracts.py`
- Modify: `src/opercerta/evaluation/executor.py`
- Modify: `src/opercerta/evaluation/runner.py`
- Modify: `scripts/verify_compose.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/unit/evaluation/test_contracts.py`
- Test: `tests/integration/evaluation/test_three_business_suite.py`
- Test: `tests/unit/runtime/test_evaluation_script.py`
- Test: `tests/unit/runtime/test_ci_assets.py`
- Test: `tests/unit/runtime/test_container_assets.py`

**Interfaces:**
- Versioned suite preserves the original 30 replenishment cases and adds transparent equipment/task cases with expected tools, terminal state, error code, approval and work-order count.
- Evaluation reports per-case actual values and aggregate counts; no LLM judge controls permission, routing or numeric correctness.
- Performance runner records environment/commit, scenario, cache mode, tool mode, repetitions, P50/P95/error rate/tool calls/cache hits and model usage.
- Compose smoke runs inventory, equipment and task success, one rejection, duplicate approval conflict, DB assertions, then recovery-only after API/MCP restart.

- [ ] **Step 1: Write RED asset and runner tests**

```python
def test_three_business_suite_preserves_replenishment_and_covers_all_scenarios() -> None:
    old = load_suite(Path("data/evals/replenishment-v3.json"))
    new = load_suite(Path("data/evals/opercerta-three-business-v1.json"))
    assert {case.case_id for case in old.cases} <= {case.case_id for case in new.cases}
    assert {case.scenario for case in new.cases} == {"inventory", "equipment", "task"}

def test_compose_smoke_checks_three_work_order_kinds_and_restart() -> None:
    text = Path("scripts/verify_compose.py").read_text(encoding="utf-8")
    for kind in ("replenishment", "repair", "task_recovery"):
        assert kind in text
```

- [ ] **Step 2: Run RED**

```powershell
uv run pytest tests/unit/evaluation/test_contracts.py tests/integration/evaluation/test_three_business_suite.py tests/unit/runtime/test_evaluation_script.py tests/unit/runtime/test_ci_assets.py tests/unit/runtime/test_container_assets.py -q
```

Expected: failures for absent dataset, scripts and three-scenario smoke.

- [ ] **Step 3: Implement transparent datasets/runners and CI smoke**

Do not hand-edit aggregate results. Report JSON is generated from per-case executions. CI uses Mock and cache configuration fixed in `.env.compose`; Real representative validation is a separately authorized local/manual release step because it needs a user secret and incurs external calls.

- [ ] **Step 4: Run GREEN, local evaluation and WSL2 Compose**

```powershell
uv run pytest tests/unit/evaluation tests/integration/evaluation tests/unit/runtime -q
uv run python scripts/run_opercerta_evaluation.py --output tmp/evals/opercerta-three-business-v1-report.json
wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/agent-portfolio/opercerta && docker compose up --build -d && python3 scripts/verify_compose.py && docker compose restart api mcp && python3 scripts/verify_compose.py --recovery-only'
wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/agent-portfolio/opercerta && docker compose down -v --remove-orphans'
```

Expected: generated report has zero infrastructure errors and records actual pass/fail counts; Compose confirms three unique work orders, rejection creates zero order, duplicate approval conflicts, and restart recovers health/state. If any assertion fails, keep the real report and debug with `systematic-debugging`; never weaken the case.

- [ ] **Step 5: Commit**

```powershell
git add data/evals/opercerta-three-business-v1.json scripts/run_opercerta_evaluation.py scripts/run_performance_matrix.py scripts/verify_compose.py src/opercerta/evaluation .github/workflows/ci.yml tests/unit/evaluation tests/integration/evaluation tests/unit/runtime
git commit -m "test: verify three-business release contracts"
```

## Task 8: 求职发布证据、交互部署与中文学习包

**执行状态（2026-07-20）：** 发布资产契约、本地完整门禁、Caddy/release Compose、一键三业务与重启 smoke、中文学习包和本地证据已完成，代码提交为 `a3994ef`。真实模型代表性验证、公网交互 HTTPS、用户掌握检查、当前远程 CI 与 Release Tag 仍待外部授权或用户操作；生产发布门禁保持 `CLOSED`。

**Files:**
- Create after real execution: `docs/release-evidence/three-business-release.md`
- Create after real execution: `docs/release-evidence/real-model-representative-validation.md`
- Create after real execution: `docs/release-evidence/performance-cache-matrix.md`
- Create: `deploy/Caddyfile`
- Create: `compose.release.yaml`
- Create: `docs/learning/OperCerta核心技术手册.md`
- Create: `docs/learning/OperCerta手动实验手册.md`
- Create: `docs/learning/OperCerta面试讲解.md`
- Modify: `docs/development-log/interview-casebook.md`
- Modify: `docs/development-log/learning-method.md`
- Modify: `docs/demo-script.md`
- Modify: `README.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-20.md` or the actual execution-date log
- Modify: portfolio source and Netlify mirror only after OperCerta status is verified
- Test: `tests/unit/runtime/test_release_assets.py`

**Interfaces:**
- One command starts the local demo; five-minute script reaches terminal states without hidden manual database writes.
- Real-model validation consumes a user-provided secret without echo and records only safe provider/model/token/latency/cost facts.
- Public interactive deployment exposes only HTTPS Web/API through Caddy or equivalent; MCP/PostgreSQL/Redis/metrics administration remain private.
- Learning package supports 30-second, 3-minute and 10-minute explanations plus manual fault labs.

- [x] **Step 1: Write failing documentation/release contract tests**

Extend repository-safety/static asset tests so they require the three learning files, three scenario names, exact public/static/local boundaries, no placeholder contacts, no Private GitHub wording in current-state files, and no release claim before an evidence document records actual commands and commit.

```python
def test_release_assets_keep_internal_services_private() -> None:
    compose = yaml.safe_load(Path("compose.release.yaml").read_text(encoding="utf-8"))
    assert "ports" in compose["services"]["caddy"]
    for service in ("postgres", "redis", "mcp"):
        assert "ports" not in compose["services"][service]

def test_learning_pack_covers_manual_failure_and_interview_explanation() -> None:
    manual = Path("docs/learning/OperCerta手动实验手册.md").read_text(encoding="utf-8")
    interview = Path("docs/learning/OperCerta面试讲解.md").read_text(encoding="utf-8")
    assert "docker compose stop mcp" in manual
    assert "exactly-once" in interview
```

Run:

```powershell
uv run pytest tests/unit/runtime/test_static_hosting_assets.py tests/unit/runtime/test_release_assets.py tests/unit/scripts/test_verify_repository_safety.py -q
```

Expected: RED until docs and truthful release metadata exist.

- [x] **Step 2: Run the fresh local release gate**

```powershell
uv sync --frozen --all-groups
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python scripts/verify_repository_safety.py
Set-Location web
npm ci
npm run test:run
npm run build
Set-Location ..
```

Then run Task 7 Compose smoke and performance matrix. Record exact outputs; do not copy old test counts into new evidence.

- [ ] **Step 3: Perform authorized real-model representative validation**

At this checkpoint ask the user to choose/provide an available OpenAI-compatible provider and place the key in an ignored local environment source. Run at least one query and one approved path per business under the fixed contract. If no key is authorized, the gate remains closed and the evidence explicitly says not executed.

- [ ] **Step 4: Deploy and verify interactive HTTPS demo**

At this checkpoint present cost/security options and obtain approval before creating paid resources. Deploy fixed Commit SHA, run migrations, health checks, three-scenario smoke, rate-limit/reset checks and rollback rehearsal. Verify desktop/mobile links from the portfolio. A sleeping/free host is acceptable only if the portfolio states the wake-up behavior and the measured response is usable; otherwise keep the static page as entry and do not claim interactive release.

- [x] **Step 5: Write evidence and learning documents from observed facts**

The manual lab must include exact WSL2/Compose/test/API/PostgreSQL/restart/failure/cleanup commands and expected observations. The technology handbook follows one request through UI → FastAPI → LangGraph → MCP → PostgreSQL/Redis → SSE/Trace. The interview guide contains architecture choices, alternatives, exactly-once explanation, checkpoint/business DB distinction, approval revalidation, three real bug stories and truthful limitations.

- [ ] **Step 6: User mastery checkpoint**

User manually completes one full business, one rule modification and one dependency failure lab, then explains the result in their own words. Record only completion facts the user actually performs. Documentation can be complete while mastery remains “练习中”; this does not block source release but blocks claiming personal proficiency in the résumé.

- [ ] **Step 7: Final remote evidence and Release Tag**

Push through the normal GitHub flow, wait for all five CI jobs including Compose smoke, then create a semantic release tag only if every release gate item is evidenced. Update the portfolio state and URLs after the tag/deploy are verified. If any gate remains open, publish an honest pre-release or keep `production release gate: CLOSED`.

- [x] **Step 8: Commit documentation and evidence separately**

```powershell
git add README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs/development-log docs/learning docs/demo-script.md docs/release-evidence/three-business-release.md docs/release-evidence/real-model-representative-validation.md docs/release-evidence/performance-cache-matrix.md
git commit -m "docs: record three-business release evidence"
```

Expected: no generated secret, raw token or unverified metric is staged; user `.gitignore` remains outside the commit.

## Plan Self-Review

- Spec coverage: Tasks 1–4 cover three business contracts, tools, approval, recovery and work orders; Task 5 covers one-page React/SSE; Task 6 covers Redis, OpenTelemetry and real model; Task 7 covers fixed evaluation, performance and Compose; Task 8 covers deployment, Release, evidence, learning and interview readiness.
- Placeholder scan: the plan contains no unresolved marker or unspecified error-handling step.
- Type consistency: `ObjectType`, `ScenarioKind`, discriminated `ApprovalBinding` and three typed work-order parameters are defined in Task 1; the shared scenario protocol is introduced in Task 2 and concrete domain types are added in Tasks 3–4 before frontend/evaluation consumption.
- Scope: no ForenTrail code, no old company material, no arbitrary execution and no production-high-availability claim are included.
- Execution choice: user previously selected Inline Execution and requested no subagents; implementation uses `superpowers:executing-plans` with review checkpoints after Tasks 2, 4, 7 and 8.
