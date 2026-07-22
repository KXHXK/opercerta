import type {
  AgentTraceSnapshot,
  ApprovalBinding,
  OperationAccepted,
  OperationDetail
} from "./contracts";
import type { OperationAction, ScenarioDefinition } from "../scenarios";

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

  async createOperation(
    scenario: ScenarioDefinition,
    action: OperationAction = scenario.action
  ): Promise<OperationAccepted> {
    const response = await fetch(this.endpoint("/api/v1/operations"), {
      method: "POST",
      headers: {
        Authorization: this.authorizationHeader(),
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: scenario.message,
        requested_action: action,
        object_type: scenario.objectType,
        object_id: scenario.objectId
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

  async getAgentTrace(operationId: string): Promise<AgentTraceSnapshot> {
    const response = await fetch(this.endpoint(`/api/v1/operations/${operationId}/agent-trace`), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
    return (await response.json()) as AgentTraceSnapshot;
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
        expected_binding: binding
      })
    });
    if (!response.ok) throw new Error(`api_status_${response.status}`);
  }
}
