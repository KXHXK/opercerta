import hashlib
import json
import math
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    StringConstraints,
    field_validator,
)

IdempotencyKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
]
PayloadHash = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


def _require_json_value(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _require_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            _require_json_value(item)
        return
    raise ValueError("payload must contain only JSON values")


class WorkOrderCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: UUID
    payload: dict[str, JsonValue]

    @field_validator("payload", mode="before")
    @classmethod
    def require_json_object(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise ValueError("payload must be a JSON object")
        _require_json_value(value)
        return value


class WorkOrderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    operation_id: UUID
    idempotency_key: IdempotencyKey
    payload: dict[str, JsonValue]
    payload_hash: PayloadHash
    status: Literal["created"]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("work-order timestamps must include timezone")
        return value


class WorkOrderWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    work_order: WorkOrderRecord
    replayed: bool


def derive_idempotency_key(operation_id: UUID) -> str:
    return f"work-order:v1:{operation_id}"


def canonical_payload_json(payload: dict[str, JsonValue]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def hash_payload(payload: dict[str, JsonValue]) -> str:
    canonical_json = canonical_payload_json(payload)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
