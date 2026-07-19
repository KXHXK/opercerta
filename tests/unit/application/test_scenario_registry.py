from importlib import import_module

import pytest

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest


def registry_module():
    try:
        return import_module("opercerta.application.scenario_registry")
    except ImportError as exc:
        pytest.fail(f"scenario registry is unavailable: {exc}", pytrace=False)


def request(object_type: ObjectType) -> OperationRequest:
    return OperationRequest(
        message=f"处理 {object_type.value}",
        requested_action=ActionType.CREATE_WORK_ORDER,
        object_type=object_type,
        object_id="SYNTHETIC-001",
    )


def test_default_registry_dispatches_inventory_scenario() -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    scenario = registry.get(request(ObjectType.INVENTORY))

    assert scenario.kind.value == "inventory"


def test_default_registry_dispatches_equipment_scenario() -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    scenario = registry.get(request(ObjectType.EQUIPMENT))

    assert scenario.kind.value == "equipment"


def test_unimplemented_task_scenario_fails_closed() -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    with pytest.raises(module.UnsupportedScenario, match="unsupported_scenario"):
        registry.get(request(ObjectType.TASK))


def test_incomplete_request_fails_closed() -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    with pytest.raises(module.UnsupportedScenario, match="unsupported_scenario"):
        registry.get(OperationRequest(message="缺少类型"))
