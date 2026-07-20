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
KNOWN_MCP_TOOLS = frozenset(
    {
        "inventory.get_snapshot",
        "equipment.get_status",
        "task.get_status",
        "policy.list_constraints",
        "work_order.create",
        "work_order.get",
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
    cache_events: Counter
    mcp_tool_calls: Counter

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
            cache_events=Counter(
                "opercerta_cache_events_total",
                "Evidence cache outcomes.",
                ("outcome",),
                registry=registry,
            ),
            mcp_tool_calls=Counter(
                "opercerta_mcp_tool_calls_total",
                "MCP tool call attempts.",
                ("tool_name",),
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

    def count_cache_event(self, outcome: str) -> None:
        safe_outcome = outcome if outcome in {"hit", "miss", "write", "error"} else "error"
        self.cache_events.labels(outcome=safe_outcome).inc()

    def count_mcp_tool_call(self, tool_name: str) -> None:
        safe_name = tool_name if tool_name in KNOWN_MCP_TOOLS else "other"
        self.mcp_tool_calls.labels(tool_name=safe_name).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
