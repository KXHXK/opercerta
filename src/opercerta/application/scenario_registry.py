from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from opercerta.domain.agent import (
    AgentAnalysis,
    GoalEncoding,
    ReadToolName,
    ToolObservation,
)
from opercerta.domain.contracts import ActionType, ObjectType, OperationRequest
from opercerta.domain.maintenance import (
    EquipmentEvidence,
    MaintenanceAssessment,
    MaintenanceEvidenceBundle,
    MaintenancePlan,
    MaintenancePolicyEvidence,
    assess_maintenance,
    build_maintenance_plan,
)
from opercerta.domain.replenishment import (
    EvidenceBundle,
    InventoryEvidence,
    ModelPlanExplanation,
    PolicyEvidence,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    assess_replenishment,
    build_plan,
)
from opercerta.domain.scenarios import ScenarioKind
from opercerta.domain.task_recovery import (
    TaskEvidence,
    TaskRecoveryAssessment,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPlan,
    TaskRecoveryPolicyEvidence,
    assess_task_recovery,
    build_task_recovery_plan,
)


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


@dataclass(frozen=True, slots=True)
class TaskRecoveryScenario:
    kind: ScenarioKind = ScenarioKind.TASK
    object_type: ObjectType = ObjectType.TASK


ScenarioEvidence = EvidenceBundle | MaintenanceEvidenceBundle | TaskRecoveryEvidenceBundle
ScenarioAssessment = ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment
ScenarioPlan = ReplenishmentPlan | MaintenancePlan | TaskRecoveryPlan


@dataclass(frozen=True, slots=True)
class AgentScenarioResult:
    evidence: ScenarioEvidence
    assessment: ScenarioAssessment
    plan: ScenarioPlan | None


class ScenarioRegistry:
    def __init__(self, scenarios: tuple[ControlledActionScenario, ...]) -> None:
        self._scenarios = {
            (action, scenario.object_type): scenario
            for scenario in scenarios
            for action in (ActionType.QUERY, ActionType.CREATE_WORK_ORDER)
        }
        self._scenario_kinds = {scenario.kind for scenario in scenarios}

    def get(self, request: OperationRequest) -> ControlledActionScenario:
        if request.requested_action is None or request.object_type is None:
            raise UnsupportedScenario
        try:
            return self._scenarios[(request.requested_action, request.object_type)]
        except KeyError:
            raise UnsupportedScenario from None

    def evaluate_agent_result(
        self,
        goal: GoalEncoding,
        observations: tuple[ToolObservation, ...],
        analysis: AgentAnalysis,
        now: datetime,
    ) -> AgentScenarioResult:
        if goal.scenario not in self._scenario_kinds:
            raise UnsupportedScenario
        successful = {
            observation.tool_name: observation
            for observation in observations
            if observation.status == "ok"
        }
        explanation = ModelPlanExplanation(
            summary=analysis.summary,
            rationale=analysis.recommendation,
        )
        create_requested = goal.goal is ActionType.CREATE_WORK_ORDER

        if goal.scenario is ScenarioKind.INVENTORY:
            inventory = InventoryEvidence.model_validate(
                self._payload(successful, ReadToolName.INVENTORY_SNAPSHOT)
            )
            policy = PolicyEvidence.model_validate(
                self._payload(successful, ReadToolName.POLICY_CONSTRAINTS)
            )
            evidence = EvidenceBundle(inventory=inventory, policy=policy)
            if (
                inventory.evidence_id != successful[ReadToolName.INVENTORY_SNAPSHOT].evidence_ref
                or policy.evidence_id != successful[ReadToolName.POLICY_CONSTRAINTS].evidence_ref
            ):
                raise ValueError("agent_evidence_reference_mismatch")
            assessment = assess_replenishment(evidence, now)
            plan = (
                build_plan(assessment, explanation, policy.rule_version)
                if create_requested and assessment.replenishment_required
                else None
            )
            return AgentScenarioResult(evidence, assessment, plan)

        if goal.scenario is ScenarioKind.EQUIPMENT:
            equipment = EquipmentEvidence.model_validate(
                self._payload(successful, ReadToolName.EQUIPMENT_STATUS)
            )
            maintenance_policy = MaintenancePolicyEvidence.model_validate(
                self._payload(successful, ReadToolName.POLICY_CONSTRAINTS)
            )
            maintenance_evidence = MaintenanceEvidenceBundle(
                equipment=equipment,
                policy=maintenance_policy,
            )
            if (
                equipment.evidence_id != successful[ReadToolName.EQUIPMENT_STATUS].evidence_ref
                or maintenance_policy.evidence_id
                != successful[ReadToolName.POLICY_CONSTRAINTS].evidence_ref
            ):
                raise ValueError("agent_evidence_reference_mismatch")
            maintenance_assessment = assess_maintenance(maintenance_evidence, now)
            maintenance_plan = (
                build_maintenance_plan(
                    maintenance_assessment,
                    explanation,
                    maintenance_policy.rule_version,
                )
                if create_requested and maintenance_assessment.maintenance_required
                else None
            )
            return AgentScenarioResult(
                maintenance_evidence,
                maintenance_assessment,
                maintenance_plan,
            )

        task = TaskEvidence.model_validate(self._payload(successful, ReadToolName.TASK_STATUS))
        task_policy = TaskRecoveryPolicyEvidence.model_validate(
            self._payload(successful, ReadToolName.POLICY_CONSTRAINTS)
        )
        task_evidence = TaskRecoveryEvidenceBundle(task=task, policy=task_policy)
        if (
            task.evidence_id != successful[ReadToolName.TASK_STATUS].evidence_ref
            or task_policy.evidence_id != successful[ReadToolName.POLICY_CONSTRAINTS].evidence_ref
        ):
            raise ValueError("agent_evidence_reference_mismatch")
        task_assessment = assess_task_recovery(task_evidence, now)
        task_plan = (
            build_task_recovery_plan(task_assessment, explanation, task_policy)
            if create_requested and task_assessment.recovery_required
            else None
        )
        return AgentScenarioResult(task_evidence, task_assessment, task_plan)

    @staticmethod
    def _payload(
        successful: dict[ReadToolName, ToolObservation],
        name: ReadToolName,
    ) -> dict[str, object]:
        try:
            return dict(successful[name].structured_payload)
        except KeyError:
            raise ValueError("required_agent_evidence_missing") from None


def build_default_scenario_registry() -> ScenarioRegistry:
    scenarios: tuple[ControlledActionScenario, ...] = (
        ReplenishmentScenario(),
        MaintenanceScenario(),
        TaskRecoveryScenario(),
    )
    return ScenarioRegistry(scenarios)
