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
