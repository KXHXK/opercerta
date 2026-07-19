from typing import Protocol

from opercerta.domain.maintenance import MaintenanceAssessment
from opercerta.domain.replenishment import (
    ModelPlanExplanation,
    ReplenishmentAssessment,
)


class ModelGateway(Protocol):
    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        raise NotImplementedError

    async def explain_maintenance(
        self,
        assessment: MaintenanceAssessment,
    ) -> ModelPlanExplanation:
        raise NotImplementedError


class MockModelGateway:
    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        return ModelPlanExplanation(
            summary=f"建议为 {assessment.sku} 创建补货计划。",
            rationale="数量由已验证库存事实和版本化规则确定。",
        )

    async def explain_maintenance(
        self,
        assessment: MaintenanceAssessment,
    ) -> ModelPlanExplanation:
        return ModelPlanExplanation(
            summary=f"建议为设备 {assessment.equipment_id} 创建维修工单。",
            rationale="维修优先级由已验证设备证据和版本化规则确定。",
        )
