import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => window.history.pushState({}, "", "/console"));

const inventorySignal = {
  id: "signal-1",
  dedup_key: `signal:v1:inventory_shortage:SKU-LOW-001:${"a".repeat(64)}`,
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

const attentionSignal = {
  ...inventorySignal,
  status: "attention_required",
  operation_id: "expired-operation"
};

const successorSignal = {
  ...inventorySignal,
  id: "signal-2",
  dedup_key: "signal:retry:v1:signal-1",
  status: "investigating",
  operation_id: "new-operation",
  predecessor_signal_id: "signal-1"
};

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

it("refreshes active lineage after scanning so an existing successor is not retried", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: "memory-token" }), { status: 200 })
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({
        signals: [attentionSignal], issues: [], scanned_count: 3,
        scanned_at: "2026-07-25T10:00:00Z"
      }), { status: 200 })
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify([attentionSignal, successorSignal]), { status: 200 })
    );
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "扫描业务异常" }));

  expect(await screen.findAllByTestId("signal-case-card")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "展开历史（1）" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重新调查" })).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(3);
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
    .mockResolvedValueOnce(new Response(JSON.stringify({
      signals: [inventorySignal], issues: [], scanned_count: 3,
      scanned_at: "2026-07-25T10:00:00Z"
    }), { status: 200 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify([inventorySignal]), { status: 200 })
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ operation_id: "operation-1" }), { status: 202 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ ...inventorySignal, status: "investigating", operation_id: "operation-1" }]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(trace), { status: 200 }))
    .mockResolvedValueOnce(new Response("id: 2\nevent: approval_requested\ndata: {}\n\n", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  expect(screen.getByRole("button", { name: "扫描业务异常" })).toBeEnabled();
  expect(screen.queryByText("SKU-LOW-001")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "扫描业务异常" }));
  const investigate = await screen.findByRole("button", { name: "启动 Agent 调查" });
  fireEvent.click(investigate);

  expect(await screen.findByText("operation-1")).toBeInTheDocument();
  expect(screen.getAllByText("等待审批")).not.toHaveLength(0);
  expect(screen.getAllByText("建议补货并提交人工审批").length).toBeGreaterThan(0);
  expect(fetchMock).toHaveBeenCalledTimes(8);
});

it("shows an actionable safe error when a controlled request is rejected", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: "memory-token" }), { status: 200 })
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({
      signals: [inventorySignal], issues: [], scanned_count: 3,
      scanned_at: "2026-07-25T10:00:00Z"
    }), { status: 200 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify([inventorySignal]), { status: 200 })
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          code: "request_validation_failed",
          message: "请求内容无效。"
        }),
        { status: 422, headers: { "content-type": "application/json" } }
      )
    );
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "扫描业务异常" }));
  fireEvent.click(await screen.findByRole("button", { name: "启动 Agent 调查" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "提交内容不符合受控业务契约。请检查场景、对象与动作。"
  );
});

it("keeps an accepted approval final when the post-write refresh is forbidden", async () => {
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
    events: []
  };
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "memory-token" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(detail), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(trace), { status: 200 }))
    .mockResolvedValueOnce(new Response("id: 2\nevent: approval_requested\ndata: {}\n\n", { status: 200 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ code: "permission_denied", message: "无权读取处置。" }), {
        status: 403,
        headers: { "content-type": "application/json" }
      })
    );
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);
  fireEvent.change(screen.getByLabelText("演示角色"), { target: { value: "approver" } });
  fireEvent.change(screen.getByLabelText("处置编号"), { target: { value: "operation-1" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "读取处置" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "读取处置" }));
  const approve = await screen.findByRole("button", { name: "批准" });

  fireEvent.click(approve);

  expect(await screen.findByRole("status")).toHaveTextContent(
    "审批已提交，但未能读取最新处置"
  );
  await waitFor(() => expect(approve).toBeDisabled());
  expect(screen.queryByText("审批未提交，请读取最新处置状态后重试。")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(6);
});
