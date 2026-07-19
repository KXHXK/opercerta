from dataclasses import dataclass
from typing import Protocol

from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.scenarios import ScenarioKind


class UnsupportedScenario(ValueError):
    code = "unsupported_scenario"

    def __init__(self) -> None:
        super().__init__(self.code)


class ControlledActionScenario(Protocol):
    @property
    def kind(self) -> ScenarioKind: ...

    @property
    def object_type(self) -> ObjectType: ...


@dataclass(frozen=True, slots=True)
class ReplenishmentScenario:
    kind: ScenarioKind = ScenarioKind.INVENTORY
    object_type: ObjectType = ObjectType.INVENTORY


@dataclass(frozen=True, slots=True)
class MaintenanceScenario:
    kind: ScenarioKind = ScenarioKind.EQUIPMENT
    object_type: ObjectType = ObjectType.EQUIPMENT


class ScenarioRegistry:
    def __init__(self, scenarios: tuple[ControlledActionScenario, ...]) -> None:
        self._scenarios = {
            (ActionType.CREATE_WORK_ORDER, scenario.object_type): scenario for scenario in scenarios
        }

    def get(self, request: OperationRequest) -> ControlledActionScenario:
        if request.requested_action is None or request.object_type is None:
            raise UnsupportedScenario
        try:
            return self._scenarios[(request.requested_action, request.object_type)]
        except KeyError:
            raise UnsupportedScenario from None


def build_default_scenario_registry() -> ScenarioRegistry:
    scenarios: tuple[ControlledActionScenario, ...] = (
        ReplenishmentScenario(),
        MaintenanceScenario(),
    )
    return ScenarioRegistry(scenarios)
