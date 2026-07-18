# OperCerta Observability and Security Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已验证的库存补货 API 增加服务端请求关联、安全 JSON 日志、低基数 Prometheus 指标和可重复安全回归，不改变领域、数据库、恢复、审批或幂等语义。

**Architecture:** 新建三个单一职责模块：`context.py` 管理 `ContextVar`，`logging.py` 只输出白名单 JSON 字段，`metrics.py` 持有应用级 `CollectorRegistry`。FastAPI 使用纯 ASGI middleware 覆盖完整响应生命周期，服务端生成 `request_id`、注入响应头、记录请求结果并更新指标；SSE 生成器只对实际回放事件计数。

**Tech Stack:** Python 3.12、FastAPI `0.139.2`、Python `logging`/`contextvars`、`prometheus-client==0.25.0`、HTTPX ASGITransport、Pytest、Ruff、mypy、uv。

## Global Constraints

- 只实施 OperCerta；不启动 ForenTrail 或其他项目。
- `prometheus-client==0.25.0` 保持不变；FastAPI 补丁升级必须独立验证，失败则恢复 `0.139.0`。
- 所有生产行为改动都遵循 RED → GREEN；依赖锁文件属于配置改动，以升级前版本断言失败和升级后完整回归为门禁。
- `request_id` 只能由服务端生成 UUIDv4；不得信任或回显客户端 `X-Request-ID`。
- 日志不得记录 Authorization、JWT、Cookie、密码、连接 URL、请求/响应正文、审批 reason、模型内容、traceback 正文或环境变量集合。
- 指标 label 禁止使用 `request_id`、`operation_id`、主体、SKU、原始路径、异常消息或任意用户输入。
- `/metrics` 默认关闭；本计划不增加 Prometheus/Grafana 容器，不配置 Caddy，不公开部署。
- 不增加 Redis readiness，不生成虚假的 `trace_id`、`thread_id` 或 `tool_call_id`。
- 发布门禁始终保持 `CLOSED`；任何测试数字只能记录实际命令输出。

---

### Task 1: FastAPI 补丁版本独立升级

**Files:**
- Modify: `pyproject.toml:9-27`
- Modify: `uv.lock`

**Interfaces:**
- Consumes: 当前锁定的 `fastapi==0.139.0` 与既有 325 条后端回归。
- Produces: 锁定并安装的 `fastapi==0.139.2`；后续任务不得再次改依赖版本。

- [ ] **Step 1: 运行版本 RED，证明当前环境尚未满足已核验版本**

Run:

```powershell
uv run python -c "from importlib.metadata import version; actual=version('fastapi'); assert actual == '0.139.2', actual"
```

Expected: 退出码 1，断言显示当前版本为 `0.139.0`。

- [ ] **Step 2: 只修改 FastAPI 直接依赖版本**

将 `pyproject.toml` 中：

```toml
"fastapi==0.139.0",
```

改为：

```toml
"fastapi==0.139.2",
```

- [ ] **Step 3: 只升级 FastAPI 相关锁定并同步环境**

Run:

```powershell
uv lock --upgrade-package fastapi
```

Expected: 退出码 0；`uv.lock` 中 FastAPI 为 `0.139.2`。

Run:

```powershell
uv sync --frozen --all-groups
```

Expected: 退出码 0，不修改 `pyproject.toml`。

- [ ] **Step 4: 运行版本 GREEN 与完整后端兼容性门禁**

Run:

```powershell
uv run python -c "from importlib.metadata import version; assert version('fastapi') == '0.139.2'"
```

Expected: 退出码 0。

Run:

```powershell
uv run pytest -q
```

Expected: 退出码 0，零失败；记录实际通过数，不沿用旧数字。

- [ ] **Step 5: 提交独立依赖升级**

```powershell
git add pyproject.toml uv.lock
git commit -m "chore: update fastapi patch release"
```

---

### Task 2: 请求上下文隔离

**Files:**
- Create: `src/opercerta/observability/__init__.py`
- Create: `src/opercerta/observability/context.py`
- Create: `tests/unit/observability/__init__.py`
- Create: `tests/unit/observability/test_context.py`

