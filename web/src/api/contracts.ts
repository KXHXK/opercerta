export type ApprovalBinding = {
  inventory_evidence_id: string;
  policy_evidence_id: string;
  rule_version: string;
  decision_facts_hash: string;
  plan_hash: string;
  recommended_quantity: number;
};

export type OperationAccepted = {
  operation_id: string;
  status: string;
  created_at: string;
};

export type OperationDetail = {
  operation_id: string;
  status: string;
  request: { message: string };
  evidence: Record<string, unknown>[];
  assessment: Record<string, unknown> | null;
  plan: Record<string, unknown> | null;
  approval_binding: ApprovalBinding | null;
  approval: { decision: "approved" | "rejected"; reason: string } | null;
  work_order: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
  last_audit_sequence: number;
};
