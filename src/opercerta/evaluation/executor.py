"""Execute frozen API contract cases against real FastAPI and PostgreSQL boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx

from opercerta.api.auth import DemoAccount, JwtAuthenticator
from opercerta.application.operation_runner import OperationRunner
from opercerta.domain.approvals import ApprovalDecision, BoundApprovalCommand
from opercerta.domain.errors import ApprovalExpired, UnknownTool
from opercerta.domain.replenishment import ApprovalBinding
from opercerta.evaluation.contracts import EvalCase
from opercerta.evaluation.runner import CaseExecution
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.replenishment_operation_repository import (
    ReplenishmentOperationRepository,
)
from opercerta.infrastructure.mcp_gateway import McpToolGateway
from opercerta.tools.catalog import SyntheticCatalog


class ApiCaseExecutor:
    """Translate declared HTTP steps to calls; facts always come from the repository."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        authenticator: JwtAuthenticator,
        operations: ReplenishmentOperationRepository,
        *,
        approvals: ApprovalRepository | None = None,
        runner: OperationRunner | None = None,
        catalog: SyntheticCatalog | None = None,
        gateway: McpToolGateway | None = None,
    ) -> None:
        self._client = client
        self._authenticator = authenticator
        self._operations = operations
        self._approvals = approvals
        self._runner = runner
        self._catalog = catalog
        self._gateway = gateway
        self.operation_ids: list[UUID] = []

    async def execute(self, case: EvalCase) -> CaseExecution:
        operation_id: UUID | None = None
        response: httpx.Response | None = None
        status_override: int | None = None
        error_override: str | None = None
        force_expired_approval = False
        for step in case.steps:
            action = step.get("action")
            if action in {"create_operation", "create_operation_as"}:
                actor = self._actor_for_step(case, step)
                response = await self._client.post(
                    "/api/v1/operations",
                    headers=self._headers(actor, step),
                    json=self._operation_body(str(step.get("sku", "SKU-LOW-001"))),
                )
                operation_id = self._operation_id_from(response)
                if operation_id is not None:
                    self.operation_ids.append(operation_id)
            elif action == "post_raw_operation":
                response = await self._client.post(
                    "/api/v1/operations",
                    headers=self._headers(DemoAccount(case.actor), step),
                    json=cast(dict[str, object], step["body"]),
                )
                operation_id = self._operation_id_from(response)
                if operation_id is not None:
                    self.operation_ids.append(operation_id)
            elif action == "get_operation":
                if operation_id is None:
                    raise ValueError("get_operation_requires_created_operation")
                response = await self._client.get(
                    f"/api/v1/operations/{operation_id}",
                    headers=self._headers(DemoAccount(case.actor), step),
                )
            elif action == "get_unknown_operation":
                response = await self._client.get(
                    f"/api/v1/operations/{uuid4()}",
                    headers=self._headers(DemoAccount(case.actor), step),
                )
            elif action == "submit_approval":
                if operation_id is None:
                    raise ValueError("submit_approval_requires_created_operation")
                detail = await self._operations.load_detail(operation_id)
                payload = self._approval_payload(
                    detail.approval_binding,
                    decision=str(step.get("decision", "approved")),
                )
                if step.get("binding") == "mismatched":
                    payload["expected_plan_hash"] = "0" * 64
                if step.get("inject_approver_id") is not None:
                    payload["approver_id"] = step["inject_approver_id"]
                if force_expired_approval:
                    try:
                        await self._require_approvals().submit_bound_once(
                            self._bound_command(
                                operation_id,
                                detail.approval_binding,
                                str(step.get("decision", "approved")),
                            ),
                            datetime.now(UTC) + timedelta(days=1),
                        )
                    except ApprovalExpired:
                        status_override = 409
                        error_override = ApprovalExpired.code
                    else:
                        raise AssertionError("expired approval was unexpectedly accepted")
                else:
                    response = await self._client.post(
                        f"/api/v1/operations/{operation_id}/approval",
                        headers=self._headers(DemoAccount(case.actor), step),
                        json=payload,
                    )
            elif action in {"replay_recovery", "restart_and_recover"}:
                await self._require_runner().recover_all()
            elif action == "mutate_inventory":
                catalog = self._require_catalog()
                sku = str(step["sku"])
                catalog.replace_inventory(sku, on_hand_quantity=25, reserved_quantity=8)
            elif action == "create_expired_operation":
                response = await self._client.post(
                    "/api/v1/operations",
                    headers=self._headers(DemoAccount.OPERATOR, step),
                    json=self._operation_body(str(step.get("sku", "SKU-LOW-001"))),
                )
                operation_id = self._operation_id_from(response)
                if operation_id is None:
                    continue
                self.operation_ids.append(operation_id)
                force_expired_approval = True
            elif action == "record_approval_then_restart":
                if operation_id is None:
                    raise ValueError("record_approval_requires_created_operation")
                detail = await self._operations.load_detail(operation_id)
                await self._require_approvals().submit_bound_once(
                    self._bound_command(
                        operation_id,
                        detail.approval_binding,
                        str(step.get("decision", "approved")),
                    ),
                    datetime.now(UTC),
                )
                await self._require_runner().recover_all()
            elif action == "invoke_mcp_tool":
                try:
                    await self._require_gateway().call_raw(str(step["tool"]), {})
                except UnknownTool:
                    status_override = 400
                    error_override = UnknownTool.code
                else:
                    raise AssertionError("unknown MCP tool was unexpectedly accepted")
            else:
                raise ValueError(f"unsupported_evaluation_action:{action}")

        if response is None:
            if status_override is not None:
                return CaseExecution(
                    status_code=status_override,
                    error_code=error_override,
                )
            raise ValueError("case_has_no_response_producing_step")
        execution = await self._execution_from(response, operation_id)
        if status_override is not None:
            return execution.model_copy(
                update={"status_code": status_override, "error_code": error_override}
            )
        return execution

    def _actor_for_step(
        self,
        case: EvalCase,
        step: Mapping[str, object],
    ) -> DemoAccount | None:
        actor = step.get("actor", case.actor.value)
        if actor == "anonymous":
            return None
        return DemoAccount(str(actor))

    def _headers(
        self,
        account: DemoAccount | None,
        step: Mapping[str, object],
    ) -> dict[str, str]:
        credential = step.get("credential")
        if account is None:
            return {}
        if credential == "tampered":
            token = self._authenticator.issue_demo_token(account, datetime.now(UTC))
            return {"Authorization": f"Bearer x{token[1:]}"}
        if credential == "expired":
            token = self._authenticator.issue_demo_token(
                account,
                datetime.now(UTC) - timedelta(seconds=self._authenticator.ttl_seconds + 1),
            )
            return {"Authorization": f"Bearer {token}"}
        if credential == "wrong-issuer":
            return {"Authorization": "Bearer malformed-wrong-issuer-token"}
        token = self._authenticator.issue_demo_token(account, datetime.now(UTC))
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _operation_body(sku: str) -> dict[str, str]:
        return {
            "message": f"为 {sku} 创建补货工单",
            "requested_action": "create_work_order",
            "object_type": "inventory",
            "object_id": sku,
        }

    @staticmethod
    def _operation_id_from(response: httpx.Response) -> UUID | None:
        if response.status_code != 202:
            return None
        return UUID(str(cast(dict[str, object], response.json())["operation_id"]))

    @staticmethod
    def _approval_payload(
        binding: ApprovalBinding | None,
        *,
        decision: str,
    ) -> dict[str, object]:
        if binding is None:
            raise ValueError("approval_binding_is_missing")
        value = cast(Mapping[str, object], binding.model_dump(mode="json"))
        return {
            "decision": decision,
            "reason": f"evaluation {decision}",
            "expected_inventory_evidence_id": value["inventory_evidence_id"],
            "expected_policy_evidence_id": value["policy_evidence_id"],
            "expected_rule_version": value["rule_version"],
            "expected_decision_facts_hash": value["decision_facts_hash"],
            "expected_plan_hash": value["plan_hash"],
            "expected_recommended_quantity": value["recommended_quantity"],
        }

    @staticmethod
    def _bound_command(
        operation_id: UUID,
        binding: ApprovalBinding | None,
        decision: str,
    ) -> BoundApprovalCommand:
        if binding is None:
            raise ValueError("approval_binding_is_missing")
        return BoundApprovalCommand(
            operation_id=operation_id,
            approver_id="evaluation.approver",
            decision=ApprovalDecision(decision),
            reason=f"evaluation {decision}",
            expected_binding=binding,
        )

    def _require_approvals(self) -> ApprovalRepository:
        if self._approvals is None:
            raise ValueError("approval_repository_is_required_for_evaluation_action")
        return self._approvals

    def _require_runner(self) -> OperationRunner:
        if self._runner is None:
            raise ValueError("operation_runner_is_required_for_evaluation_action")
        return self._runner

    def _require_catalog(self) -> SyntheticCatalog:
        if self._catalog is None:
            raise ValueError("synthetic_catalog_is_required_for_evaluation_action")
        return self._catalog

    def _require_gateway(self) -> McpToolGateway:
        if self._gateway is None:
            raise ValueError("mcp_gateway_is_required_for_evaluation_action")
        return self._gateway

    async def _execution_from(
        self,
        response: httpx.Response,
        operation_id: UUID | None,
    ) -> CaseExecution:
        body = cast(dict[str, object], response.json())
        if operation_id is None:
            return CaseExecution(
                status_code=response.status_code,
                error_code=cast(str | None, body.get("code")),
            )
        detail = await self._operations.load_detail(operation_id)
        return CaseExecution(
            status_code=response.status_code,
            error_code=detail.error.code
            if detail.error is not None
            else cast(str | None, body.get("code")),
            terminal_status=detail.status.value,
            approval_count=1 if detail.approval is not None else 0,
            work_order_count=1 if detail.work_order is not None else 0,
            audit_event_names=detail.event_types,
        )
