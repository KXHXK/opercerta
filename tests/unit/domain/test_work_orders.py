from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from opercerta.domain.errors import IdempotencyConflict, WriteNotAuthorized
from opercerta.domain.work_orders import (
    WorkOrderCommand,
    WorkOrderRecord,
    WorkOrderWriteResult,
    canonical_payload_json,
    derive_idempotency_key,
    hash_payload,
)

OPERATION_ID = UUID("00000000-0000-4000-8000-000000000001")
WORK_ORDER_ID = UUID("00000000-0000-4000-8000-000000000002")


def valid_record_data() -> dict[str, object]:
    now = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    return {
        "id": WORK_ORDER_ID,
        "operation_id": OPERATION_ID,
        "idempotency_key": derive_idempotency_key(OPERATION_ID),
        "payload": {"quantity": 4, "sku": "SKU-DEMO-001"},
        "payload_hash": hash_payload({"quantity": 4, "sku": "SKU-DEMO-001"}),
        "status": "created",
        "created_at": now,
        "updated_at": now,
    }


def test_command_accepts_an_empty_json_object() -> None:
    command = WorkOrderCommand(operation_id=OPERATION_ID, payload={})

    assert command.payload == {}


@pytest.mark.parametrize(
    "data",
    [
        {"payload": {}},
        {"operation_id": OPERATION_ID},
        {"operation_id": "not-a-uuid", "payload": {}},
        {"operation_id": OPERATION_ID, "payload": []},
        {"operation_id": OPERATION_ID, "payload": {1: "value"}},
        {"operation_id": OPERATION_ID, "payload": {"items": ("a", "b")}},
        {"operation_id": OPERATION_ID, "payload": {"value": object()}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("nan")}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("inf")}},
        {"operation_id": OPERATION_ID, "payload": {"value": float("-inf")}},
        {"operation_id": OPERATION_ID, "payload": {}, "extra": True},
    ],
)
def test_command_rejects_invalid_input(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WorkOrderCommand.model_validate(data)


def test_command_fields_cannot_be_reassigned() -> None:
    command = WorkOrderCommand(operation_id=OPERATION_ID, payload={})

    with pytest.raises(ValidationError):
        command.operation_id = WORK_ORDER_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idempotency_key", ""),
        ("idempotency_key", "x" * 129),
        ("payload_hash", "A" * 64),
        ("payload_hash", "0" * 63),
        ("status", "executing"),
        ("created_at", datetime(2026, 7, 16, 0, 0)),
        ("updated_at", datetime(2026, 7, 16, 0, 0)),
    ],
)
def test_record_rejects_invalid_fields(field: str, value: object) -> None:
    data = valid_record_data()
    data[field] = value

    with pytest.raises(ValidationError):
        WorkOrderRecord.model_validate(data)


def test_write_result_preserves_record_and_replay_flag() -> None:
    record = WorkOrderRecord.model_validate(valid_record_data())

    result = WorkOrderWriteResult(work_order=record, replayed=True)

    assert result.work_order.id == WORK_ORDER_ID
    assert result.replayed is True


def test_record_forbids_extra_fields_and_reassignment() -> None:
    data = valid_record_data()
    data["extra"] = True
    with pytest.raises(ValidationError):
        WorkOrderRecord.model_validate(data)

    record = WorkOrderRecord.model_validate(valid_record_data())
    with pytest.raises(ValidationError):
        record.status = "created"


def test_idempotency_key_is_stable_for_operation() -> None:
    assert derive_idempotency_key(OPERATION_ID) == (
        "work-order:v1:00000000-0000-4000-8000-000000000001"
    )


def test_canonical_payload_is_compact_sorted_and_unicode_preserving() -> None:
    assert canonical_payload_json({"sku": "设备-01", "quantity": 4}) == (
        '{"quantity":4,"sku":"设备-01"}'
    )


def test_payload_hash_is_independent_of_dictionary_order() -> None:
    assert hash_payload({"quantity": 4, "sku": "SKU-DEMO-001"}) == hash_payload(
        {"sku": "SKU-DEMO-001", "quantity": 4}
    )


def test_payload_hash_changes_with_content() -> None:
    assert hash_payload({"quantity": 4}) != hash_payload({"quantity": 5})


def test_domain_errors_keep_safe_location_fields() -> None:
    conflict = IdempotencyConflict(
        OPERATION_ID,
        derive_idempotency_key(OPERATION_ID),
    )
    unauthorized = WriteNotAuthorized(OPERATION_ID, "planning")

    assert conflict.code == "idempotency_conflict"
    assert conflict.operation_id == OPERATION_ID
    assert conflict.idempotency_key == derive_idempotency_key(OPERATION_ID)
    assert unauthorized.code == "write_not_authorized"
    assert unauthorized.operation_id == OPERATION_ID
    assert unauthorized.status == "planning"
