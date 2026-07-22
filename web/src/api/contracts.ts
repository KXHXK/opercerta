export type ApprovalBinding = {
  scenario: "inventory" | "equipment" | "task";
  subject_evidence_id: string;
  policy_evidence_id: string;
  rule_version: string;
  decision_facts_hash: string;
  plan_hash: string;
  parameters:
    | { kind: "replenishment"; recommended_quantity: number }
    | { kind: "repair"; alert_code: string; priority: "normal" | "high" | "urgent" }
    | { kind: "task_recovery"; recovery_action: "manual_requeue" };
};

export type OperationAccepted = {
  operation_id: string;
  status: string;
  created_at: string;
};

export type WorkOrderSummary = {
  id: string;
  status: string;
  payload: Record<string, unknown>;
};

export type OperationResult = {
  outcome: string;
  work_order_id: string;
};

export type OperationDetail = {
  operation_id: string;
  status: string;
  request: {
    message: string;
    requested_action?: "query" | "create_work_order";
    object_type: "inventory" | "equipment" | "task";
    object_id: string;
  };
  evidence: Record<string, unknown>[];
  assessment: Record<string, unknown> | null;
  plan: Record<string, unknown> | null;
  approval_binding: ApprovalBinding | null;
  approval: { decision: "approved" | "rejected"; reason: string } | null;
  work_order: WorkOrderSummary | null;
  result: OperationResult | null;
  error: { code: string; message: string } | null;
  last_audit_sequence: number;
};

export type TraceValue = null | boolean | number | string | TraceValue[] | {
  [key: string]: TraceValue;
};

export type AgentTraceCitation = {
  id: string;
  event_id: string;
  document_id: string;
  chunk_id: string;
  version: string;
  rank: number;
  score: number;
};

export type AgentTraceEvent = {
  id: string;
  run_id: string;
  sequence: number;
  semantic_key: string;
  event_type: "perception" | "model" | "tool" | "rag" | "rule" | "human" | "execution" | "feedback" | "guardrail";
  actor_type: "user" | "agent" | "model" | "tool" | "policy" | "human" | "system";
  node: string;
  status: "started" | "completed" | "failed" | "blocked" | "waiting";
  safe_input: Record<string, TraceValue>;
  safe_output: Record<string, TraceValue>;
  prompt_ref: string | null;
  tool_ref: string | null;
  error_code: string | null;
  citations: AgentTraceCitation[];
  started_at: string;
  ended_at: string | null;
};

export type AgentTraceSnapshot = {
  run: {
    id: string;
    operation_id: string;
    run_key: string;
    scenario: "inventory" | "equipment" | "task";
    status: "running" | "awaiting_human" | "completed" | "failed";
    model_mode: "mock" | "real";
    initiated_by: string | null;
    next_sequence: number;
    started_at: string;
    ended_at: string | null;
  };
  events: AgentTraceEvent[];
};
