export type ApprovalBinding = {
  inventory_evidence_id: string;
  policy_evidence_id: string;
  rule_version: string;
  decision_facts_hash: string;
  plan_hash: string;
  recommended_quantity: number;
};

export class ApiClient {
  constructor(private readonly authorizationHeader: () => string) {}

  async issueToken(
    role: "operator" | "approver" | "auditor" | "demo-admin"
  ): Promise<string> {
    const response = await fetch("/api/v1/auth/demo-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account: role })
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
    const body = (await response.json()) as { access_token: string };
    return body.access_token;
  }

  async submitApproval(
    operationId: string,
    binding: ApprovalBinding,
    decision: "approved" | "rejected"
  ): Promise<void> {
    const response = await fetch(`/api/v1/operations/${operationId}/approval`, {
      method: "POST",
      headers: {
        Authorization: this.authorizationHeader(),
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        decision,
        reason: `演示审批：${decision}`,
        expected_inventory_evidence_id: binding.inventory_evidence_id,
        expected_policy_evidence_id: binding.policy_evidence_id,
        expected_rule_version: binding.rule_version,
        expected_decision_facts_hash: binding.decision_facts_hash,
        expected_plan_hash: binding.plan_hash,
        expected_recommended_quantity: binding.recommended_quantity
      })
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
  }
}
