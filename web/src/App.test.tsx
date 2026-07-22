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

  expect(
    screen.getByRole("heading", { name: "可审批、可恢复的运营工单 Agent" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/生产门禁.*CLOSED/)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("renders the engineering walkthrough only on local development", () => {
  window.history.pushState({}, "", "/engineering");

  render(<App development hostname="localhost" />);

  expect(screen.getByRole("heading", { name: "OperCerta 工程拆解" })).toBeInTheDocument();
});

it("does not expose the engineering walkthrough on the public host", () => {
  window.history.pushState({}, "", "/engineering");

  render(<App development={false} hostname="opercerta-kxh.netlify.app" />);

  expect(screen.getByRole("heading", { name: "页面不存在" })).toBeInTheDocument();
  expect(screen.queryByText("掌握检查")).not.toBeInTheDocument();
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
  expect(screen.getByRole("region", { name: "Agent Trace" })).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "下一角色引导" })).toBeInTheDocument();
  expect(screen.getByText("发布门禁保持 CLOSED")).toBeInTheDocument();
  expect(screen.queryByPlaceholderText(/自由输入|聊天/)).not.toBeInTheDocument();
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
  const trace = {
    run: {
      id: "run-1", operation_id: "operation-1", run_key: "primary", scenario: "inventory",
      status: "awaiting_human", model_mode: "mock", initiated_by: "demo.operator",
      next_sequence: 1, started_at: "2026-07-22T09:00:00Z", ended_at: null
    },
    events: [{
      id: "event-1", run_id: "run-1", sequence: 1, semantic_key: "model:analysis",
      event_type: "model", actor_type: "model", node: "analyze_observations", status: "completed",
      safe_input: {}, safe_output: { recommendation: "建议补货并提交人工审批" },
      prompt_ref: "observation_analyst:v1", tool_ref: null, error_code: null, citations: [],
      started_at: "2026-07-22T09:00:00Z", ended_at: "2026-07-22T09:00:00Z"
    }]
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "memory-token" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "operation-1" }), { status: 202 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(trace), { status: 200 }))
    .mockResolvedValueOnce(new Response("id: 2\nevent: approval_requested\ndata: {}\n\n", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("演示角色"), { target: { value: "operator" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "创建处置" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "创建处置" }));

  expect(await screen.findByText("operation-1")).toBeInTheDocument();
  expect(screen.getAllByText("等待审批")).not.toHaveLength(0);
  expect(screen.getAllByText("建议补货并提交人工审批").length).toBeGreaterThan(0);
  expect(fetchMock).toHaveBeenCalledTimes(5);
});
