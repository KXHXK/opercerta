import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from pytest import MonkeyPatch
from sqlalchemy import delete
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.api.app import (
    AppRuntime,
    ProductionSettings,
    create_app,
    create_production_app,
)
from opercerta.api.auth import DemoAccount, JwtAuthenticator, JwtSettings
from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.application.operation_runner import OperationRunner
from opercerta.application.scenario_registry import build_default_scenario_registry
from opercerta.domain.contracts import (
    ActionType,
    ObjectType,
    OperationRequest,
)
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operations
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.controlled_action_graph import build_controlled_action_graph
from opercerta.workflow.controlled_action_recovery import (
    ControlledActionRecoveryCoordinator,
)
from tests.integration.mcp.conftest import McpServerHarness
from tests.integration.mcp.conftest import (
    mcp_server as _mcp_server_fixture,
)

mcp_server = _mcp_server_fixture

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


@dataclass(slots=True)
class ApiHarness:
    client: AsyncClient
    operations: OperationRepository
    mcp_server: McpServerHarness
    authenticator: JwtAuthenticator
    runner: OperationRunner
    approvals: ApprovalRepository
    gateway: McpToolGateway
    operation_ids: list[UUID] = field(default_factory=list)

    def headers(self, account: DemoAccount) -> dict[str, str]:
        token = self.authenticator.issue_demo_token(account, datetime.now(UTC))
        return {"Authorization": f"Bearer {token}"}

    async def create_operation(self, sku: str = "SKU-LOW-001") -> dict[str, object]:
        response = await self.client.post(
            "/api/v1/operations",
            headers=self.headers(DemoAccount.OPERATOR),
            json={
                "message": f"为 {sku} 生成补货工单",
                "requested_action": "create_work_order",
                "object_type": "inventory",
                "object_id": sku,
            },
        )
        body = cast(dict[str, object], response.json())
        if response.status_code == 202:
            self.operation_ids.append(UUID(str(body["operation_id"])))
        body["_status_code"] = response.status_code
        return body

    async def create_equipment_operation(
        self, equipment_id: str = "EQ-PUMP-001"
    ) -> dict[str, object]:
        response = await self.client.post(
            "/api/v1/operations",
            headers=self.headers(DemoAccount.OPERATOR),
            json={
                "message": f"为 {equipment_id} 创建维修工单",
                "requested_action": "create_work_order",
                "object_type": "equipment",
                "object_id": equipment_id,
            },
        )
        body = cast(dict[str, object], response.json())
        if response.status_code == 202:
            self.operation_ids.append(UUID(str(body["operation_id"])))
        body["_status_code"] = response.status_code
        return body

    async def create_task_operation(self, task_id: str = "TASK-BLOCKED-001") -> dict[str, object]:
        response = await self.client.post(
            "/api/v1/operations",
            headers=self.headers(DemoAccount.OPERATOR),
            json={
                "message": f"recover blocked task {task_id}",
                "requested_action": "create_work_order",
                "object_type": "task",
                "object_id": task_id,
            },
        )
        body = cast(dict[str, object], response.json())
        if response.status_code == 202:
            self.operation_ids.append(UUID(str(body["operation_id"])))
        body["_status_code"] = response.status_code
        return body


class UnavailableRunner:
    async def start(self, request: object) -> UUID:
        del request
        raise RuntimeError("postgresql password traceback 127.0.0.1:55432")


def assert_safe_response(body: object) -> None:
    serialized = json.dumps(body, ensure_ascii=False)
    assert "postgresql" not in serialized.lower()
    assert "password" not in serialized.lower()
    assert "traceback" not in serialized.lower()
    assert "127.0.0.1:55432" not in serialized


def approval_payload(
    detail: dict[str, object],
    decision: str,
) -> dict[str, object]:
    binding = cast(dict[str, object], detail["approval_binding"])
    return {
        "decision": decision,
        "reason": f"{decision} after reviewing API evidence",
        "expected_binding": binding,
    }


