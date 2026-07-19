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


@pytest.mark.parametrize("object_type", [ObjectType.EQUIPMENT, ObjectType.TASK])
def test_unimplemented_scenario_fails_closed(object_type: ObjectType) -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    with pytest.raises(module.UnsupportedScenario, match="unsupported_scenario"):
        registry.get(request(object_type))


def test_incomplete_request_fails_closed() -> None:
    module = registry_module()
    registry = module.build_default_scenario_registry()

    with pytest.raises(module.UnsupportedScenario, match="unsupported_scenario"):
        registry.get(OperationRequest(message="缺少类型"))
