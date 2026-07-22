from uuid import UUID


class InvalidRecoveryFacts(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OperationNotFound(LookupError):
    code = "operation_not_found"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)


class ApprovalAlreadyDecided(RuntimeError):
    code = "approval_already_decided"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)


class IdempotencyConflict(RuntimeError):
    code = "idempotency_conflict"

    def __init__(self, operation_id: UUID, idempotency_key: str) -> None:
        self.operation_id = operation_id
        self.idempotency_key = idempotency_key
        super().__init__(self.code)


class WriteNotAuthorized(RuntimeError):
    code = "write_not_authorized"

    def __init__(self, operation_id: UUID, status: str) -> None:
        self.operation_id = operation_id
        self.status = status
        super().__init__(self.code)


class InvalidOperationSnapshot(ValueError):
    code = "invalid_operation_snapshot"

    def __init__(self, operation_id: UUID, reason: str) -> None:
        self.operation_id = operation_id
        self.reason = reason
        super().__init__(self.code)


class OperationTransitionConflict(RuntimeError):
    code = "operation_transition_conflict"

    def __init__(
        self,
        operation_id: UUID,
        current_status: str,
        target_status: str,
    ) -> None:
        self.operation_id = operation_id
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(self.code)


class RecoveryStateConflict(RuntimeError):
    code = "recovery_state_conflict"

    def __init__(self, operation_id: UUID, reason: str) -> None:
        self.operation_id = operation_id
        self.reason = reason
        super().__init__(self.code)


class InventoryNotFound(LookupError):
    code = "inventory_not_found"

    def __init__(self) -> None:
        super().__init__(self.code)


class EquipmentNotFound(LookupError):
    code = "equipment_not_found"

    def __init__(self) -> None:
        super().__init__(self.code)


class TaskNotFound(LookupError):
    code = "task_not_found"

    def __init__(self) -> None:
        super().__init__(self.code)


class EvidenceUnavailable(RuntimeError):
    code = "evidence_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


class EvidenceConflict(RuntimeError):
    code = "evidence_conflict"

    def __init__(self) -> None:
        super().__init__(self.code)


class EvidenceExpired(RuntimeError):
    code = "evidence_expired"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidInventoryEvidence(ValueError):
    code = "invalid_inventory_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidPolicyEvidence(ValueError):
    code = "invalid_policy_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidEquipmentEvidence(ValueError):
    code = "invalid_equipment_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidMaintenancePolicyEvidence(ValueError):
    code = "invalid_maintenance_policy_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class ReplenishmentQuantityOutOfPolicy(ValueError):
    code = "replenishment_quantity_out_of_policy"

    def __init__(self) -> None:
        super().__init__(self.code)


class TaskRecoveryOutOfPolicy(ValueError):
    code = "task_recovery_out_of_policy"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidTaskEvidence(ValueError):
    code = "invalid_task_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidTaskRecoveryPolicyEvidence(ValueError):
    code = "invalid_task_recovery_policy_evidence"

    def __init__(self) -> None:
        super().__init__(self.code)


class ApprovalExpired(RuntimeError):
    code = "approval_expired"

    def __init__(self) -> None:
        super().__init__(self.code)


class ApprovalSnapshotMismatch(RuntimeError):
    code = "approval_snapshot_mismatch"

    def __init__(self) -> None:
        super().__init__(self.code)


class UnknownTool(RuntimeError):
    code = "unknown_tool"

    def __init__(self) -> None:
        super().__init__(self.code)


class ToolPolicyViolation(RuntimeError):
    code = "tool_policy_violation"

    def __init__(self) -> None:
        super().__init__(self.code)


class ObjectBindingMismatch(RuntimeError):
    code = "object_binding_mismatch"

    def __init__(self) -> None:
        super().__init__(self.code)


class DuplicateToolCall(RuntimeError):
    code = "duplicate_tool_call"

    def __init__(self) -> None:
        super().__init__(self.code)


class ToolBudgetExceeded(RuntimeError):
    code = "tool_budget_exceeded"

    def __init__(self) -> None:
        super().__init__(self.code)


class InvalidAgentToolArguments(ValueError):
    code = "invalid_agent_tool_arguments"

    def __init__(self) -> None:
        super().__init__(self.code)


class WorkOrderNotFound(LookupError):
    code = "work_order_not_found"

    def __init__(self) -> None:
        super().__init__(self.code)


class WorkOrderVerificationFailed(RuntimeError):
    code = "work_order_verification_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class WorkOrderStorageFailed(RuntimeError):
    code = "work_order_storage_failed"

    def __init__(self) -> None:
        super().__init__(self.code)


class DependencyUnavailable(RuntimeError):
    code = "dependency_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


class KnowledgeVersionConflict(RuntimeError):
    code = "knowledge_version_conflict"

    def __init__(self) -> None:
        super().__init__(self.code)


class KnowledgeInsufficient(LookupError):
    code = "knowledge_insufficient"

    def __init__(self) -> None:
        super().__init__(self.code)


class KnowledgeUnavailable(RuntimeError):
    code = "knowledge_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)
