import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AnyHttpUrl, Field, PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.requests import Request
from starlette.types import Lifespan

from opercerta.api.health import (
    ProductionReadinessProbe,
    ReadinessProbe,
    UnavailableReadinessProbe,
    not_ready_report,
)
from opercerta.api.models import (
    ApprovalRequest,
    ApprovalResponse,
    ErrorResponse,
    OperationAccepted,
    OperationDetailResponse,
)
from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.application.operation_runner import OperationRunner
from opercerta.domain.approvals import BoundApprovalCommand
from opercerta.domain.contracts import (
    ActionType,
    ObjectType,
    OperationRequest,
)
from opercerta.domain.errors import (
    ApprovalAlreadyDecided,
    ApprovalExpired,
    ApprovalSnapshotMismatch,
    DependencyUnavailable,
    OperationNotFound,
)
from opercerta.domain.model_gateway import MockModelGateway
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    OperationDetail,
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.workflow.replenishment_graph import build_replenishment_graph
from opercerta.workflow.replenishment_recovery import (
    ReplenishmentRecoveryCoordinator,
)

LOGGER = logging.getLogger(__name__)


class ApiRequestValidationFailed(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AppRuntime:
    runner: OperationRunner
    operations: ReplenishmentOperationRepository
    readiness: ReadinessProbe = field(default_factory=UnavailableReadinessProbe)


class ProductionSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    database_url: SecretStr = Field(
        validation_alias="OPERCERTA_DATABASE_URL",
    )
    mcp_url: AnyHttpUrl = Field(validation_alias="OPERCERTA_MCP_URL")
    mcp_timeout_seconds: PositiveFloat = Field(
        validation_alias="OPERCERTA_MCP_TIMEOUT_SECONDS",
    )
    approval_ttl_seconds: PositiveInt = Field(
        validation_alias="OPERCERTA_APPROVAL_TTL_SECONDS",
    )
    model_mode: Literal["mock"] = Field(
        validation_alias="OPERCERTA_MODEL_MODE",
    )


RuntimeProvider = Callable[[], AppRuntime]


def create_app(runtime: AppRuntime) -> FastAPI:
    return _build_app(lambda: runtime)


def create_production_app(
    settings: ProductionSettings | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    production_settings = settings or ProductionSettings()
    active_runtime: AppRuntime | None = None

    def runtime_provider() -> AppRuntime:
        if active_runtime is None:
            raise DependencyUnavailable
        return active_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal active_runtime
        del app
        async with _open_production_runtime(
            production_settings,
            clock,
        ) as runtime:
            active_runtime = runtime
            await runtime.runner.recover_all()
            try:
                yield
            finally:
                active_runtime = None

    return _build_app(runtime_provider, lifespan=lifespan)


@asynccontextmanager
async def _open_production_runtime(
    settings: ProductionSettings,
    clock: Callable[[], datetime],
) -> AsyncIterator[AppRuntime]:
    parsed_url = make_url(settings.database_url.get_secret_value())
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed_url.password is not None:
        os.environ["PGPASSWORD"] = parsed_url.password
    engine: AsyncEngine | None = None
    try:
        engine = create_async_engine(
            parsed_url.set(password=None),
            pool_pre_ping=True,
        )
        async with open_checkpointer(settings.database_url) as saver:
            operations = ReplenishmentOperationRepository(engine)
            graph = build_replenishment_graph(
                saver,
                operations,
                EvidenceRepository(engine),
                McpToolGateway(
                    str(settings.mcp_url),
                    timeout_seconds=float(settings.mcp_timeout_seconds),
                ),
                MockModelGateway(),
                clock,
                approval_ttl_seconds=int(settings.approval_ttl_seconds),
            )
            recovery = ReplenishmentRecoveryCoordinator(graph, operations)
            runner = OperationRunner(
                graph,
                ApprovalRepository(engine),
                operations,
                recovery,
                ApprovalExpiryService(operations, clock),
                clock,
            )
            yield AppRuntime(
                runner=runner,
                operations=operations,
                readiness=ProductionReadinessProbe(
                    engine=engine,
                    database_url=settings.database_url,
                    mcp_health_url=mcp_health_url(settings.mcp_url),
                    timeout_seconds=float(settings.mcp_timeout_seconds),
                ),
            )
    finally:
        if engine is not None:
            await engine.dispose()
        if original_pgpassword is None:
            os.environ.pop("PGPASSWORD", None)
        else:
            os.environ["PGPASSWORD"] = original_pgpassword


def _build_app(
    runtime_provider: RuntimeProvider,
    *,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="OperCerta API",
        version="0.1.0",
        description=(
            "OperCerta 本地演示 API。approver_id 等 actor 字段仅用于审计演示。"
            "不是可信身份、认证或 RBAC。"
        ),
        lifespan=lifespan,
    )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        try:
            report = await runtime_provider().readiness.check()
        except Exception:
            report = not_ready_report()
        return JSONResponse(
            status_code=(
                status.HTTP_200_OK
                if report.status == "ready"
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content=report.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "request_validation_failed",
            "请求内容无效。",
        )

    @app.exception_handler(ApiRequestValidationFailed)
    async def api_request_validation_handler(
        request: Request,
        error: ApiRequestValidationFailed,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "request_validation_failed",
            "请求内容无效。",
        )

    @app.exception_handler(OperationNotFound)
    async def operation_not_found_handler(
        request: Request,
        error: OperationNotFound,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_404_NOT_FOUND,
            OperationNotFound.code,
            "未找到指定操作。",
        )

    @app.exception_handler(ApprovalAlreadyDecided)
    async def approval_already_decided_handler(
        request: Request,
        error: ApprovalAlreadyDecided,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_409_CONFLICT,
            ApprovalAlreadyDecided.code,
            "该操作已经完成审批决定。",
        )

    @app.exception_handler(ApprovalExpired)
    async def approval_expired_handler(
        request: Request,
        error: ApprovalExpired,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_409_CONFLICT,
            ApprovalExpired.code,
            "审批已过期。",
        )

    @app.exception_handler(ApprovalSnapshotMismatch)
    async def approval_snapshot_mismatch_handler(
        request: Request,
        error: ApprovalSnapshotMismatch,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_409_CONFLICT,
            ApprovalSnapshotMismatch.code,
            "审批依据已变化。请刷新后重试。",
        )

    @app.exception_handler(DependencyUnavailable)
    async def dependency_unavailable_handler(
        request: Request,
        error: DependencyUnavailable,
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            DependencyUnavailable.code,
            "依赖服务暂时不可用。",
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        del request
        LOGGER.error(
            "unhandled API dependency failure",
            extra={"exception_type": type(error).__name__},
        )
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            DependencyUnavailable.code,
            "依赖服务暂时不可用。",
        )

    @app.post(
        "/api/v1/operations",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=OperationAccepted,
        responses={
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        },
    )
    async def create_operation(
        operation_request: OperationRequest,
    ) -> OperationAccepted:
        if (
            operation_request.requested_action is not ActionType.CREATE_WORK_ORDER
            or operation_request.object_type is not ObjectType.INVENTORY
            or operation_request.object_id is None
        ):
            raise ApiRequestValidationFailed
        runtime = runtime_provider()
        operation_id = await runtime.runner.start(operation_request)
        detail = await runtime.operations.load_detail(operation_id)
        return accepted_response(detail)

    @app.get(
        "/api/v1/operations/{operation_id}",
        response_model=OperationDetailResponse,
        responses={
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        },
    )
    async def get_operation(operation_id: UUID) -> OperationDetailResponse:
        runtime = runtime_provider()
        detail = await runtime.operations.load_detail(operation_id)
        return detail_response(detail)

    @app.post(
        "/api/v1/operations/{operation_id}/approval",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=OperationAccepted,
        responses={
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
            status.HTTP_409_CONFLICT: {"model": ErrorResponse},
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        },
    )
    async def submit_approval(
        operation_id: UUID,
        approval_request: ApprovalRequest,
    ) -> OperationAccepted:
        command = BoundApprovalCommand(
            operation_id=operation_id,
            approver_id=approval_request.approver_id,
            decision=approval_request.decision,
            reason=approval_request.reason,
            expected_binding=approval_request.approval_binding(),
        )
        runtime = runtime_provider()
        await runtime.runner.submit_approval(command)
        detail = await runtime.operations.load_detail(operation_id)
        return accepted_response(detail)

    return app


def mcp_health_url(mcp_url: AnyHttpUrl) -> str:
    parsed = urlsplit(str(mcp_url))
    return urlunsplit((parsed.scheme, parsed.netloc, "/health/ready", "", ""))


def accepted_response(detail: OperationDetail) -> OperationAccepted:
    if not detail.audit_events:
        raise DependencyUnavailable
    return OperationAccepted(
        operation_id=detail.operation_id,
        status=detail.status,
        created_at=detail.audit_events[0].created_at,
    )


def detail_response(detail: OperationDetail) -> OperationDetailResponse:
    approval = (
        ApprovalResponse(
            id=detail.approval.id,
            approver_id=detail.approval.approver_id,
            decision=detail.approval.decision,
            reason=detail.approval.reason,
            created_at=detail.approval.created_at,
        )
        if detail.approval is not None
        else None
    )
    return OperationDetailResponse(
        operation_id=detail.operation_id,
        status=detail.status,
        request=OperationRequest.model_validate(detail.snapshot.request),
        evidence=tuple(record.content for record in detail.evidence_records),
        assessment=detail.assessment,
        plan=detail.plan,
        approval_binding=detail.approval_binding,
        approval=approval,
        work_order=detail.work_order,
        result=detail.result,
        error=detail.error,
        last_audit_sequence=detail.last_audit_sequence,
    )


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(code=code, message=message)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )
