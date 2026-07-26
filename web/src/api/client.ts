import type {
  AgentTraceSnapshot,
  ApprovalBinding,
  OperationAccepted,
  OperationDetail,
  OperationalSignal,
  SignalCaseView,
  SignalScanResult
} from "./contracts";
import type { OperationAction, ScenarioDefinition } from "../scenarios";

export type { ApprovalBinding } from "./contracts";

type ErrorEnvelope = {
  code: string;
  message: string;
};

const actionableMessages: Record<string, string> = {
  approval_expired: "审批已过期。请由 operator 创建新的处置后再审批。",
  approval_already_decided: "该处置已完成审批。请读取最新状态，不要重复提交。",
  approval_snapshot_mismatch: "审批依据已变化。请刷新处置并核对新的审批绑定。",
  authentication_required: "演示登录已失效。请切换角色刷新凭据后重试。",
  invalid_access_token: "演示登录已失效。请切换角色刷新凭据后重试。",
  permission_denied: "当前角色无权执行此操作。请切换到流程要求的角色。",
  request_validation_failed: "提交内容不符合受控业务契约。请检查场景、对象与动作。",
  dependency_unavailable: "依赖服务暂时不可用。请检查 API、MCP、PostgreSQL 与 Redis 健康状态。"
};

export class ApiError extends Error {
  readonly userMessage: string;

  constructor(
    readonly status: number,
    readonly code: string
  ) {
    const userMessage =
      actionableMessages[code] ?? `服务返回了无法识别的安全错误响应。（HTTP ${status}）`;
    super(userMessage);
    this.name = "ApiError";
    this.userMessage = userMessage;
  }
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<ErrorEnvelope>;
  return typeof candidate.code === "string" && typeof candidate.message === "string";
}

export function userFacingError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.userMessage : fallback;
}

export async function raiseApiError(response: Response): Promise<never> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // The API contract uses JSON envelopes, but transport/proxy failures may not.
  }
  if (isErrorEnvelope(body)) {
    throw new ApiError(response.status, body.code);
  }
  throw new ApiError(response.status, `http_${response.status}`);
}

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
    if (!response.ok) await raiseApiError(response);
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
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as OperationAccepted;
  }

  async scanSignals(): Promise<SignalScanResult> {
    const response = await fetch(this.endpoint("/api/v1/signals/scan"), {
      method: "POST",
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as SignalScanResult;
  }

  async listSignals(): Promise<OperationalSignal[]> {
    const response = await fetch(this.endpoint("/api/v1/signals"), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as OperationalSignal[];
  }

  async listSignalCases(): Promise<SignalCaseView[]> {
    const response = await fetch(this.endpoint("/api/v1/signal-cases"), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as SignalCaseView[];
  }

  async investigateSignal(signalId: string): Promise<OperationAccepted> {
    const response = await fetch(this.endpoint(`/api/v1/signals/${signalId}/investigate`), {
      method: "POST",
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as OperationAccepted;
  }

  async retrySignal(signalId: string): Promise<OperationAccepted> {
    const response = await fetch(this.endpoint(`/api/v1/signals/${signalId}/retry`), {
      method: "POST",
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as OperationAccepted;
  }

  async getOperation(operationId: string): Promise<OperationDetail> {
    const response = await fetch(this.endpoint(`/api/v1/operations/${operationId}`), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
    return (await response.json()) as OperationDetail;
  }

  async getAgentTrace(operationId: string): Promise<AgentTraceSnapshot> {
    const response = await fetch(this.endpoint(`/api/v1/operations/${operationId}/agent-trace`), {
      headers: { Authorization: this.authorizationHeader() }
    });
    if (!response.ok) await raiseApiError(response);
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
    if (!response.ok) await raiseApiError(response);
  }
}