**Interfaces:**
- Consumes: Python `ContextVar` 与 `uuid4()`。
- Produces: `new_request_id() -> str`、`request_context(request_id: str)` 上下文管理器、`current_request_id() -> str | None`。

- [ ] **Step 1: 写并发隔离与恢复 RED 测试**

```python
# tests/unit/observability/test_context.py
import asyncio
from uuid import UUID

import pytest

from opercerta.observability.context import (
    current_request_id,
    new_request_id,
    request_context,
)


def test_new_request_id_is_uuid4() -> None:
    request_id = new_request_id()
    parsed = UUID(request_id)
    assert parsed.version == 4
    assert str(parsed) == request_id


@pytest.mark.asyncio
async def test_request_context_is_isolated_and_restored() -> None:
    async def observe(request_id: str) -> str | None:
        with request_context(request_id):
            await asyncio.sleep(0)
            return current_request_id()

    observed = await asyncio.gather(observe("request-a"), observe("request-b"))

    assert observed == ["request-a", "request-b"]
    assert current_request_id() is None
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/observability/test_context.py -q
```

Expected: 收集失败，提示 `opercerta.observability` 不存在。

- [ ] **Step 3: 实现最小 ContextVar 边界**

```python
# src/opercerta/observability/context.py
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

_REQUEST_ID: ContextVar[str | None] = ContextVar("opercerta_request_id", default=None)


def new_request_id() -> str:
    return str(uuid4())


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


@contextmanager
def request_context(request_id: str) -> Iterator[None]:
    token = _REQUEST_ID.set(request_id)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)
```

两个 `__init__.py` 保持空文件，不重导出内部变量。

- [ ] **Step 4: 运行 GREEN 与静态检查**

Run:

```powershell
uv run pytest tests/unit/observability/test_context.py -q
```

Expected: `2 passed`。

Run:

```powershell
uv run ruff check src/opercerta/observability tests/unit/observability
```

Expected: `All checks passed!`。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0。

- [ ] **Step 5: 提交请求上下文**

```powershell
git add src/opercerta/observability tests/unit/observability
git commit -m "feat: isolate api request context"
```

---

### Task 3: 安全 JSON 日志与 API 运行入口

**Files:**
- Create: `src/opercerta/observability/logging.py`
- Create: `tests/unit/observability/test_logging.py`
- Modify: `src/opercerta/runtime/api.py`
- Modify: `tests/unit/runtime/test_entrypoints.py`

**Interfaces:**
- Consumes: Task 2 的 `current_request_id()`。
- Produces: `SafeJsonFormatter(service: str)`、`log_event(...)`、`configure_json_logging(service: str) -> None`；API 入口在 Uvicorn 启动前配置安全日志。

- [ ] **Step 1: 写日志白名单 RED 测试**

```python
# tests/unit/observability/test_logging.py
import json
import logging

from opercerta.observability.context import request_context
from opercerta.observability.logging import SafeJsonFormatter


def test_formatter_emits_only_safe_allowlisted_fields() -> None:
    record = logging.makeLogRecord(
        {
            "name": "opercerta.api.app",
            "levelno": logging.ERROR,
            "levelname": "ERROR",
            "msg": "Bearer secret-token password=secret",
            "created": 1_784_323_200.0,
            "event": "api_request_failed",
            "route": "/api/v1/operations/{operation_id}",
            "method": "GET",
            "status_code": 503,
            "error_code": "dependency_unavailable",
            "authorization": "Bearer secret-token",
            "exception_type": "RuntimeError",
        }
    )

    with request_context("server-request-id"):
        payload = json.loads(SafeJsonFormatter("opercerta-api").format(record))

    assert payload["service"] == "opercerta-api"
    assert payload["event"] == "api_request_failed"
    assert payload["request_id"] == "server-request-id"
    assert payload["error_code"] == "dependency_unavailable"
    assert set(payload) == {
        "timestamp", "level", "service", "event", "request_id",
        "route", "method", "status_code", "error_code",
    }
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "password" not in serialized
    assert "RuntimeError" not in serialized
```

在 `tests/unit/runtime/test_entrypoints.py` 把 API 入口测试改为同时断言：

