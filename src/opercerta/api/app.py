import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic_ns
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import (
    AnyHttpUrl,
    Field,
    PositiveFloat,
    PositiveInt,
    RedisDsn,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sse_starlette.sse import EventSourceResponse
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Lifespan, Message, Receive, Scope, Send

from opercerta.api.auth import (
    AuthenticatedActor,
    AuthenticationRequired,
    DemoTokenUnavailable,
    InvalidAccessToken,
    JwtAuthenticator,
    JwtSettings,
    PermissionDenied,
    Role,
)
from opercerta.api.health import (
    ProductionReadinessProbe,
    ReadinessProbe,
    UnavailableReadinessProbe,
    not_ready_report,
)
from opercerta.api.models import (
    ApprovalRequest,
    ApprovalResponse,
    DemoTokenRequest,
    DemoTokenResponse,
    ErrorResponse,
    OperationAccepted,
    OperationDetailResponse,
)
from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.application.operation_runner import OperationRunner
from opercerta.application.scenario_registry import build_default_scenario_registry
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
from opercerta.domain.model_gateway import MockModelGateway, ModelGateway
from opercerta.infrastructure.cache import (
    EvidenceCache,
    NullEvidenceCache,
    RedisEvidenceCache,
)
from opercerta.infrastructure.checkpoints import open_checkpointer
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.evidence_repository import EvidenceRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    OperationDetail,
)
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.infrastructure.model_gateway import OpenAICompatibleModelGateway
from opercerta.observability.context import new_request_id, request_context
from opercerta.observability.logging import log_event
from opercerta.observability.metrics import ApiMetrics
from opercerta.observability.tracing import (
    NOOP_TRACING,
    Tracing,
    configure_tracing,
    instrument_sqlalchemy_engine,
)
from opercerta.workflow.controlled_action_graph import build_controlled_action_graph
from opercerta.workflow.controlled_action_recovery import (
    ControlledActionRecoveryCoordinator,
)

LOGGER = logging.getLogger(__name__)


