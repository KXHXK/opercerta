from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from functools import wraps
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine, ExceptionContext

SAFE_ATTRIBUTE_NAMES = frozenset(
    {
        "scenario",
        "node",
        "error_type",
        "component",
        "operation",
        "request_id",
        "operation_id",
        "thread_id",
        "tool_call_id",
    }
)
DB_SPANS_KEY = "_opercerta_db_spans"


class Tracing:
    def __init__(self, tracer: Tracer | None = None) -> None:
        self._tracer = tracer or trace.get_tracer("opercerta")

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, object] | None = None) -> Iterator[Span]:
        with self._tracer.start_as_current_span(
            name,
            attributes=self._safe_attributes(attributes),
            record_exception=False,
            set_status_on_exception=False,
        ) as active_span:
            try:
                yield active_span
            except Exception as error:
                active_span.set_attribute("error_type", type(error).__name__)
                active_span.set_status(Status(StatusCode.ERROR))
                raise

    def start_span(
        self,
        name: str,
        attributes: Mapping[str, object] | None = None,
    ) -> Span:
        return self._tracer.start_span(name, attributes=self._safe_attributes(attributes))

    @staticmethod
    def _safe_attributes(
        attributes: Mapping[str, object] | None,
    ) -> dict[str, str | bool | int | float]:
        return {
            key: value
            for key, value in (attributes or {}).items()
            if key in SAFE_ATTRIBUTE_NAMES and isinstance(value, str | bool | int | float)
        }


NOOP_TRACING = Tracing()


def trace_async_node[StateT](
    tracing: Tracing,
    *,
    scenario: str,
    node: str,
    function: Callable[[StateT], Awaitable[Any]],
) -> Callable[[StateT], Awaitable[Any]]:
    @wraps(function)
    async def traced(state: StateT) -> Any:
        with tracing.span(
            "graph.node",
            {"component": "graph", "scenario": scenario, "node": node},
        ):
            return await function(state)

    return traced


def instrument_sqlalchemy_engine(engine: Engine, tracing: Tracing) -> None:
    def before_cursor_execute(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        span = tracing.start_span(
            "db.execute",
            {"component": "postgresql", "operation": "execute"},
        )
        connection.info.setdefault(DB_SPANS_KEY, []).append(span)

    def finish_span(connection: Connection, error_type: str | None = None) -> None:
        spans = connection.info.get(DB_SPANS_KEY)
        if not spans:
            return
        span = spans.pop()
        if error_type is not None:
            span.set_attribute("error_type", error_type)
            span.set_status(Status(StatusCode.ERROR))
        span.end()

    def after_cursor_execute(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        finish_span(connection)

    def handle_error(exception_context: ExceptionContext) -> None:
        connection = exception_context.connection
        if connection is not None:
            finish_span(
                connection,
                type(exception_context.original_exception).__name__,
            )

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)
    event.listen(engine, "handle_error", handle_error)


def configure_tracing(
    *, enabled: bool, endpoint: str | None, service_name: str
) -> tuple[Tracing, TracerProvider | None]:
    if not enabled:
        return NOOP_TRACING, None
    if endpoint is None:
        raise ValueError("OTLP endpoint is required when tracing is enabled")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return Tracing(provider.get_tracer(service_name)), provider