```python
def test_api_main_configures_logging_and_binds_all_container_interfaces(monkeypatch) -> None:
    events: list[tuple[object, ...]] = []
    application = object()
    monkeypatch.setenv("PORT", "9010")
    monkeypatch.setattr(api, "create_production_app", lambda: application)
    monkeypatch.setattr(
        api,
        "configure_json_logging",
        lambda service: events.append(("logging", service)),
    )
    monkeypatch.setattr(
        api.uvicorn,
        "run",
        lambda app, host, port, log_config: events.append(
            ("uvicorn", app, host, port, log_config)
        ),
    )

    api.main()

    assert events == [
        ("logging", "opercerta-api"),
        ("uvicorn", application, "0.0.0.0", 9010, None),
    ]
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/observability/test_logging.py tests/unit/runtime/test_entrypoints.py -q
```

Expected: 收集失败或入口断言失败，因为安全 formatter 与入口配置尚不存在。

- [ ] **Step 3: 实现日志 formatter、事件函数和配置函数**

```python
# src/opercerta/observability/logging.py
import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from opercerta.observability.context import current_request_id

_OPTIONAL_FIELDS = (
    "operation_id",
    "route",
    "method",
    "status_code",
    "duration_ms",
    "error_code",
)


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str | int | float | None] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "event": str(getattr(record, "event", "application_log")),
            "request_id": current_request_id(),
        }
        for field_name in _OPTIONAL_FIELDS:
            value = getattr(record, field_name, None)
            if isinstance(value, str | int | float):
                payload[field_name] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    operation_id: str | None = None,
    route: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    duration_ms: float | None = None,
    error_code: str | None = None,
) -> None:
    values = {
        "event": event,
        "operation_id": operation_id,
        "route": route,
        "method": method,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "error_code": error_code,
    }
    logger.log(level, event, extra={key: value for key, value in values.items() if value is not None})


def configure_json_logging(service: str, stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(SafeJsonFormatter(service))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
```

在 `src/opercerta/runtime/api.py` 中导入配置函数，并把 `main()` 改为：

```python
def main() -> None:
    configure_json_logging("opercerta-api")
    uvicorn.run(
        create_production_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        log_config=None,
    )
```

- [ ] **Step 4: 运行 GREEN 与回归**

Run:

```powershell
uv run pytest tests/unit/observability/test_logging.py tests/unit/runtime/test_entrypoints.py -q
```

Expected: 全部通过。

Run:

```powershell
uv run ruff check src/opercerta/observability src/opercerta/runtime/api.py tests/unit
```

Expected: `All checks passed!`。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0。

- [ ] **Step 5: 提交安全日志**

```powershell
git add src/opercerta/observability/logging.py src/opercerta/runtime/api.py tests/unit/observability/test_logging.py tests/unit/runtime/test_entrypoints.py
git commit -m "feat: emit allowlisted json logs"
```

---

### Task 4: 应用级低基数 Prometheus registry

**Files:**
- Create: `src/opercerta/observability/metrics.py`
- Create: `tests/unit/observability/test_metrics.py`

**Interfaces:**
- Consumes: `prometheus-client==0.25.0`。
- Produces: `ApiMetrics.create()`、`observe_http(...)`、`count_audit_event(event_type)`、`render() -> bytes`、`normalize_route()` 与固定白名单。

- [ ] **Step 1: 写 registry 隔离和标签安全 RED 测试**

```python
# tests/unit/observability/test_metrics.py
from opercerta.observability.metrics import ApiMetrics


def test_metrics_use_isolated_registry_and_low_cardinality_labels() -> None:
    secret_operation_id = "2b971f65-1844-4f58-acbc-acdeef012345"
    metrics_a = ApiMetrics.create()
    metrics_b = ApiMetrics.create()

    metrics_a.observe_http(
        "GET",
        f"/api/v1/operations/{secret_operation_id}",
        404,
        0.125,
    )
    metrics_a.count_audit_event("unknown-user-controlled-event")

    rendered_a = metrics_a.render().decode()
    rendered_b = metrics_b.render().decode()
    assert 'route="unmatched"' in rendered_a
    assert 'event_type="other"' in rendered_a
    assert secret_operation_id not in rendered_a
    assert "unknown-user-controlled-event" not in rendered_a
    assert 'route="unmatched"' not in rendered_b
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/observability/test_metrics.py -q
```

