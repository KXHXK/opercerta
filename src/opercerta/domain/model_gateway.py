from typing import Protocol

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


class MockModelGateway:
    async def explain_plan(
        self,
        assessment: ReplenishmentAssessment,
    ) -> ModelPlanExplanation:
        return ModelPlanExplanation(
            summary=f"建议为 {assessment.sku} 创建补货计划。",
            rationale="数量由已验证库存事实和版本化规则确定。",
        )