@asynccontextmanager
async def open_api_harness(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    *,
    graph_clock: Callable[[], datetime] = lambda: NOW,
    runner_clock: Callable[[], datetime] = lambda: NOW,
    approval_ttl_seconds: int = 300,
) -> AsyncIterator[ApiHarness]:
    operations_repository = OperationRepository(engine)
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("integration-test-jwt-signing-key"),
            issuer="opercerta-integration-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    async with open_checkpointer(checkpoint_database_url) as saver:
        registry = build_default_scenario_registry()
        graph = build_controlled_action_graph(
            saver,
            operations_repository,
            EvidenceRepository(engine),
            McpToolGateway(mcp_server.url, timeout_seconds=2),
            MockModelGateway(),
            graph_clock,
            registry,
            approval_ttl_seconds=approval_ttl_seconds,
        )
        runner = OperationRunner(
            graph,
            ApprovalRepository(engine),
            operations_repository,
            ControlledActionRecoveryCoordinator(graph, operations_repository),
            ApprovalExpiryService(operations_repository, runner_clock),
            runner_clock,
            registry,
        )
        app = create_app(
            AppRuntime(
                runner=runner,
                operations=operations_repository,
                authenticator=authenticator,
            )
        )
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        operator_token = authenticator.issue_demo_token(
            DemoAccount.OPERATOR,
            datetime.now(UTC),
        )
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {operator_token}"},
        ) as client:
            harness = ApiHarness(
                client=client,
                operations=operations_repository,
                mcp_server=mcp_server,
                authenticator=authenticator,
                runner=runner,
                approvals=ApprovalRepository(engine),
                gateway=McpToolGateway(mcp_server.url, timeout_seconds=2),
            )
            try:
                yield harness
            finally:
                for operation_id in harness.operation_ids:
                    await saver.adelete_thread(str(operation_id))
                async with engine.begin() as connection:
                    if harness.operation_ids:
                        await connection.execute(
                            delete(operations).where(operations.c.id.in_(harness.operation_ids))
                        )


@pytest.mark.asyncio
async def test_create_and_query_low_inventory_operation(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        accepted = await harness.create_operation()
        assert accepted.pop("_status_code") == 202
        assert set(accepted) == {"operation_id", "status", "created_at"}
        assert accepted["status"] == "awaiting_approval"

        operation_id = UUID(str(accepted["operation_id"]))
        response = await harness.client.get(f"/api/v1/operations/{operation_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["assessment"]["recommended_quantity"] == 18
        assert detail["approval_binding"]["parameters"]["recommended_quantity"] == 18
        assert detail["approval"] is None
        assert detail["work_order"] is None
        assert detail["last_audit_sequence"] > 0
        assert len(detail["evidence"]) == 2


@pytest.mark.asyncio
async def test_create_approve_and_query_equipment_repair_operation(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        accepted = await harness.create_equipment_operation()
        assert accepted.pop("_status_code") == 202
        assert accepted["status"] == "awaiting_approval"
        operation_id = UUID(str(accepted["operation_id"]))

        before = await harness.client.get(f"/api/v1/operations/{operation_id}")
        assert before.status_code == 200
        detail = before.json()
        assert detail["assessment"]["priority"] == "urgent"
        assert detail["approval_binding"]["scenario"] == "equipment"

        approved = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=approval_payload(detail, "approved"),
        )
        assert approved.status_code == 202
        assert approved.json()["status"] == "completed"

        after = await harness.client.get(f"/api/v1/operations/{operation_id}")
        assert after.status_code == 200
        completed = after.json()
        assert completed["work_order"]["payload"]["kind"] == "repair"
        assert completed["work_order"]["payload"]["equipment_id"] == "EQ-PUMP-001"


@pytest.mark.asyncio
async def test_create_approve_and_query_task_recovery_operation(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        accepted = await harness.create_task_operation()
        assert accepted.pop("_status_code") == 202
        assert accepted["status"] == "awaiting_approval"
        operation_id = UUID(str(accepted["operation_id"]))

        before = await harness.client.get(f"/api/v1/operations/{operation_id}")
        assert before.status_code == 200
        detail = before.json()
        assert detail["assessment"]["reason"] == "blocked"
        assert detail["approval_binding"]["scenario"] == "task"

        approved = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=approval_payload(detail, "approved"),
        )
        assert approved.status_code == 202
        assert approved.json()["status"] == "completed"

        completed = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        assert completed["work_order"]["payload"]["kind"] == "task_recovery"
        assert completed["work_order"]["payload"]["task_id"] == "TASK-BLOCKED-001"
        openapi = (await harness.client.get("/openapi.json")).json()
        accepted_schema = openapi["components"]["schemas"]["OperationAccepted"]
        assert accepted_schema["properties"]["created_at"]["format"] == "date-time"
        assert_safe_response([accepted, detail])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_type", "object_id"),
    [
        ("inventory", "SKU-LOW-001"),
        ("equipment", "EQ-PUMP-001"),
        ("task", "TASK-BLOCKED-001"),
    ],
)
async def test_query_returns_evidence_without_approval_or_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    object_type: str,
    object_id: str,
) -> None:
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        response = await harness.client.post(
            "/api/v1/operations",
            headers=harness.headers(DemoAccount.OPERATOR),
            json={
                "message": f"查询 {object_id} 当前状态",
                "requested_action": "query",
                "object_type": object_type,
                "object_id": object_id,
            },
        )

        assert response.status_code == 202
        accepted = response.json()
        operation_id = UUID(accepted["operation_id"])
        harness.operation_ids.append(operation_id)
        detail = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        assert detail["status"] == "completed"
        assert detail["result"]["outcome"] == "query_completed"
        assert detail["assessment"] is not None
        assert len(detail["evidence"]) == 2
        assert detail["approval_binding"] is None
        assert detail["approval"] is None
        assert detail["work_order"] is None


