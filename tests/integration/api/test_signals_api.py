import asyncio
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine

from opercerta.api.app import AppRuntime, create_app
from opercerta.api.auth import DemoAccount, JwtAuthenticator, JwtSettings
from opercerta.application.signal_detection import SignalScanResult
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.replenishment import OperationError
from opercerta.domain.signals import SignalDraft
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.schema import operational_signals, operations
from opercerta.infrastructure.db.signal_repository import SignalRepository

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=UTC)


class RepositoryRunner:
    def __init__(self, operations_repository: OperationRepository) -> None:
        self._operations = operations_repository

    async def start(self, request: OperationRequest) -> UUID:
        return await self._operations.create(request)


class StaticSignalDetector:
    def __init__(self, result: SignalScanResult) -> None:
        self._result = result

    async def scan(self) -> SignalScanResult:
        return self._result


def inventory_signal() -> SignalDraft:
    return SignalDraft(
        signal_type="inventory_shortage",
        object_type="inventory",
        object_id="SKU-LOW-001",
        source="demo_watchlist.v1",
        severity="medium",
        reason_code="inventory_below_reorder_point",
        facts_hash="b" * 64,
        facts={
            "available_quantity": 12,
            "reorder_point": 15,
            "target_stock": 30,
            "recommended_quantity": 18,
        },
        detected_at=NOW,
    )


@pytest.mark.asyncio
async def test_signal_is_listed_and_investigation_atomically_binds_operation(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    signal = await signals.upsert_detected(inventory_signal())
    operation_repository = OperationRepository(engine)
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("signal-api-test-signing-key-at-least-32-bytes"),
            issuer="signal-api-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    app = create_app(
        AppRuntime(
            runner=cast(Any, RepositoryRunner(operation_repository)),
            operations=operation_repository,
            authenticator=authenticator,
            signals=signals,
            signal_detector=cast(
                Any,
                StaticSignalDetector(
                    SignalScanResult(
                        signals=(signal,),
                        issues=(),
                        scanned_count=1,
                        scanned_at=NOW,
                    )
                ),
            ),
        )
    )
    token = authenticator.issue_demo_token(DemoAccount.OPERATOR, datetime.now(UTC))
    operation_id: UUID | None = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            listed = await client.get("/api/v1/signals")
            assert listed.status_code == 200
            assert listed.json()[0]["id"] == str(signal.id)

            scanned = await client.post("/api/v1/signals/scan")
            assert scanned.status_code == 200
            assert scanned.json()["signals"][0]["id"] == str(signal.id)
            assert scanned.json()["affected_cases"][0]["case_key"] == ("inventory:SKU-LOW-001")
            assert scanned.json()["affected_cases"][0]["lineage"][0]["id"] == str(signal.id)

            accepted = await client.post(f"/api/v1/signals/{signal.id}/investigate")
            assert accepted.status_code == 202
            operation_id = UUID(accepted.json()["operation_id"])

            repeated = await client.post(f"/api/v1/signals/{signal.id}/investigate")
            assert repeated.status_code == 409
            assert repeated.json()["code"] == "signal_already_claimed"

        linked = await signals.load(signal.id)
        assert linked.status.value == "investigating"
        assert linked.operation_id == operation_id
        detail = await operation_repository.load_detail(operation_id)
        request = OperationRequest.model_validate(detail.snapshot.request)
        assert request.trigger_signal_id == signal.id
        assert request.object_id == "SKU-LOW-001"
    finally:
        async with engine.begin() as connection:
            if operation_id is not None:
                await connection.execute(delete(operations).where(operations.c.id == operation_id))
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == signal.id)
            )


