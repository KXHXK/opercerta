from typing import Protocol

from opercerta.domain.maintenance import MaintenanceAssessment
from opercerta.domain.replenishment import (
    ModelPlanExplanation,
    ReplenishmentAssessment,
)
from opercerta.domain.task_recovery import TaskRecoveryAssessment

ScenarioAssessment = ReplenishmentAssessment | MaintenanceAssessment | TaskRecoveryAssessment


class ModelGateway(Protocol):
    async def explain_plan(
        self,
        assessment: ScenarioAssessment,
    ) -> ModelPlanExplanation:
        raise NotImplementedError


class MockModelGateway:
    async def explain_plan(
        self,
        assessment: ScenarioAssessment,
    ) -> ModelPlanExplanation:
        if isinstance(assessment, MaintenanceAssessment):
            return ModelPlanExplanation(
                summary=f"建议为设备 {assessment.equipment_id} 创建维修工单。",
                rationale="维修优先级由已验证设备证据和版本化规则确定。",
            )
        if isinstance(assessment, TaskRecoveryAssessment):
            return ModelPlanExplanation(
                summary=f"建议为任务 {assessment.task_id} 创建人工恢复工单。",
                rationale="恢复动作由已验证阻塞或逾期事实和版本化规则确定。",
            )
        return ModelPlanExplanation(
            summary=f"建议为 {assessment.sku} 创建补货计划。",
            rationale="数量由已验证库存事实和版本化规则确定。",
        )
