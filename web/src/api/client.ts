import type { ApprovalBinding, OperationAccepted, OperationDetail } from "./contracts";

export type { ApprovalBinding } from "./contracts";

export class ApiClient {
  constructor(
    private readonly authorizationHeader: () => string,
    private readonly apiBaseUrl = ""
  ) {}

  private endpoint(path: string): string {
    return `${this.apiBaseUrl}${path}`;
  }

  async issueToken(
    role: "operator" | "approver" | "auditor" | "demo-admin"
  ): Promise<string> {
    const response = await fetch(this.endpoint("/api/v1/auth/demo-token"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account: role })
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
    const body = (await response.json()) as { access_token: string };
    return body.access_token;
  }

  async createOperation(sku: string): Promise<OperationAccepted> {
    const response = await fetch(this.endpoint("/api/v1/operations"), {
      method: "POST",
      headers: {
        Authorization: this.authorizationHeader(),
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: `为 ${sku} 创建库存补货工单`,
        requested_action: "create_work_order",
        object_type: "inventory",
        object_id: sku
      })
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
    return (await response.json()) as OperationAccepted;
  }

  async getOperation(operationId: string): Promise<OperationDetail> {
    const response = await fetch(this.endpoint(`/api/v1/operations/${operationId}`), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
    return (await response.json()) as OperationDetail;
  }

  async submitApproval(
    operationId: string,
    binding: ApprovalBinding,
    decision: "approved" | "rejected"
  ): Promise<void> {
    const response = await fetch(this.endpoint(`/api/v1/operations/${operationId}/approval`), {
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