@pytest.mark.asyncio
async def test_authorized_audit_event_stream_replays_from_last_event_id(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        all_events = await harness.client.get(
            f"/api/v1/operations/{operation_id}/events",
            headers=harness.headers(DemoAccount.AUDITOR),
        )
        resumed = await harness.client.get(
            f"/api/v1/operations/{operation_id}/events",
            headers={
                **harness.headers(DemoAccount.AUDITOR),
                "Last-Event-ID": "2",
            },
        )

    assert all_events.status_code == 200
    assert all_events.headers["content-type"].startswith("text/event-stream")
    assert "id: 1" in all_events.text
    assert "event: operation_received" in all_events.text
    assert resumed.status_code == 200
    assert "id: 1" not in resumed.text
    assert "id: 3" in resumed.text


@pytest.mark.asyncio
async def test_audit_event_stream_rejects_anonymous_and_invalid_cursor(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(engine, checkpoint_database_url, mcp_server) as harness:
        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        anonymous = await harness.client.get(
            f"/api/v1/operations/{operation_id}/events",
            headers={"Authorization": ""},
        )
        invalid_cursor = await harness.client.get(
            f"/api/v1/operations/{operation_id}/events",
            headers={
                **harness.headers(DemoAccount.AUDITOR),
                "Last-Event-ID": "not-a-sequence",
            },
        )

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "authentication_required"
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["code"] == "request_validation_failed"


@pytest.mark.asyncio
async def test_authentication_and_roles_protect_operations_before_writing(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        unauthenticated = await harness.client.post(
            "/api/v1/operations",
            headers={"Authorization": "Bearer"},
            json={
                "message": "create a replenishment work order",
                "requested_action": "create_work_order",
                "object_type": "inventory",
                "object_id": "SKU-LOW-001",
            },
        )
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "authentication_required"
        assert harness.operation_ids == []

        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        detail = (
            await harness.client.get(
                f"/api/v1/operations/{operation_id}",
                headers=harness.headers(DemoAccount.OPERATOR),
            )
        ).json()
        forbidden = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.OPERATOR),
            json=approval_payload(detail, "approved"),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["code"] == "permission_denied"

        approved = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=approval_payload(detail, "approved"),
        )
        assert approved.status_code == 202
        final = (
            await harness.client.get(
                f"/api/v1/operations/{operation_id}",
                headers=harness.headers(DemoAccount.AUDITOR),
            )
        ).json()
        assert final["approval"]["approver_id"] == "demo.approver"


@pytest.mark.asyncio
async def test_approve_with_exact_binding_completes_and_duplicate_returns_409(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        detail = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        payload = approval_payload(detail, "approved")

        approved = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=payload,
        )
        assert approved.status_code == 202
        assert approved.json()["status"] == "completed"

        final = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        assert final["status"] == "completed"
        assert final["approval"]["decision"] == "approved"
        assert final["work_order"]["payload"] == {
            "approved_plan_hash": final["plan"]["plan_hash"],
            "quantity": 18,
            "sku": "SKU-LOW-001",
        }
        assert final["result"]["outcome"] == "work_order_completed"

        duplicate = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=payload,
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {
            "code": "approval_already_decided",
            "message": "该操作已经完成审批决定。",
        }
        assert_safe_response([approved.json(), final, duplicate.json()])


@pytest.mark.asyncio
async def test_reject_with_exact_binding_returns_rejected_without_work_order(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        detail = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()

        rejected = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=approval_payload(detail, "rejected"),
        )
        assert rejected.status_code == 202
        assert rejected.json()["status"] == "rejected"

        final = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        assert final["status"] == "rejected"
        assert final["approval"]["decision"] == "rejected"
        assert final["work_order"] is None


@pytest.mark.asyncio
async def test_validation_missing_and_stale_binding_use_safe_error_envelopes(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
    ) as harness:
        invalid = await harness.client.post(
            "/api/v1/operations",
            json={
                "message": "",
                "requested_action": "create_work_order",
                "object_type": "inventory",
                "unexpected": "secret",
            },
        )
        assert invalid.status_code == 422
        assert invalid.json() == {
            "code": "request_validation_failed",
            "message": "请求内容无效。",
        }
        unsupported = await harness.client.post(
            "/api/v1/operations",
            json={
                "message": "查询未知对象状态",
                "requested_action": "query",
                "object_type": "building",
                "object_id": "BUILDING-001",
            },
        )
        assert unsupported.status_code == 422
        assert unsupported.json() == {
            "code": "request_validation_failed",
            "message": "请求内容无效。",
        }

        missing = await harness.client.get(f"/api/v1/operations/{uuid4()}")
        assert missing.status_code == 404
        assert missing.json() == {
            "code": "operation_not_found",
            "message": "未找到指定操作。",
        }

        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        detail = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        stale = approval_payload(detail, "approved")
        cast(dict[str, object], stale["expected_binding"])["plan_hash"] = "0" * 64
        mismatch = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=stale,
        )
        assert mismatch.status_code == 409
        assert mismatch.json() == {
            "code": "approval_snapshot_mismatch",
            "message": "审批依据已变化。请刷新后重试。",
        }
        assert_safe_response(
            [
                invalid.json(),
                unsupported.json(),
                missing.json(),
                mismatch.json(),
            ]
        )


