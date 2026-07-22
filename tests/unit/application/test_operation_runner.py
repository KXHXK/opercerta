from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from opercerta.application.approval_expiry import ApprovalExpiryService
from opercerta.application.operation_runner import OperationRunner
from opercerta.domain.contracts import OperationRequest
from opercerta.domain.replenishment import OperationError
from opercerta.infrastructure.db.approval_repository import ApprovalRepository
from opercerta.infrastructure.db.operation_repository import OperationRepository
from opercerta.workflow.controlled_action_graph import ControlledActionGraph
from opercerta.workflow.controlled_action_recovery import ControlledActionRecoveryCoordinator

NOW = datetime(2026, 7, 23, 0, 0, tzinfo=UTC)


class FailingGraph:
    async def ainvoke(self, value: object, config: object) -> None:
        del value, config
        raise RuntimeError("provider response must not be persisted")


class RecordingOperations:
    def __init__(self, *, fail_transition: bool = False) -> None:
        self.operation_id = uuid4()
        self.failures: list[tuple[UUID, OperationError]] = []
        self.fail_transition = fail_transition

    async def create(self, request: OperationRequest) -> UUID:
        del request
        return self.operation_id

    async def mark_failed(self, operation_id: UUID, error: OperationError) -> None:
        if self.fail_transition:
            raise RuntimeError("database transition unavailable")
        self.failures.append((operation_id, error))


@pytest.mark.asyncio
async def test_start_marks_created_operation_failed_when_graph_dependency_raises() -> None:
    operations = RecordingOperations()
    runner = OperationRunner(
        cast(ControlledActionGraph, FailingGraph()),
        cast(ApprovalRepository, object()),
        cast(OperationRepository, operations),
        cast(ControlledActionRecoveryCoordinator, object()),
        cast(ApprovalExpiryService, object()),
        lambda: NOW,
    )
    request = OperationRequest(
        message="核对低库存对象",
        requested_action="query",
        object_type="inventory",
        object_id="SKU-LOW-001",
    )

    with pytest.raises(RuntimeError, match="provider response"):
        await runner.start(request)

    assert operations.failures == [
        (
            operations.operation_id,
            OperationError(
                code="dependency_unavailable",
                message="Operation dependency failed before the workflow reached a safe state.",
            ),
        )
    ]
    assert "provider response" not in operations.failures[0][1].model_dump_json()


@pytest.mark.asyncio
async def test_start_preserves_original_dependency_error_if_failure_transition_also_fails() -> None:
    operations = RecordingOperations(fail_transition=True)
    runner = OperationRunner(
        cast(ControlledActionGraph, FailingGraph()),
        cast(ApprovalRepository, object()),
        cast(OperationRepository, operations),
        cast(ControlledActionRecoveryCoordinator, object()),
        cast(ApprovalExpiryService, object()),
        lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="provider response"):
        await runner.start(
            OperationRequest(
                message="核对低库存对象",
                requested_action="query",
                object_type="inventory",
                object_id="SKU-LOW-001",
            )
        )