class ApiRequestValidationFailed(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AppRuntime:
    runner: OperationRunner
    operations: OperationRepository
    authenticator: JwtAuthenticator | None = None
    readiness: ReadinessProbe = field(default_factory=UnavailableReadinessProbe)


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    metrics: ApiMetrics = field(default_factory=ApiMetrics.create)
    metrics_enabled: bool = False
    request_id_factory: Callable[[], str] = new_request_id
    clock_ns: Callable[[], int] = monotonic_ns
    tracing: Tracing = NOOP_TRACING


class ObservabilityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: ApiMetrics,
        request_id_factory: Callable[[], str] = new_request_id,
        clock_ns: Callable[[], int] = monotonic_ns,
        tracing: Tracing = NOOP_TRACING,
    ) -> None:
        self._app = app
        self._metrics = metrics
        self._request_id_factory = request_id_factory
        self._clock_ns = clock_ns
        self._tracing = tracing

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = self._request_id_factory()
        started_at = self._clock_ns()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        with (
            request_context(request_id),
            self._tracing.span(
                "api.request",
                {
                    "component": "api",
                    "operation": str(scope.get("method", "OTHER")),
                    "request_id": request_id,
                },
            ),
        ):
            try:
                await self._app(scope, receive, send_with_request_id)
            except Exception:
                if response_started:
                    raise
                response = error_response(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    DependencyUnavailable.code,
                    "依赖服务暂时不可用。",
                )
                status_code = response.status_code
                log_event(
                    LOGGER,
                    logging.ERROR,
                    "api_unhandled_error",
                    status_code=status_code,
                    error_code=DependencyUnavailable.code,
                )
                await response(scope, receive, send_with_request_id)
            finally:
                route_object = scope.get("route")
                route = getattr(route_object, "path", None)
                duration_seconds = max(
                    (self._clock_ns() - started_at) / 1_000_000_000,
                    0.0,
                )
                self._metrics.observe_http(
                    str(scope.get("method", "OTHER")),
                    route if isinstance(route, str) else None,
                    status_code,
                    duration_seconds,
                )
                log_event(
                    LOGGER,
                    logging.INFO,
                    "http_request_completed",
                    route=route if isinstance(route, str) else "unmatched",
                    method=str(scope.get("method", "OTHER")),
                    status_code=status_code,
                    duration_ms=duration_seconds * 1000,
                )


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
    model_mode: Literal["mock", "real"] = Field(
        validation_alias="OPERCERTA_MODEL_MODE",
    )
    redis_url: RedisDsn | None = Field(default=None, validation_alias="OPERCERTA_REDIS_URL")
    cache_enabled: bool = Field(default=False, validation_alias="OPERCERTA_CACHE_ENABLED")
    cache_ttl_seconds: PositiveInt = Field(
        default=60, validation_alias="OPERCERTA_CACHE_TTL_SECONDS"
    )
    model_base_url: AnyHttpUrl | None = Field(
        default=None, validation_alias="OPERCERTA_MODEL_BASE_URL"
    )
    model_name: str | None = Field(default=None, validation_alias="OPERCERTA_MODEL_NAME")
    model_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPERCERTA_MODEL_API_KEY"
    )
    otlp_enabled: bool = Field(default=False, validation_alias="OPERCERTA_OTLP_ENABLED")
    otlp_endpoint: AnyHttpUrl | None = Field(
        default=None, validation_alias="OPERCERTA_OTLP_ENDPOINT"
    )
    jwt_signing_key: SecretStr = Field(validation_alias="OPERCERTA_JWT_SIGNING_KEY")
    jwt_issuer: str = Field(validation_alias="OPERCERTA_JWT_ISSUER")
    jwt_audience: str = Field(validation_alias="OPERCERTA_JWT_AUDIENCE")
    jwt_ttl_seconds: PositiveInt = Field(validation_alias="OPERCERTA_JWT_TTL_SECONDS")
    demo_token_enabled: bool = Field(validation_alias="OPERCERTA_DEMO_TOKEN_ENABLED")
    metrics_enabled: bool = Field(
        default=False,
        validation_alias="OPERCERTA_METRICS_ENABLED",
    )

    @model_validator(mode="after")
    def validate_optional_services(self) -> "ProductionSettings":
        if self.cache_enabled and self.redis_url is None:
            raise ValueError("Redis URL is required when cache is enabled")
        if self.model_mode == "real" and (
            self.model_base_url is None or self.model_name is None or self.model_api_key is None
        ):
            raise ValueError("real model settings are incomplete")
        if self.otlp_enabled and self.otlp_endpoint is None:
            raise ValueError("OTLP endpoint is required when tracing is enabled")
        return self


RuntimeProvider = Callable[[], AppRuntime]


def create_app(
    runtime: AppRuntime,
    *,
    observability: ObservabilityConfig | None = None,
) -> FastAPI:
    return _build_app(lambda: runtime, observability=observability)


