import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { AgentTraceSnapshot, OperationDetail } from "../api/contracts";
import { AgentTrace } from "./AgentTrace";
import { DecisionComparison } from "./DecisionComparison";
import { EvidenceAndCitations } from "./EvidenceAndCitations";
import { IntentCard } from "./IntentCard";
import { NextRoleGuide } from "./NextRoleGuide";

const detail: OperationDetail = {
  operation_id: "operation-1",
  status: "awaiting_approval",
  request: {
    message: "检查 SKU-LOW-001 并在库存不足时创建补货工单",
    object_type: "inventory",
    object_id: "SKU-LOW-001"
  },
  evidence: [],
  assessment: { shortage: true, available: 4 },
  plan: { kind: "replenishment", recommended_quantity: 18 },
  approval_binding: null,
  approval: null,
  work_order: null,
  result: null,
  error: null,
  last_audit_sequence: 4
};

const trace: AgentTraceSnapshot = {
  run: {
    id: "run-1",
    operation_id: "operation-1",
    run_key: "primary",
    scenario: "inventory",
    status: "awaiting_human",
    model_mode: "mock",
    initiated_by: "demo.operator",
    next_sequence: 4,
    started_at: "2026-07-22T09:00:00Z",
    ended_at: "2026-07-22T09:00:01Z"
  },
  events: [
    {
      id: "event-1", run_id: "run-1", sequence: 1,
      semantic_key: "perception:intent", event_type: "perception", actor_type: "user",
      node: "intent_envelope", status: "completed",
      safe_input: { object_id: "SKU-LOW-001" },
      safe_output: { objective: "核验库存并申请补货" },
      prompt_ref: null, tool_ref: null, error_code: null, citations: [],
      started_at: "2026-07-22T09:00:00Z", ended_at: "2026-07-22T09:00:00Z"
    },
    {
      id: "event-2", run_id: "run-1", sequence: 2,
      semantic_key: "model:analysis", event_type: "model", actor_type: "model",
      node: "analyze_observations", status: "completed", safe_input: {},
      safe_output: { recommendation: "建议补货并提交人工审批", citation_count: 1 },
      prompt_ref: "observation_analyst:v1", tool_ref: null, error_code: null, citations: [],
      started_at: "2026-07-22T09:00:00Z", ended_at: "2026-07-22T09:00:00Z"
    },
    {
      id: "event-3", run_id: "run-1", sequence: 3,
      semantic_key: "observation:tool-1", event_type: "tool", actor_type: "tool",
      node: "execute_read_tools", status: "completed", safe_input: {},
      safe_output: { safe_summary: "可用库存 4，低于补货点 10。" },
      prompt_ref: null, tool_ref: "inventory.get_snapshot", error_code: null, citations: [],
      started_at: "2026-07-22T09:00:00Z", ended_at: "2026-07-22T09:00:00Z"
    },
    {
      id: "event-4", run_id: "run-1", sequence: 4,
      semantic_key: "observation:rag-1", event_type: "rag", actor_type: "tool",
      node: "execute_read_tools", status: "completed", safe_input: {},
      safe_output: { safe_summary: "已匹配库存补货 SOP。" },
      prompt_ref: null, tool_ref: "knowledge.search_sop", error_code: null,
      citations: [{
        id: "citation-1", event_id: "event-4", document_id: "document-1",
        chunk_id: "chunk-1", version: "1.0.0", rank: 1, score: 0.91
      }],
      started_at: "2026-07-22T09:00:00Z", ended_at: "2026-07-22T09:00:00Z"
    }
  ]
};

it("presents a constrained intent and structured goal without a chat box", () => {
  render(<IntentCard detail={detail} trace={trace} />);

  expect(screen.getByText("结构化 Goal")).toBeInTheDocument();
  expect(screen.getByText("检查 SKU-LOW-001 并在库存不足时创建补货工单"))
    .toBeInTheDocument();
  expect(screen.queryByPlaceholderText(/自由输入|聊天/)).not.toBeInTheDocument();
});

it("renders ordered backend Agent Trace events instead of audit events", () => {
  render(<AgentTrace trace={trace} />);

  expect(screen.getByText("01")).toBeInTheDocument();
  expect(screen.getByText("感知")).toBeInTheDocument();
  expect(screen.getByText("模型分析")).toBeInTheDocument();
  expect(screen.getByText("MCP 工具")).toBeInTheDocument();
  expect(screen.getByText("SOP 检索")).toBeInTheDocument();
  expect(screen.getByText("observation_analyst:v1")).toBeInTheDocument();
});

it("shows safe tool observations and citation references", () => {
  render(<EvidenceAndCitations trace={trace} />);

  expect(screen.getByText("inventory.get_snapshot")).toBeInTheDocument();
  expect(screen.getByText("可用库存 4，低于补货点 10。")).toBeInTheDocument();
  expect(screen.getByText(/document-1.*chunk-1/)).toBeInTheDocument();
  expect(screen.getByText((_, element) => element?.textContent === "v1.0.0 · 91.0%"))
    .toBeInTheDocument();
});

it("separates model recommendation from deterministic execution plan", () => {
  render(<DecisionComparison detail={detail} trace={trace} />);

  expect(screen.getByText("模型建议")).toBeInTheDocument();
  expect(screen.getByText("建议补货并提交人工审批")).toBeInTheDocument();
  expect(screen.getByText("确定性执行计划")).toBeInTheDocument();
  expect(screen.getByText(/recommended_quantity.*18/)).toBeInTheDocument();
});

it("guides the active role through approval and audit handoff", () => {
  const { rerender } = render(
    <NextRoleGuide role="operator" status="awaiting_approval" hasWorkOrder={false} />
  );
  expect(screen.getByText(/切换为 approver/)).toBeInTheDocument();

  rerender(<NextRoleGuide role="approver" status="completed" hasWorkOrder />);
  expect(screen.getByText(/切换为 auditor/)).toBeInTheDocument();
});
