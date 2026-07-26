from typing import cast

from pydantic import JsonValue

from opercerta.application.scenario_registry import (
    ScenarioAssessment,
    ScenarioEvidence,
    ScenarioPlan,
)
from opercerta.domain.agent import GoalEncoding, ReadToolName, ToolCallProposal
from opercerta.domain.maintenance import (
    MaintenanceAssessment,
    MaintenanceEvidenceBundle,
    MaintenancePlan,
    RepairWorkOrderPayload,
    build_maintenance_approval_binding,
)
from opercerta.domain.replenishment import (
    EvidenceBundle,
    ReplenishmentAssessment,
    ReplenishmentPlan,
    build_approval_binding,
)
from opercerta.domain.scenarios import ApprovalBinding, ScenarioKind
from opercerta.domain.task_recovery import (
    TaskRecoveryAssessment,
    TaskRecoveryEvidenceBundle,
    TaskRecoveryPlan,
    TaskRecoveryWorkOrderPayload,
    build_task_recovery_approval_binding,
)

_SUBJECT_TOOLS = {
    ScenarioKind.INVENTORY: ReadToolName.INVENTORY_SNAPSHOT,
    ScenarioKind.EQUIPMENT: ReadToolName.EQUIPMENT_STATUS,
    ScenarioKind.TASK: ReadToolName.TASK_STATUS,
}
_SUBJECT_KEYS = {
    ScenarioKind.INVENTORY: "sku",
    ScenarioKind.EQUIPMENT: "equipment_id",
    ScenarioKind.TASK: "task_id",
}
_ACTIONS = {
    ScenarioKind.INVENTORY: "replenish_inventory",
    ScenarioKind.EQUIPMENT: "repair_equipment",
    ScenarioKind.TASK: "recover_task",
}


def required_fact_tools(scenario: ScenarioKind) -> set[ReadToolName]:
    return {_SUBJECT_TOOLS[scenario], ReadToolName.POLICY_CONSTRAINTS}


def build_refresh_calls(goal: GoalEncoding) -> tuple[ToolCallProposal, ToolCallProposal]:
    subject_key = _SUBJECT_KEYS[goal.scenario]
    return (
        ToolCallProposal(
            tool_call_id="refresh-subject",
            tool_name=_SUBJECT_TOOLS[goal.scenario],
            arguments={subject_key: goal.object_id},
        ),
        ToolCallProposal(
            tool_call_id="refresh-policy",
            tool_name=ReadToolName.POLICY_CONSTRAINTS,
            arguments={
                "action": _ACTIONS[goal.scenario],
                subject_key: goal.object_id,
            },
        ),
    )


def parse_scenario_evidence(
    scenario: ScenarioKind,
    value: object,
) -> ScenarioEvidence:
    if scenario is ScenarioKind.INVENTORY:
        return EvidenceBundle.model_validate(value)
    if scenario is ScenarioKind.EQUIPMENT:
        return MaintenanceEvidenceBundle.model_validate(value)
    return TaskRecoveryEvidenceBundle.model_validate(value)


def parse_scenario_assessment(
    scenario: ScenarioKind,
    value: object,
) -> ScenarioAssessment:
    if scenario is ScenarioKind.INVENTORY:
        return ReplenishmentAssessment.model_validate(value)
    if scenario is ScenarioKind.EQUIPMENT:
        return MaintenanceAssessment.model_validate(value)
    return TaskRecoveryAssessment.model_validate(value)


def parse_scenario_plan(scenario: ScenarioKind, value: object) -> ScenarioPlan:
    if scenario is ScenarioKind.INVENTORY:
        return ReplenishmentPlan.model_validate(value)
    if scenario is ScenarioKind.EQUIPMENT:
        return MaintenancePlan.model_validate(value)
    return TaskRecoveryPlan.model_validate(value)


def build_scenario_approval_binding(
    evidence: ScenarioEvidence,
    plan: ScenarioPlan,
) -> ApprovalBinding:
    if isinstance(evidence, EvidenceBundle) and isinstance(plan, ReplenishmentPlan):
        return ApprovalBinding.model_validate(build_approval_binding(evidence, plan))
    if isinstance(evidence, MaintenanceEvidenceBundle) and isinstance(plan, MaintenancePlan):
        return build_maintenance_approval_binding(evidence, plan)
    if isinstance(evidence, TaskRecoveryEvidenceBundle) and isinstance(plan, TaskRecoveryPlan):
        return build_task_recovery_approval_binding(evidence, plan)
    raise TypeError("scenario_binding_mismatch")


def binding_facts(binding: ApprovalBinding) -> tuple[object, ...]:
    return (
        binding.scenario,
        binding.rule_version,
        binding.decision_facts_hash,
        binding.plan_hash,
        binding.parameters,
    )


def scenario_work_order_payload(plan: ScenarioPlan) -> dict[str, JsonValue]:
    if isinstance(plan, ReplenishmentPlan):
        return {
            "sku": plan.sku,
            "quantity": plan.recommended_quantity,
            "approved_plan_hash": plan.plan_hash,
        }
    if isinstance(plan, MaintenancePlan):
        return cast(
            dict[str, JsonValue],
            RepairWorkOrderPayload(
                equipment_id=plan.equipment_id,
                alert_code=plan.alert_code,
                priority=plan.priority,
                approved_plan_hash=plan.plan_hash,
            ).model_dump(mode="json"),
        )
    return cast(
        dict[str, JsonValue],
        TaskRecoveryWorkOrderPayload(
            task_id=plan.task_id,
            blocker_code=plan.blocker_code,
            retry_count=plan.retry_count,
            recovery_action=plan.recovery_action,
            approved_plan_hash=plan.plan_hash,
        ).model_dump(mode="json"),
    )


def no_action_outcome(scenario: ScenarioKind, *, query: bool) -> str:
    if query:
        return "query_completed"
    return {
        ScenarioKind.INVENTORY: "replenishment_not_required",
        ScenarioKind.EQUIPMENT: "maintenance_not_required",
        ScenarioKind.TASK: "task_recovery_not_required",
    }[scenario]