Expected: 收集失败，提示 `opercerta.observability.metrics` 不存在。

- [ ] **Step 3: 实现指标对象与归一化白名单**

```python
# src/opercerta/observability/metrics.py
from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

KNOWN_ROUTES = frozenset(
    {
        "/health/live",
        "/health/ready",
        "/metrics",
        "/api/v1/auth/demo-token",
        "/api/v1/operations",
        "/api/v1/operations/{operation_id}",
        "/api/v1/operations/{operation_id}/events",
        "/api/v1/operations/{operation_id}/approval",
    }
)
KNOWN_AUDIT_EVENTS = frozenset(
    {
        "operation_received",
        "evidence_gathering_started",
        "evidence_recorded",
        "plan_validated",
        "reporting_started",
        "approval_requested",
        "approval_recorded",
        "approval_expired",
        "execution_started",
        "work_order_created",
        "verification_started",
        "operation_completed",
        "operation_rejected",
        "operation_failed",
    }
)


def normalize_route(route: str | None) -> str:
    return route if route in KNOWN_ROUTES else "unmatched"


def normalize_method(method: str) -> str:
    normalized = method.upper()
    return normalized if normalized in {"GET", "POST"} else "OTHER"


def normalize_status_code(status_code: int) -> str:
    return str(status_code) if 100 <= status_code <= 599 else "other"


def normalize_audit_event(event_type: str) -> str:
    return event_type if event_type in KNOWN_AUDIT_EVENTS else "other"


@dataclass(frozen=True, slots=True)
class ApiMetrics:
    registry: CollectorRegistry
    http_requests: Counter
    http_duration: Histogram
    audit_events: Counter

    @classmethod
    def create(cls) -> "ApiMetrics":
        registry = CollectorRegistry()
        return cls(
            registry=registry,
            http_requests=Counter(
                "opercerta_http_requests_total",
                "Completed OperCerta HTTP requests.",
                ("method", "route", "status_code"),
                registry=registry,
            ),
            http_duration=Histogram(
                "opercerta_http_request_duration_seconds",
                "OperCerta HTTP request duration through response completion.",
                ("method", "route"),
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
                registry=registry,
            ),
            audit_events=Counter(
                "opercerta_audit_events_replayed_total",
                "Persisted audit events replayed through SSE.",
                ("event_type",),
                registry=registry,
            ),
        )

    def observe_http(
        self,
        method: str,
        route: str | None,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        method_label = normalize_method(method)
        route_label = normalize_route(route)
        self.http_requests.labels(
            method=method_label,
            route=route_label,
            status_code=normalize_status_code(status_code),
        ).inc()
        self.http_duration.labels(method=method_label, route=route_label).observe(
            max(duration_seconds, 0.0)
        )

    def count_audit_event(self, event_type: str) -> None:
        self.audit_events.labels(event_type=normalize_audit_event(event_type)).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
```

- [ ] **Step 4: 运行 GREEN、lint 与类型检查**

Run:

```powershell
uv run pytest tests/unit/observability/test_metrics.py -q
```

Expected: `1 passed`。

Run:

```powershell
uv run ruff check src/opercerta/observability tests/unit/observability
```

Expected: `All checks passed!`。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0。

- [ ] **Step 5: 提交指标 registry**

```powershell
git add src/opercerta/observability/metrics.py tests/unit/observability/test_metrics.py
git commit -m "feat: collect low-cardinality api metrics"
```

---

### Task 5: HTTP 请求关联、异常与可选 metrics 端点

**Files:**
- Modify: `src/opercerta/api/app.py:1-520`
- Create: `tests/integration/api/test_observability_api.py`
- Modify: `.env.example`
- Modify: `.env.compose.example`

**Interfaces:**
- Consumes: Task 2 的请求上下文、Task 3 的 `log_event()`、Task 4 的 `ApiMetrics`。
- Produces: `ObservabilityConfig`、`ObservabilityMiddleware`；`create_app(..., observability=...)`；`ProductionSettings.metrics_enabled`；默认关闭、显式启用的 `/metrics`。

- [ ] **Step 1: 写恶意请求头、默认关闭和异常安全 RED 集成测试**

