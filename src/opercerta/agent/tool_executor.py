from hashlib import sha256
from typing import Protocol, cast
from uuid import UUID

from pydantic import BaseModel, JsonValue

from opercerta.domain.agent import ReadToolName, ToolCallProposal, ToolObservation
from opercerta.domain.errors import (
    EquipmentNotFound,
    EvidenceUnavailable,
    InvalidAgentToolArguments,
    InvalidEquipmentEvidence,
    InvalidInventoryEvidence,
    InvalidMaintenancePolicyEvidence,
    InvalidPolicyEvidence,
    InvalidTaskEvidence,
    InvalidTaskRecoveryPolicyEvidence,
    InventoryNotFound,
    TaskNotFound,
)
from opercerta.domain.work_orders import canonical_payload_json


class ReadToolGateway(Protocol):
    async def read_agent_tool(
        self,
        name: ReadToolName,
        arguments: dict[str, JsonValue],
    ) -> BaseModel: ...


EXPECTED_READ_FAILURES = (
    EquipmentNotFound,
    EvidenceUnavailable,
    InvalidAgentToolArguments,
    InvalidEquipmentEvidence,
    InvalidInventoryEvidence,
    InvalidMaintenancePolicyEvidence,
    InvalidPolicyEvidence,
    InvalidTaskEvidence,
    InvalidTaskRecoveryPolicyEvidence,
    InventoryNotFound,
    TaskNotFound,
)


class ToolExecutor:
    def __init__(self, gateway: ReadToolGateway) -> None:
        self._gateway = gateway

    async def execute(self, proposal: ToolCallProposal) -> ToolObservation:
        canonical_arguments = canonical_payload_json(proposal.arguments)
        arguments_hash = sha256(canonical_arguments.encode("utf-8")).hexdigest()
        try:
            evidence = await self._gateway.read_agent_tool(
                proposal.tool_name,
                proposal.arguments,
            )
        except EXPECTED_READ_FAILURES as error:
            return ToolObservation(
                tool_call_id=proposal.tool_call_id,
                tool_name=proposal.tool_name,
                arguments_hash=arguments_hash,
                status="error",
                safe_summary="只读证据不可用。",
                structured_payload={"error_code": error.code},
            )

        evidence_ref = getattr(evidence, "evidence_id", None)
        if not isinstance(evidence_ref, UUID):
            raise TypeError("read_tool_evidence_invalid")
        payload = cast(dict[str, JsonValue], evidence.model_dump(mode="json"))
        return ToolObservation(
            tool_call_id=proposal.tool_call_id,
            tool_name=proposal.tool_name,
            arguments_hash=arguments_hash,
            status="ok",
            evidence_ref=evidence_ref,
            safe_summary="已取得并验证只读业务证据。",
            structured_payload=payload,
        )
