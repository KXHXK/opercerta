import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { OperationalSignal } from "../api/contracts";
import { SignalInbox } from "./SignalInbox";

const signal: OperationalSignal = {
  id: "signal-1",
  dedup_key: "signal:v1:inventory_shortage:SKU-LOW-001:facts",
  signal_type: "inventory_shortage",
  object_type: "inventory",
  object_id: "SKU-LOW-001",
  source: "demo_watchlist.v1",
  severity: "medium",
  reason_code: "inventory_below_reorder_point",
  facts_hash: "a".repeat(64),
  facts: { available_quantity: 12, reorder_point: 15 },
  status: "open",
  operation_id: null,
  predecessor_signal_id: null,
  detected_at: "2026-07-25T10:00:00Z",
  updated_at: "2026-07-25T10:00:00Z",
  resolved_at: null
};

it("explains why no action is available before anomaly detection", () => {
  render(
    <SignalInbox
      signals={[]}
      disabled={false}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onOpenOperation={vi.fn()}
    />
  );

  expect(screen.getByText(/先运行一次受控扫描/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "启动 Agent 调查" })).not.toBeInTheDocument();
});

it("starts investigation from a detected business signal", () => {
  const investigate = vi.fn();
  render(
    <SignalInbox
      signals={[signal]}
      disabled={false}
      onInvestigate={investigate}
      onRetry={vi.fn()}
      onOpenOperation={vi.fn()}
    />
  );

  expect(screen.getByText("库存短缺")).toBeInTheDocument();
  expect(screen.getByText("SKU-LOW-001")).toBeInTheDocument();
  expect(screen.getByText(/可用库存 12 < 补货点 15/)).toBeInTheDocument();
  expect(screen.getByText(/MCP 实时取证/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "启动 Agent 调查" }));
  expect(investigate).toHaveBeenCalledWith(signal);
});

it("starts a successor investigation without overwriting an attention signal", () => {
  const retry = vi.fn();
  const attention = {
    ...signal,
    status: "attention_required" as const,
    operation_id: "expired-operation"
  };
  render(
    <SignalInbox
      signals={[attention]}
      disabled={false}
      onInvestigate={vi.fn()}
      onRetry={retry}
      onOpenOperation={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "重新调查" }));
  expect(retry).toHaveBeenCalledWith(attention);
  expect(screen.getByText(/新的处置会重新读取 MCP 事实/)).toBeInTheDocument();
});
