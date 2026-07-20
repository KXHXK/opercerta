import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => window.history.pushState({}, "", "/console"));

it("renders the static showcase at the root without calling fetch", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  window.history.pushState({}, "", "/");

  render(<App />);

  expect(screen.getByRole("heading", { name: "OperCerta" })).toBeInTheDocument();
  expect(screen.getByText(/release gate: CLOSED/i)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("renders the OperCerta console shell", () => {
  render(<App />);

  expect(screen.getByText("OperCerta｜智能运营处置 Agent")).toBeInTheDocument();
  expect(screen.getByText("发布门禁：CLOSED")).toBeInTheDocument();
});

it("renders the controls, facts, approval, and audit areas", () => {
  render(<App />);

  expect(screen.getByRole("article", { name: "操作控制区" })).toBeInTheDocument();
  expect(screen.getByRole("article", { name: "业务事实区" })).toBeInTheDocument();
  expect(screen.getByText("审批与绑定")).toBeInTheDocument();
  expect(screen.getByText("发布门禁保持 CLOSED")).toBeInTheDocument();
});

it("loads a created operation after acquiring an in-memory demo token", async () => {
  const binding = {
    scenario: "inventory" as const,
    subject_evidence_id: "inventory-evidence", policy_evidence_id: "policy-evidence",
    rule_version: "rule-v1", decision_facts_hash: "facts-hash", plan_hash: "plan-hash",
    parameters: { kind: "replenishment" as const, recommended_quantity: 18 }
  };
  const detail = {
    operation_id: "operation-1", status: "awaiting_approval",
    request: { message: "为 SKU-LOW-001 创建库存补货工单", object_type: "inventory", object_id: "SKU-LOW-001" },
    evidence: [], assessment: null, plan: null, approval_binding: binding, approval: null,
    work_order: null, result: null, error: null, last_audit_sequence: 2
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "memory-token" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "operation-1" }), { status: 202 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))
    .mockResolvedValueOnce(new Response("id: 2\nevent: approval_requested\ndata: {}\n\n", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("演示角色"), { target: { value: "operator" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "创建处置" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "创建处置" }));

  expect(await screen.findByText("operation-1")).toBeInTheDocument();
  expect(screen.getAllByText("等待审批")).not.toHaveLength(0);
  expect(fetchMock).toHaveBeenCalledTimes(4);
});
