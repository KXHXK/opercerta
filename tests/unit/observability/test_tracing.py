import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine, text

from opercerta.observability.tracing import Tracing, instrument_sqlalchemy_engine


def test_tracing_keeps_only_low_cardinality_safe_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(provider.get_tracer("opercerta-test"))

    with tracing.span(
        "graph.node",
        {
            "scenario": "equipment",
            "node": "calculate_assessment",
            "error_type": "none",
            "request_id": "request-1",
            "operation_id": "00000000-0000-4000-8000-000000000001",
            "jwt": "Bearer secret",
            "api_key": "model-secret",
            "message": "full user request",
            "evidence": '{"private":"payload"}',
        },
    ):
        pass

    attributes = dict(exporter.get_finished_spans()[0].attributes)
    assert attributes == {
        "scenario": "equipment",
        "node": "calculate_assessment",
        "error_type": "none",
        "request_id": "request-1",
        "operation_id": "00000000-0000-4000-8000-000000000001",
    }


def test_database_trace_records_operation_without_sql_or_parameters() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(provider.get_tracer("opercerta-db-test"))
    engine = create_engine("sqlite://")
    instrument_sqlalchemy_engine(engine, tracing)

    with engine.connect() as connection:
        connection.execute(text("select :secret"), {"secret": "must-not-enter-span"})

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "db.execute"
    assert dict(spans[0].attributes) == {
        "component": "postgresql",
        "operation": "execute",
    }


def test_trace_exception_records_only_safe_type_without_message_or_stack() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing = Tracing(provider.get_tracer("opercerta-error-test"))

    with pytest.raises(RuntimeError, match="must-not-enter-span"):
        with tracing.span("mcp.call", {"component": "mcp", "operation": "read"}):
            raise RuntimeError("Bearer must-not-enter-span password=secret")

    span = exporter.get_finished_spans()[0]
    assert dict(span.attributes) == {
        "component": "mcp",
        "operation": "read",
        "error_type": "RuntimeError",
    }
    assert span.events == ()