def create_production_app(
    settings: ProductionSettings | None = None,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FastAPI:
    production_settings = settings or ProductionSettings()
    metrics = ApiMetrics.create()
    tracing, tracer_provider = configure_tracing(
        enabled=production_settings.otlp_enabled,
        endpoint=(
            str(production_settings.otlp_endpoint)
            if production_settings.otlp_endpoint is not None
            else None
        ),
        service_name="opercerta-api",
    )
    active_runtime: AppRuntime | None = None

    def runtime_provider() -> AppRuntime:
        if active_runtime is None:
            raise DependencyUnavailable
        return active_runtime

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal active_runtime
        del app
        try:
            async with _open_production_runtime(
                production_settings,
                clock,
                tracing,
                metrics,
            ) as runtime:
                active_runtime = runtime
                await runtime.runner.recover_all()
                yield
        finally:
            active_runtime = None
            if tracer_provider is not None:
                tracer_provider.shutdown()

    return _build_app(
        runtime_provider,
        lifespan=lifespan,
        observability=ObservabilityConfig(
            metrics=metrics,
            metrics_enabled=production_settings.metrics_enabled,
            tracing=tracing,
        ),
    )


@asynccontextmanager
async def _open_production_runtime(
    settings: ProductionSettings,
    clock: Callable[[], datetime],
    tracing: Tracing = NOOP_TRACING,
    metrics: ApiMetrics | None = None,
) -> AsyncIterator[AppRuntime]:
    parsed_url = make_url(settings.database_url.get_secret_value())
    original_pgpassword = os.environ.get("PGPASSWORD")
    if parsed_url.password is not None:
        os.environ["PGPASSWORD"] = parsed_url.password
    engine: AsyncEngine | None = None
    redis_client: Redis | None = None
    model_client: httpx.AsyncClient | None = None
    try:
        engine = create_async_engine(
            parsed_url.set(password=None),
            pool_pre_ping=True,
        )
        instrument_sqlalchemy_engine(engine.sync_engine, tracing)
        async with open_checkpointer(settings.database_url) as saver:
            operations = OperationRepository(engine)
            registry = build_default_scenario_registry()
            active_cache: EvidenceCache = NullEvidenceCache()
            if settings.cache_enabled and settings.redis_url is not None:
                redis_client = Redis.from_url(str(settings.redis_url))
                active_cache = RedisEvidenceCache(
                    redis_client,
                    (metrics or ApiMetrics.create()).count_cache_event,
                )
            if settings.model_mode == "real":
                if (
                    settings.model_base_url is None
                    or settings.model_name is None
                    or settings.model_api_key is None
                ):
                    raise ValueError("real model settings are incomplete")
                model_client = httpx.AsyncClient()
                model_gateway: ModelGateway = OpenAICompatibleModelGateway(
                    client=model_client,
                    base_url=str(settings.model_base_url),
                    model=settings.model_name,
                    api_key=settings.model_api_key,
                    timeout_seconds=float(settings.mcp_timeout_seconds),
                )
            else:
                model_gateway = MockModelGateway()
            graph = build_controlled_action_graph(
                saver,
                operations,
                EvidenceRepository(engine),
                McpToolGateway(
                    str(settings.mcp_url),
                    timeout_seconds=float(settings.mcp_timeout_seconds),
                ),
                model_gateway,
                clock,
                registry,
                cache=active_cache,
                cache_ttl_seconds=int(settings.cache_ttl_seconds),
                tracing=tracing,
                approval_ttl_seconds=int(settings.approval_ttl_seconds),
            )
            recovery = ControlledActionRecoveryCoordinator(graph, operations)
            runner = OperationRunner(
                graph,
                ApprovalRepository(engine),
                operations,
                recovery,
                ApprovalExpiryService(operations, clock),
                clock,
                registry,
            )
            yield AppRuntime(
                runner=runner,
                operations=operations,
                authenticator=JwtAuthenticator(
                    JwtSettings(
                        signing_key=settings.jwt_signing_key,
                        issuer=settings.jwt_issuer,
                        audience=settings.jwt_audience,
                        ttl_seconds=settings.jwt_ttl_seconds,
                        demo_token_enabled=settings.demo_token_enabled,
                    )
                ),
                readiness=ProductionReadinessProbe(
                    engine=engine,
                    database_url=settings.database_url,
                    mcp_health_url=mcp_health_url(settings.mcp_url),
                    timeout_seconds=float(settings.mcp_timeout_seconds),
                ),
            )
    finally:
        if model_client is not None:
            await model_client.aclose()
        if redis_client is not None:
            await redis_client.aclose()
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
    observability: ObservabilityConfig | None = None,
) -> FastAPI:
    active_observability = observability or ObservabilityConfig()
    app = FastAPI(
        title="OperCerta API",
        version="0.1.0",
        description=(
            "OperCerta 本地演示 API。approver_id 等 actor 字段仅用于审计演示。"
            "不是可信身份、认证或 RBAC。"
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        ObservabilityMiddleware,
        metrics=active_observability.metrics,
        request_id_factory=active_observability.request_id_factory,
        clock_ns=active_observability.clock_ns,
        tracing=active_observability.tracing,
    )

    if active_observability.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint() -> Response:
            return Response(
                content=active_observability.metrics.render(),
                headers={"Content-Type": CONTENT_TYPE_LATEST},
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

    @app.exception_handler(AuthenticationRequired)
    async def authentication_required_handler(
        request: Request, error: AuthenticationRequired
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_401_UNAUTHORIZED, AuthenticationRequired.code, "认证信息缺失"
        )

    @app.exception_handler(InvalidAccessToken)
    async def invalid_access_token_handler(
        request: Request, error: InvalidAccessToken
    ) -> JSONResponse:
        del request, error
        return error_response(status.HTTP_401_UNAUTHORIZED, InvalidAccessToken.code, "访问令牌无效")

    @app.exception_handler(PermissionDenied)
    async def permission_denied_handler(request: Request, error: PermissionDenied) -> JSONResponse:
        del request, error
        return error_response(status.HTTP_403_FORBIDDEN, PermissionDenied.code, "无权执行此操作")

    @app.exception_handler(DemoTokenUnavailable)
    async def demo_token_unavailable_handler(
        request: Request, error: DemoTokenUnavailable
    ) -> JSONResponse:
        del request, error
        return error_response(
            status.HTTP_403_FORBIDDEN, DemoTokenUnavailable.code, "演示令牌入口不可用"
        )

    def require_roles(*roles: Role) -> Callable[..., Awaitable[AuthenticatedActor]]:
        async def dependency(
            authorization: Annotated[str | None, Header()] = None,
        ) -> AuthenticatedActor:
            authenticator = runtime_provider().authenticator
            if authenticator is None:
                raise DependencyUnavailable
            actor = authenticator.authenticate(authorization)
            if actor.role not in roles:
                raise PermissionDenied
            return actor

        return dependency

    @app.post("/api/v1/auth/demo-token", response_model=DemoTokenResponse)
    async def issue_demo_token(request: DemoTokenRequest) -> DemoTokenResponse:
        authenticator = runtime_provider().authenticator
        if authenticator is None:
            raise DependencyUnavailable
        return DemoTokenResponse(
            access_token=authenticator.issue_demo_token(request.account, datetime.now(UTC)),
            expires_in=authenticator.ttl_seconds,
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
        actor: Annotated[AuthenticatedActor, Depends(require_roles(Role.OPERATOR))],
    ) -> OperationAccepted:
        del actor
        if (
            operation_request.requested_action
            not in {ActionType.QUERY, ActionType.CREATE_WORK_ORDER}
            or operation_request.object_type
            not in {ObjectType.INVENTORY, ObjectType.EQUIPMENT, ObjectType.TASK}
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
    async def get_operation(
        operation_id: UUID,
        actor: Annotated[
            AuthenticatedActor,
            Depends(require_roles(Role.OPERATOR, Role.APPROVER, Role.AUDITOR, Role.DEMO_ADMIN)),
        ],
    ) -> OperationDetailResponse:
        del actor
        runtime = runtime_provider()
        detail = await runtime.operations.load_detail(operation_id)
        return detail_response(detail)

    @app.get(
        "/api/v1/operations/{operation_id}/events",
        responses={
            status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
            status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        },
    )
    async def replay_audit_events(
        operation_id: UUID,
        actor: Annotated[
            AuthenticatedActor,
            Depends(require_roles(Role.OPERATOR, Role.APPROVER, Role.AUDITOR, Role.DEMO_ADMIN)),
        ],
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> EventSourceResponse:
        del actor
        after_sequence = parse_last_event_id(last_event_id)
        detail = await runtime_provider().operations.load_detail(operation_id)

        async def event_stream() -> AsyncIterator[dict[str, str]]:
            for audit_event in detail.audit_events:
                if audit_event.sequence > after_sequence:
                    active_observability.metrics.count_audit_event(audit_event.event_type)
                    yield {
                        "id": str(audit_event.sequence),
                        "event": audit_event.event_type,
                        "data": json.dumps(dict(audit_event.payload), ensure_ascii=False),
                    }

        return EventSourceResponse(event_stream())

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
        actor: Annotated[AuthenticatedActor, Depends(require_roles(Role.APPROVER))],
    ) -> OperationAccepted:
        command = BoundApprovalCommand(
            operation_id=operation_id,
            approver_id=actor.subject,
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


def parse_last_event_id(last_event_id: str | None) -> int:
    if last_event_id is None:
        return 0
    if not last_event_id.isdecimal() or int(last_event_id) < 1:
        raise ApiRequestValidationFailed
    return int(last_event_id)


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