@pytest.mark.asyncio
async def test_direct_write_intent_is_rejected_when_signal_flow_is_enabled(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("signal-api-test-signing-key-at-least-32-bytes"),
            issuer="signal-api-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    app = create_app(
        AppRuntime(
            runner=cast(Any, RepositoryRunner(operation_repository)),
            operations=operation_repository,
            authenticator=authenticator,
            signals=signals,
        )
    )
    token = authenticator.issue_demo_token(DemoAccount.OPERATOR, datetime.now(UTC))
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        response = await client.post(
            "/api/v1/operations",
            json={
                "message": "直接创建补货处置",
                "requested_action": ActionType.CREATE_WORK_ORDER.value,
                "object_type": ObjectType.INVENTORY.value,
                "object_id": "SKU-LOW-001",
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_failed"


@pytest.mark.asyncio
async def test_attention_signal_retry_preserves_old_operation_and_starts_successor(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    original = await signals.upsert_detected(inventory_signal())
    original_operation_id = await operation_repository.create(
        OperationRequest(
            message="首次调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=original.id,
        )
    )
    await operation_repository.mark_failed(
        original_operation_id,
        OperationError(code="dependency_unavailable", message="Dependency unavailable."),
    )
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("signal-api-test-signing-key-at-least-32-bytes"),
            issuer="signal-api-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    app = create_app(
        AppRuntime(
            runner=cast(Any, RepositoryRunner(operation_repository)),
            operations=operation_repository,
            authenticator=authenticator,
            signals=signals,
        )
    )
    operator_token = authenticator.issue_demo_token(DemoAccount.OPERATOR, datetime.now(UTC))
    approver_token = authenticator.issue_demo_token(DemoAccount.APPROVER, datetime.now(UTC))
    successor_operation_id: UUID | None = None
    successor_id: UUID | None = None
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            forbidden = await client.post(
                f"/api/v1/signals/{original.id}/retry",
                headers={"Authorization": f"Bearer {approver_token}"},
            )
            assert forbidden.status_code == 403

            attempts = await asyncio.gather(
                *[
                    client.post(
                        f"/api/v1/signals/{original.id}/retry",
                        headers={"Authorization": f"Bearer {operator_token}"},
                    )
                    for _ in range(10)
                ]
            )
            accepted = next(response for response in attempts if response.status_code == 202)
            conflicts = [response for response in attempts if response.status_code == 409]
            assert accepted.status_code == 202
            assert len(conflicts) == 9
            assert all(
                response.json()["code"] == "signal_already_claimed" for response in conflicts
            )
            successor_operation_id = UUID(accepted.json()["operation_id"])

            repeated = await client.post(
                f"/api/v1/signals/{original.id}/retry",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert repeated.status_code == 409
            assert repeated.json()["code"] == "signal_already_claimed"

        active = await signals.list_active()
        successor = next(item for item in active if item.predecessor_signal_id == original.id)
        successor_id = successor.id
        assert successor.operation_id == successor_operation_id
        assert successor.status.value == "investigating"
        assert (await operation_repository.load_detail(original_operation_id)).status.value == (
            "failed"
        )
        successor_detail = await operation_repository.load_detail(successor_operation_id)
        successor_request = OperationRequest.model_validate(successor_detail.snapshot.request)
        assert successor_request.trigger_signal_id == successor.id
    finally:
        async with engine.begin() as connection:
            if successor_operation_id is not None:
                await connection.execute(
                    delete(operations).where(operations.c.id == successor_operation_id)
                )
            await connection.execute(
                delete(operations).where(operations.c.id == original_operation_id)
            )
            if successor_id is not None:
                await connection.execute(
                    delete(operational_signals).where(operational_signals.c.id == successor_id)
                )
            await connection.execute(
                delete(operational_signals).where(operational_signals.c.id == original.id)
            )


@pytest.mark.asyncio
async def test_signal_cases_aggregate_lineage_and_current_operation_for_read_roles(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    original = await signals.upsert_detected(inventory_signal())
    original_operation_id = await operation_repository.create(
        OperationRequest(
            message="首次调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=original.id,
        )
    )
    await operation_repository.mark_failed(
        original_operation_id,
        OperationError(code="dependency_unavailable", message="Dependency unavailable."),
    )
    successor = await signals.create_successor(
        original.id,
        NOW.replace(microsecond=1),
    )
    successor_operation_id = await operation_repository.create(
        OperationRequest(
            message="重新调查库存异常",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=successor.id,
        )
    )
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("signal-api-test-signing-key-at-least-32-bytes"),
            issuer="signal-api-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    app = create_app(
        AppRuntime(
            runner=cast(Any, RepositoryRunner(operation_repository)),
            operations=operation_repository,
            authenticator=authenticator,
            signals=signals,
        )
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            for account in (
                DemoAccount.OPERATOR,
                DemoAccount.APPROVER,
                DemoAccount.AUDITOR,
            ):
                token = authenticator.issue_demo_token(account, datetime.now(UTC))
                response = await client.get(
                    "/api/v1/signal-cases",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response.status_code == 200
                cases = response.json()
                assert len(cases) == 1
                case = cases[0]
                assert case["case_key"] == "inventory:SKU-LOW-001"
                assert case["current_signal"]["id"] == str(successor.id)
                assert case["current_operation"]["operation_id"] == str(successor_operation_id)
                assert case["current_operation"]["status"] == "received"
                assert case["history_count"] == 1
                assert [item["id"] for item in case["lineage"]] == [
                    str(original.id),
                    str(successor.id),
                ]

            raw_signals = await client.get(
                "/api/v1/signals",
                headers={
                    "Authorization": "Bearer "
                    + authenticator.issue_demo_token(DemoAccount.AUDITOR, datetime.now(UTC))
                },
            )
            assert raw_signals.status_code == 200
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operations).where(
                    operations.c.id.in_([original_operation_id, successor_operation_id])
                )
            )
            await connection.execute(
                delete(operational_signals).where(
                    operational_signals.c.id.in_([successor.id, original.id])
                )
            )


@pytest.mark.asyncio
async def test_signal_case_current_is_terminal_leaf_not_actionable_ancestor(
    engine: AsyncEngine,
) -> None:
    signals = SignalRepository(engine)
    operation_repository = OperationRepository(engine)
    original = await signals.upsert_detected(inventory_signal())
    original_operation_id = await operation_repository.create(
        OperationRequest(
            message="Investigate initial inventory signal",
            requested_action=ActionType.CREATE_WORK_ORDER,
            object_type=ObjectType.INVENTORY,
            object_id="SKU-LOW-001",
            trigger_signal_id=original.id,
        )
    )
    await operation_repository.mark_failed(
        original_operation_id,
        OperationError(code="dependency_unavailable", message="Dependency unavailable."),
    )
    successor = await signals.create_successor(original.id, NOW.replace(microsecond=2))
    try:
        async with engine.begin() as connection:
            await connection.execute(
                update(operational_signals)
                .where(operational_signals.c.id == successor.id)
                .values(status="resolved", resolved_at=NOW, updated_at=NOW)
            )

        cases = await signals.list_cases(object_keys={(ObjectType.INVENTORY.value, "SKU-LOW-001")})

        assert len(cases) == 1
        assert cases[0].current_signal.id == successor.id
        assert cases[0].current_signal.status.value == "resolved"
        assert cases[0].history_count == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                delete(operational_signals).where(
                    operational_signals.c.id.in_([successor.id, original.id])
                )
            )
            await connection.execute(
                delete(operations).where(operations.c.id == original_operation_id)
            )