@pytest.mark.asyncio
async def test_expired_approval_returns_409_and_inventory_missing_is_queryable(
    engine: AsyncEngine,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
) -> None:
    async with open_api_harness(
        engine,
        checkpoint_database_url,
        mcp_server,
        runner_clock=lambda: NOW + timedelta(seconds=2),
        approval_ttl_seconds=1,
    ) as harness:
        accepted = await harness.create_operation()
        operation_id = UUID(str(accepted["operation_id"]))
        detail = (await harness.client.get(f"/api/v1/operations/{operation_id}")).json()
        expired = await harness.client.post(
            f"/api/v1/operations/{operation_id}/approval",
            headers=harness.headers(DemoAccount.APPROVER),
            json=approval_payload(detail, "approved"),
        )
        assert expired.status_code == 409
        assert expired.json() == {
            "code": "approval_expired",
            "message": "审批已过期。",
        }

        missing_inventory = await harness.create_operation("SKU-MISSING-001")
        assert missing_inventory["_status_code"] == 202
        missing_id = UUID(str(missing_inventory["operation_id"]))
        failed = (await harness.client.get(f"/api/v1/operations/{missing_id}")).json()
        assert failed["status"] == "failed"
        assert failed["error"]["code"] == "inventory_not_found"
        assert_safe_response([expired.json(), failed])


