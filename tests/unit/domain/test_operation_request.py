from importlib import import_module

import pytest
from pydantic import ValidationError


def operation_request_type():
    try:
        return import_module("opercerta.domain.contracts").OperationRequest
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"OperationRequest is unavailable: {exc}", pytrace=False)


def test_blank_message_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate({"message": "   "})


def test_undeclared_field_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate({"message": "check stock", "shell": "whoami"})


def test_known_action_is_accepted() -> None:
    operation_request = operation_request_type()

    request = operation_request.model_validate(
        {"message": "create a repair order", "requested_action": "create_work_order"}
    )

    assert request.requested_action.value == "create_work_order"


def test_unknown_action_is_rejected() -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate(
            {"message": "delete inventory", "requested_action": "delete_inventory"}
        )


def test_complete_object_reference_is_accepted() -> None:
    operation_request = operation_request_type()

    request = operation_request.model_validate(
        {
            "message": "check stock",
            "object_type": "inventory",
            "object_id": "SKU-DEMO-001",
        }
    )

    assert request.object_type.value == "inventory"
    assert request.object_id == "SKU-DEMO-001"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "check stock", "object_type": "inventory"},
        {"message": "check stock", "object_id": "SKU-DEMO-001"},
    ],
)
def test_partial_object_reference_is_rejected(payload: dict[str, str]) -> None:
    operation_request = operation_request_type()

    with pytest.raises(ValidationError):
        operation_request.model_validate(payload)
