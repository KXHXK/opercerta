import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.types import Receive, Scope, Send

from opercerta.api.app import (
    AppRuntime,
    ObservabilityConfig,
    ObservabilityMiddleware,
    create_app,
)
from opercerta.api.auth import DemoAccount, JwtAuthenticator, JwtSettings
from opercerta.application.operation_runner import OperationRunner
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.observability.context import current_request_id
from opercerta.observability.logging import SafeJsonFormatter
from opercerta.observability.metrics import ApiMetrics

SERVER_REQUEST_ID = "00000000-0000-4000-8000-000000000001"


def empty_runtime() -> AppRuntime:
    return AppRuntime(
        runner=cast(OperationRunner, object()),
        operations=cast(ReplenishmentOperationRepository, object()),
    )


@dataclass
class AuditOperations:
    async def load_detail(self, operation_id: UUID) -> SimpleNamespace:
        del operation_id
        return SimpleNamespace(
            audit_events=(
                SimpleNamespace(
                    sequence=1,
                    event_type="operation_received",
                    payload={},
                ),
                SimpleNamespace(
                    sequence=2,
                    event_type="approval_requested",
                    payload={},
                ),
            )
        )


@pytest.mark.asyncio
async def test_server_request_id_ignores_untrusted_header_and_metrics_default_off() -> (
    None
):
    app = create_app(
        empty_runtime(),
        observability=ObservabilityConfig(
            request_id_factory=lambda: SERVER_REQUEST_ID,
        ),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        live = await client.get(
            "/health/live",
            headers={"X-Request-ID": "attacker-value"},
        )
        metrics = await client.get("/metrics")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == SERVER_REQUEST_ID
    assert "attacker-value" not in live.headers.values()
    assert metrics.status_code == 404
    assert "opercerta_http_requests" not in metrics.text


@pytest.mark.asyncio
async def test_unhandled_error_has_safe_503_request_id_metric_and_log() -> None:
    metrics = ApiMetrics.create()

    async def unsafe_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        raise RuntimeError("Bearer leaked-token password=secret")

    observed_app = ObservabilityMiddleware(
        unsafe_app,
        metrics=metrics,
        request_id_factory=lambda: SERVER_REQUEST_ID,
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeJsonFormatter("opercerta-api"))
    logger = logging.getLogger("opercerta.api.app")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        transport = ASGITransport(app=observed_app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(
                "/explode",
                headers={"Authorization": "Bearer request-token"},
            )
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == SERVER_REQUEST_ID
    assert response.json() == {
        "code": "dependency_unavailable",
        "message": "依赖服务暂时不可用。",
    }
    assert current_request_id() is None
    rendered = metrics.render().decode()
    assert 'route="unmatched"' in rendered
    assert "explode" not in rendered
    logs = stream.getvalue()
    assert "request-token" not in logs
    assert "leaked-token" not in logs
    assert "password" not in logs


@pytest.mark.asyncio
async def test_sse_counts_only_events_after_last_event_id() -> None:
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("observability-test-signing-key-32-bytes"),
            issuer="opercerta-observability-test",
            audience="opercerta-api-test",
            ttl_seconds=300,
            demo_token_enabled=True,
        )
    )
    metrics = ApiMetrics.create()
    runtime = AppRuntime(
        runner=cast(OperationRunner, object()),
        operations=cast(ReplenishmentOperationRepository, AuditOperations()),
        authenticator=authenticator,
    )
    app = create_app(
        runtime,
        observability=ObservabilityConfig(
            metrics=metrics,
            metrics_enabled=True,
        ),
    )
    token = authenticator.issue_demo_token(
        DemoAccount.AUDITOR,
        datetime.now(UTC),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        events = await client.get(
            "/api/v1/operations/00000000-0000-4000-8000-000000000010/events",
            headers={
                "Authorization": f"Bearer {token}",
                "Last-Event-ID": "1",
            },
        )
        rendered = await client.get("/metrics")

    assert events.status_code == 200
    assert "id: 1" not in events.text
    assert "id: 2" in events.text
    assert (
        'opercerta_audit_events_replayed_total{event_type="approval_requested"} 1.0'
        in rendered.text
    )
    assert 'event_type="operation_received"' not in rendered.text