@pytest.mark.asyncio
async def test_unexpected_dependency_error_returns_fixed_503_without_details(
    engine: AsyncEngine,
) -> None:
    runtime = AppRuntime(
        runner=cast(OperationRunner, UnavailableRunner()),
        operations=OperationRepository(engine),
    )
    app = create_app(runtime)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/operations",
            json={
                "message": "为低库存物料生成补货工单",
                "requested_action": "create_work_order",
                "object_type": "inventory",
                "object_id": "SKU-LOW-001",
            },
        )

    assert response.status_code == 503
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "依赖服务暂时不可用。",
    }
    assert_safe_response(response.json())


@pytest.mark.asyncio
async def test_production_lifespan_loads_environment_and_recovers_once(
    engine: AsyncEngine,
    database_url: SecretStr,
    checkpoint_database_url: SecretStr,
    mcp_server: McpServerHarness,
    monkeypatch: MonkeyPatch,
) -> None:
    operations_repository = OperationRepository(engine)
    operation_id = await operations_repository.create(
        OperationRequest(
            message="启动时恢复低库存补货操作",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
        )
    )
    monkeypatch.setenv(
        "OPERCERTA_DATABASE_URL",
        database_url.get_secret_value(),
    )
    monkeypatch.setenv("OPERCERTA_MCP_URL", mcp_server.url)
    monkeypatch.setenv("OPERCERTA_MCP_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("OPERCERTA_APPROVAL_TTL_SECONDS", "300")
    monkeypatch.setenv("OPERCERTA_MODEL_MODE", "mock")
    monkeypatch.setenv("OPERCERTA_JWT_SIGNING_KEY", "production-lifespan-test-key")
    monkeypatch.setenv("OPERCERTA_JWT_ISSUER", "opercerta-production-test")
    monkeypatch.setenv("OPERCERTA_JWT_AUDIENCE", "opercerta-api-test")
    monkeypatch.setenv("OPERCERTA_JWT_TTL_SECONDS", "300")
    monkeypatch.setenv("OPERCERTA_DEMO_TOKEN_ENABLED", "true")
    app = create_production_app(clock=lambda: NOW)

    try:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app, raise_app_exceptions=False)
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                token = await client.post(
                    "/api/v1/auth/demo-token",
                    json={"account": "auditor"},
                )
                response = await client.get(
                    f"/api/v1/operations/{operation_id}",
                    headers={"Authorization": f"Bearer {token.json()['access_token']}"},
                )

        assert response.status_code == 200
        assert response.json()["status"] == "awaiting_approval"
    finally:
        async with open_checkpointer(checkpoint_database_url) as saver:
            await saver.adelete_thread(str(operation_id))
        await cleanup_operation(engine, operation_id)


async def cleanup_operation(engine: AsyncEngine, operation_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(operations).where(operations.c.id == operation_id))


@pytest.mark.asyncio
async def test_production_lifespan_restores_password_environment_on_engine_error(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGPASSWORD", "original-test-value")
    invalid_async_url = URL.create(
        drivername="postgresql",
        username="test-user",
        password="temporary-test-value",
        host="127.0.0.1",
        database="test-db",
    ).render_as_string(hide_password=False)
    settings = ProductionSettings.model_validate(
        {
            "OPERCERTA_DATABASE_URL": invalid_async_url,
            "OPERCERTA_MCP_URL": "http://127.0.0.1:8001/mcp",
            "OPERCERTA_MCP_TIMEOUT_SECONDS": 2,
            "OPERCERTA_APPROVAL_TTL_SECONDS": 300,
            "OPERCERTA_MODEL_MODE": "mock",
            "OPERCERTA_JWT_SIGNING_KEY": "production-engine-error-test-key",
            "OPERCERTA_JWT_ISSUER": "opercerta-production-test",
            "OPERCERTA_JWT_AUDIENCE": "opercerta-api-test",
            "OPERCERTA_JWT_TTL_SECONDS": 300,
            "OPERCERTA_DEMO_TOKEN_ENABLED": False,
        }
    )
    app = create_production_app(settings, clock=lambda: NOW)

    with pytest.raises(ModuleNotFoundError):
        async with app.router.lifespan_context(app):
            pass

    assert os.environ["PGPASSWORD"] == "original-test-value"
