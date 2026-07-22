from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.api.app import AppRuntime, create_app
from opercerta.api.auth import DemoAccount, JwtAuthenticator, JwtSettings
from opercerta.domain.agent_trace import (
    AgentRunStatus,
    AgentTraceActor,
    AgentTraceEventInput,
    AgentTraceEventType,
    AgentTraceStatus,
)
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.scenarios import ScenarioKind
from opercerta.infrastructure.db.agent_trace_repository import AgentTraceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import agent_runs, operations

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


@dataclass
class UnusedRunner:
    async def start(self, request: OperationRequest) -> UUID:
        del request
        raise AssertionError("not used")


def authenticator() -> JwtAuthenticator:
    return JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("agent-trace-api-test-signing-key"),
            issuer="opercerta-agent-trace-test",
            audience="opercerta-agent-trace-api",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )


def headers(auth: JwtAuthenticator, account: DemoAccount) -> dict[str, str]:
    token = auth.issue_demo_token(account, datetime.now(UTC))
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_trace_snapshot_and_sse_enforce_role_and_operation_scope(
    engine: AsyncEngine,
) -> None:
    operations_repository = OperationRepository(engine)
    trace_repository = AgentTraceRepository(engine)
    operation_id = await operations_repository.create(
        OperationRequest(
            message="为 SKU-LOW-001 生成补货工单",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
        )
    )
    auth = authenticator()
    run = await trace_repository.start_run(
        operation_id=operation_id,
        scenario=ScenarioKind.INVENTORY,
        model_mode="mock",
        run_key="primary",
        started_at=NOW,
    )
    await trace_repository.append_event(
        run.id,
        AgentTraceEventInput(
            semantic_key="perception:intent",
            event_type=AgentTraceEventType.PERCEPTION,
            actor_type=AgentTraceActor.USER,
            node="intent_envelope",
            status=AgentTraceStatus.COMPLETED,
            safe_input={"object_id": "SKU-LOW-001"},
            safe_output={"summary": "有限表单已编码。"},
            started_at=NOW,
            ended_at=NOW,
        ),
    )
    await trace_repository.finish_run(run.id, AgentRunStatus.AWAITING_HUMAN, NOW)
    await trace_repository.claim_owner(operation_id, "demo.operator")
    app = create_app(
        AppRuntime(
            runner=UnusedRunner(),  # type: ignore[arg-type]
            operations=operations_repository,
            authenticator=auth,
            traces=trace_repository,
            demo_admin_enabled=False,
        )
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            operator_allowed = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.OPERATOR),
            )
            async with engine.begin() as connection:
                await connection.execute(
                    update(agent_runs)
                    .where(agent_runs.c.operation_id == operation_id)
                    .values(initiated_by="other.operator")
                )
            operator_denied = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.OPERATOR),
            )
            approver_denied = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.APPROVER),
            )
            auditor = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.AUDITOR),
            )
            demo_admin_denied = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.DEMO_ADMIN),
            )
            async with engine.begin() as connection:
                await connection.execute(
                    update(operations)
                    .where(operations.c.id == operation_id)
                    .values(status="awaiting_approval")
                )
            approver = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace",
                headers=headers(auth, DemoAccount.APPROVER),
            )
            stream = await client.get(
                f"/api/v1/operations/{operation_id}/agent-trace/events",
                headers=headers(auth, DemoAccount.AUDITOR),
            )

        assert operator_allowed.status_code == 200
        assert operator_denied.status_code == 403
        assert approver_denied.status_code == 403
        assert demo_admin_denied.status_code == 403
        assert auditor.status_code == 200
        assert auditor.json()["events"][0]["event_type"] == "perception"
        assert approver.status_code == 200
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "event: agent_trace" in stream.text
        assert "id: 1" in stream.text
    finally:
        async with engine.begin() as connection:
            await connection.execute(delete(operations).where(operations.c.id == operation_id))