```python
# tests/integration/api/test_observability_api.py
import io
import logging
from dataclasses import dataclass
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from opercerta.api.app import (
    AppRuntime,
    ObservabilityConfig,
    ObservabilityMiddleware,
    create_app,
)
from opercerta.application.operation_runner import OperationRunner
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.observability.logging import SafeJsonFormatter
from opercerta.observability.metrics import ApiMetrics

SERVER_REQUEST_ID = "00000000-0000-4000-8000-000000000001"


def empty_runtime() -> AppRuntime:
    return AppRuntime(
        runner=cast(OperationRunner, object()),
        operations=cast(ReplenishmentOperationRepository, object()),
    )


@pytest.mark.asyncio
async def test_server_request_id_ignores_untrusted_header_and_metrics_default_off() -> None:
    app = create_app(
        empty_runtime(),
        observability=ObservabilityConfig(request_id_factory=lambda: SERVER_REQUEST_ID),
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        live = await client.get("/health/live", headers={"X-Request-ID": "attacker-value"})
        metrics = await client.get("/metrics")

    assert live.status_code == 200
    assert live.headers["X-Request-ID"] == SERVER_REQUEST_ID
    assert "attacker-value" not in live.headers.values()
    assert metrics.status_code == 404
    assert "opercerta_http_requests" not in metrics.text


@pytest.mark.asyncio
async def test_unhandled_error_has_safe_503_request_id_metric_and_log() -> None:
    metrics = ApiMetrics.create()
    async def unsafe_app(scope, receive, send) -> None:
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
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
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
    rendered = metrics.render().decode()
    assert 'route="unmatched"' in rendered
    assert "explode" not in rendered
    logs = stream.getvalue()
    assert "request-token" not in logs
    assert "leaked-token" not in logs
    assert "password" not in logs
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/integration/api/test_observability_api.py -q
```

Expected: 收集失败，因为 `ObservabilityConfig` 和 `ObservabilityMiddleware` 尚不存在。

- [ ] **Step 3: 实现纯 ASGI middleware 与配置对象**

在 `src/opercerta/api/app.py` 增加以下接口和所需导入：

```python
from time import monotonic_ns

from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from opercerta.observability.context import new_request_id, request_context
from opercerta.observability.logging import log_event
from opercerta.observability.metrics import ApiMetrics


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    metrics: ApiMetrics = field(default_factory=ApiMetrics.create)
    metrics_enabled: bool = False
    request_id_factory: Callable[[], str] = new_request_id
    clock_ns: Callable[[], int] = monotonic_ns


class ObservabilityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        metrics: ApiMetrics,
        request_id_factory: Callable[[], str] = new_request_id,
        clock_ns: Callable[[], int] = monotonic_ns,
    ) -> None:
        self._app = app
        self._metrics = metrics
        self._request_id_factory = request_id_factory
        self._clock_ns = clock_ns

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

        with request_context(request_id):
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
                duration_seconds = max((self._clock_ns() - started_at) / 1_000_000_000, 0.0)
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
```

修改应用 factory 签名并统一传递配置：

```python
def create_app(
    runtime: AppRuntime,
    *,
    observability: ObservabilityConfig | None = None,
) -> FastAPI:
    return _build_app(lambda: runtime, observability=observability)
```

`_build_app()` 创建 `active_observability = observability or ObservabilityConfig()`，随后：

```python
app.add_middleware(
    ObservabilityMiddleware,
    metrics=active_observability.metrics,
    request_id_factory=active_observability.request_id_factory,
    clock_ns=active_observability.clock_ns,
)

if active_observability.metrics_enabled:
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(
            content=active_observability.metrics.render(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
```

- [ ] **Step 4: 把 metrics 开关接入 ProductionSettings 和环境样例**

在 `ProductionSettings` 增加默认关闭字段：

```python
metrics_enabled: bool = Field(
    default=False,
    validation_alias="OPERCERTA_METRICS_ENABLED",
)
```

`create_production_app()` 调用 `_build_app()` 时传入：

```python
observability=ObservabilityConfig(metrics_enabled=production_settings.metrics_enabled)
```

在 `.env.example` 与 `.env.compose.example` 各增加：

```dotenv
OPERCERTA_METRICS_ENABLED=false
```

- [ ] **Step 5: 运行 GREEN、现有 API 回归和静态检查**

