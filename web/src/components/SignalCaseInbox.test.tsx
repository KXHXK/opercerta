import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { OperationalSignal, SignalCaseView } from "../api/contracts";
import { SignalCaseInbox } from "./SignalCaseInbox";

function signal(
  id: string,
  objectType: OperationalSignal["object_type"],
  objectId: string,
  predecessorSignalId: string | null,
  operationId: string
): OperationalSignal {
  const signalType = {
    inventory: "inventory_shortage",
    equipment: "equipment_attention",
    task: "task_blocked"
  } as const;
  return {
    id,
    dedup_key: `dedup-${id}`,
    signal_type: signalType[objectType],
    object_type: objectType,
    object_id: objectId,
    source: "demo_watchlist.v1",
    severity: "medium",
    reason_code: `${objectType}_attention`,
    facts_hash: id.padEnd(64, "a").slice(0, 64),
    facts: {},
    status: "investigating",
    operation_id: operationId,
    predecessor_signal_id: predecessorSignalId,
    detected_at: "2026-07-26T08:00:00Z",
    updated_at: "2026-07-26T08:00:00Z",
    resolved_at: null
  };
}

function signalCase(
  objectType: OperationalSignal["object_type"],
  objectId: string
): SignalCaseView {
  const first = signal(`${objectType}-1`, objectType, objectId, null, `${objectType}-op-1`);
  const current = signal(
    `${objectType}-2`,
    objectType,
    objectId,
    first.id,
    `${objectType}-op-2`
  );
  return {
    case_key: `${objectType}:${objectId}`,
    object_type: objectType,
    object_id: objectId,
    current_signal: current,
    current_operation: { operation_id: `${objectType}-op-2`, status: "awaiting_approval" },
    history_count: 1,
    lineage: [first, current]
  };
}

it("renders six lineage rows as three case cards and expands only the selected history", () => {
  const cases = [
    signalCase("inventory", "SKU-LOW-001"),
    signalCase("equipment", "EQ-PUMP-001"),
    signalCase("task", "TASK-BLOCKED-001")
  ];
  render(
    <SignalCaseInbox
      cases={cases}
      selectedCaseKey={null}
      busyCaseKey={null}
      disabled={false}
      onSelect={vi.fn()}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onOpenOperation={vi.fn()}
    />
  );

  expect(screen.getAllByTestId("signal-case-card")).toHaveLength(3);
  expect(screen.queryByText("inventory-1")).not.toBeInTheDocument();

  const inventoryCard = screen.getAllByTestId("signal-case-card")[0];
  fireEvent.click(within(inventoryCard).getByRole("button", { name: "展开历史（1）" }));

  expect(within(inventoryCard).getByText("inventory-1")).toBeInTheDocument();
  expect(screen.queryByText("equipment-1")).not.toBeInTheDocument();
  expect(screen.queryByText("task-1")).not.toBeInTheDocument();
});

it("opens only the operation belonging to the clicked case", () => {
  const onOpenOperation = vi.fn();
  const cases = [
    signalCase("inventory", "SKU-LOW-001"),
    signalCase("equipment", "EQ-PUMP-001")
  ];
  render(
    <SignalCaseInbox
      cases={cases}
      selectedCaseKey={null}
      busyCaseKey={null}
      disabled={false}
      onSelect={vi.fn()}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onOpenOperation={onOpenOperation}
    />
  );

  const equipmentCard = screen.getAllByTestId("signal-case-card")[1];
  fireEvent.click(within(equipmentCard).getByRole("button", { name: "查看关联处置" }));

  expect(onOpenOperation).toHaveBeenCalledTimes(1);
  expect(onOpenOperation).toHaveBeenCalledWith(
    "equipment:EQ-PUMP-001",
    "equipment-op-2"
  );
});
