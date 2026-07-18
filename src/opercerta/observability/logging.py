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
    logger.log(
        level,
        event,
        extra={key: value for key, value in values.items() if value is not None},
    )


def configure_json_logging(service: str, stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(SafeJsonFormatter(service))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
