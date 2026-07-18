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
        "timestamp",
        "level",
        "service",
        "event",
        "request_id",
        "route",
        "method",
        "status_code",
        "error_code",
    }
    serialized = json.dumps(payload)
    assert "secret-token" not in serialized
    assert "password" not in serialized
    assert "RuntimeError" not in serialized