Run:

```powershell
uv run pytest tests/integration/api/test_observability_api.py tests/integration/api/test_health_api.py tests/integration/api/test_operations_api.py -q
```

Expected: 全部通过；现有状态码、错误 envelope、健康与 RBAC 测试不回退。

Run:

```powershell
uv run ruff check src/opercerta/api src/opercerta/observability tests/integration/api
```

Expected: `All checks passed!`。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0。

- [ ] **Step 6: 提交 HTTP 可观测边界**

```powershell
git add src/opercerta/api/app.py tests/integration/api/test_observability_api.py .env.example .env.compose.example
git commit -m "feat: correlate and observe api requests"
```

---

### Task 6: SSE 实际回放计数与标签白名单回归

**Files:**
- Modify: `src/opercerta/api/app.py:453-481`
- Modify: `tests/integration/api/test_observability_api.py`

**Interfaces:**
- Consumes: Task 4 的 `ApiMetrics.count_audit_event()` 与 Task 5 的应用配置。
- Produces: 每个实际 yield 的持久化审计事件恰好增加一次 `opercerta_audit_events_replayed_total`；`Last-Event-ID` 跳过的事件不计数。

- [ ] **Step 1: 写 SSE 计数 RED 测试**

在 `tests/integration/api/test_observability_api.py` 增加：

```python
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from opercerta.api.auth import DemoAccount, JwtAuthenticator, JwtSettings
from pydantic import SecretStr


@dataclass
class AuditOperations:
    async def load_detail(self, operation_id: UUID) -> SimpleNamespace:
        del operation_id
        return SimpleNamespace(
            audit_events=(
                SimpleNamespace(sequence=1, event_type="operation_received", payload={}),
                SimpleNamespace(sequence=2, event_type="approval_requested", payload={}),
            )
        )


@pytest.mark.asyncio
async def test_sse_counts_only_events_after_last_event_id() -> None:
    authenticator = JwtAuthenticator(
        JwtSettings(
            signing_key=SecretStr("observability-test-key"),
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
        observability=ObservabilityConfig(metrics=metrics, metrics_enabled=True),
    )
    token = authenticator.issue_demo_token(DemoAccount.AUDITOR, datetime.now(UTC))
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
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/integration/api/test_observability_api.py::test_sse_counts_only_events_after_last_event_id -q
```

Expected: 失败，因为 SSE 生成器尚未调用 `count_audit_event()`。

- [ ] **Step 3: 在实际 yield 前增加一次白名单计数**

把 SSE 生成器修改为：

```python
async def event_stream() -> AsyncIterator[dict[str, str]]:
    for audit_event in detail.audit_events:
        if audit_event.sequence > after_sequence:
            active_observability.metrics.count_audit_event(audit_event.event_type)
            yield {
                "id": str(audit_event.sequence),
                "event": audit_event.event_type,
                "data": json.dumps(dict(audit_event.payload), ensure_ascii=False),
            }
```

不得在加载数据库快照时批量计数；只有向客户端实际 yield 的事件才计数。

- [ ] **Step 4: 运行 GREEN 与 SSE/API 回归**

Run:

```powershell
uv run pytest tests/integration/api/test_observability_api.py tests/integration/api/test_operations_api.py -q
```

Expected: 全部通过，包括既有 `Last-Event-ID`、认证、快照内容和错误测试。

Run:

```powershell
uv run ruff check src/opercerta/api/app.py tests/integration/api/test_observability_api.py
```

Expected: `All checks passed!`。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0。

- [ ] **Step 5: 提交 SSE 指标**

```powershell
git add src/opercerta/api/app.py tests/integration/api/test_observability_api.py
git commit -m "feat: count replayed audit events"
```

---

### Task 7: 完整门禁、证据与交接同步

