from datetime import UTC, datetime
from uuid import UUID

import pytest

from opercerta.application.controlled_agent_root_runner import ControlledAgentRootRunner
from opercerta.domain.contracts import OperationRequest

NOW = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
OPERATION_ID = UUID("81000000-0000-4000-8000-000000000026")


class FakeGraph:
    def __init__(self) -> None:
        self.invocations: list[tuple[object, object]] = []

    async def ainvoke(self, value: object, config: object) -> dict[str, object]:
        self.invocations.append((value, config))
        assert isinstance(value, dict)
        return {**value, "status": "awaiting_approval"}


class FakeOperations:
    async def create(self, request: OperationRequest) -> UUID:
        self.request = request
        return OPERATION_ID

    async def mark_failed(self, operation_id: UUID, error: object) -> None:
        raise AssertionError((operation_id, error))


class Unused:
    pass


@pytest.mark.asyncio
async def test_start_invokes_the_single_root_with_operation_as_thread_id() -> None:
    graph = FakeGraph()
    runner = ControlledAgentRootRunner(
        graph=graph,  # type: ignore[arg-type]
        approvals=Unused(),  # type: ignore[arg-type]
        operations=FakeOperations(),  # type: ignore[arg-type]
        recovery=Unused(),  # type: ignore[arg-type]
        expiry=Unused(),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )
    request = OperationRequest(
        message="调查已检测的库存异常",
        requested_action="create_work_order",
        object_type="inventory",
        object_id="SKU-LOW-001",
    )

    assert await runner.start(request) == OPERATION_ID
    state, config = graph.invocations[0]
    assert isinstance(state, dict)
    assert state["operation_id"] == str(OPERATION_ID)
    assert state["intent"]["scenario"] == "inventory"  # type: ignore[index]
    assert config == {"configurable": {"thread_id": str(OPERATION_ID)}}