**Files:**
- Create: `docs/release-evidence/observability-security-regression.md`
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-18.md`
- Modify: `docs/superpowers/plans/2026-07-18-observability-security-regression.md`

**Interfaces:**
- Consumes: Tasks 1–6 的提交和新鲜命令输出。
- Produces: 可复查的本地验证证据、真实限制与下一发布门禁边界；不打开 release gate。

- [ ] **Step 1: 运行完整后端测试**

Run:

```powershell
uv run pytest -q
```

Expected: 退出码 0、零失败。把命令输出中的实际通过数和耗时原样记录到证据；不得预填或沿用 325。

- [ ] **Step 2: 运行全部静态门禁**

Run:

```powershell
uv run ruff check .
```

Expected: `All checks passed!`。

Run:

```powershell
uv run ruff format --check .
```

Expected: 退出码 0，记录实际文件数。

Run:

```powershell
uv run mypy src
```

Expected: 退出码 0，记录实际源文件数。

- [ ] **Step 3: 运行前端防回退门禁**

Run:

```powershell
npm run test:run
```

Working directory: `web/`。

Expected: 退出码 0；记录实际测试文件数与测试数。

Run:

```powershell
npm run build
```

Working directory: `web/`。

Expected: TypeScript 与 Vite 构建退出码 0。

- [ ] **Step 4: 生成只包含实际事实的中文证据**

`docs/release-evidence/observability-security-regression.md` 必须按以下固定章节写入：

```markdown
# 可观测性与安全回归：本地验证证据

## 范围
说明服务端 request_id、安全 JSON 日志、低基数指标、SSE 回放计数与默认关闭的 /metrics。

## RED/GREEN 证据
逐项记录版本升级、ContextVar、日志、指标、HTTP middleware 与 SSE 测试实际观察到的失败原因和通过命令。

## 完整门禁
只抄录 Step 1–3 本轮实际 stdout 中的通过数、耗时和文件数。

## 安全断言
记录客户端 X-Request-ID 不受信、敏感字段不进日志、用户输入不进 label、异常上下文已清理。

## 已知限制
明确未实现 OpenTelemetry、Grafana、Redis 业务依赖、生产 IAM、CI/CD、Caddy、HTTPS 与公开部署，release gate 为 CLOSED。
```

不得写性能提升、成功率、SLA、生产可用或已经上线。

- [ ] **Step 5: 同步索引、当前状态、README、交接和当日日志**

每个文档只写以下已验证口径：

- 本地可观测性与安全回归基础已通过；
- `/metrics` 默认关闭，只有显式内部配置才启用；
- 不使用高基数 label，不记录凭据或正文；
- 发布门禁仍为 `CLOSED`；
- 下一步为 CI 安全门禁或 Caddy/HTTPS 设计，必须另行确认外部平台与发布权限。

同时把本计划已完成步骤改为 `- [x]`，不得删除原 RED/GREEN 命令。

- [ ] **Step 6: 检查敏感内容、占位和差异质量**

Run:

```powershell
rg -n "T[B]D|T[O]DO|稍后填[写]|待[定]" README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs/release-evidence/observability-security-regression.md docs/development-log/current-state.md src
```

Expected: 退出码 1，表示新交接与运行代码没有未完成占位。

Run:

```powershell
rg -n "Bearer [A-Za-z0-9._-]+|postgresql[^ ]*://[^ ]+:[^ ]+@" README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs/release-evidence/observability-security-regression.md docs/development-log/current-state.md src
```

Expected: 退出码 1，表示运行代码和发布证据没有令牌或带密码连接串。合成攻击样本只保存在测试文件，不纳入凭据扫描结论。

Run:

```powershell
git diff --check
```

Expected: 退出码 0。

- [ ] **Step 7: 提交证据与交接**

```powershell
git add README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs
git commit -m "docs: record observability security evidence"
```

## Self-Review Mapping

- 规格第 3 节依赖核验：Task 1。
- 规格第 4 节请求关联：Task 2、Task 5。
- 规格第 5 节安全日志：Task 3、Task 5。
- 规格第 6 节 Prometheus 指标：Task 4、Task 5、Task 6。
- 规格第 7 节健康与错误边界：Task 5 完整 API 回归。
- 规格第 8 节安全与并发测试：Task 2–6。
- 规格第 9 节文件边界：Tasks 2–6；middleware 按规格保留在 `api/app.py`，未增加额外层。
- 规格第 10 节完成条件：Task 7。

无 OpenTelemetry、Grafana、Redis、生产 IAM、CI/CD、Caddy/HTTPS、公开部署或性能指标任务；这些范围没有被计划中的容器、依赖或文档步骤暗中引入。
