export type ScenarioFact = {
  key: "inventory" | "equipment" | "task";
  label: string;
  trigger: string;
  statusTool: string;
  policySummary: string;
  workOrderKind: "replenishment" | "repair" | "task_recovery";
  accent: "teal" | "amber" | "violet";
};

export const PROJECT_FACTS = {
  businessLoops: 3,
  frozenEvaluations: 42,
  realModelPaths: 9,
  backendTests: 682,
  frontendTests: 60,
  agentSafetyEvaluations: 9,
  promptInjectionPasses: 3,
  endToEndP50Seconds: 19.722,
  endToEndP95Seconds: 31.333,
  realModelProvider: "Moonshot AI",
  realModelName: "kimi-k2.6",
  releaseGate: "CLOSED",
} as const;

export const MCP_TOOLS = [
  "inventory.get_snapshot",
  "equipment.get_status",
  "task.get_status",
  "policy.list_constraints",
  "work_order.create",
  "work_order.get",
] as const;

export const SCENARIOS: readonly ScenarioFact[] = [
  {
    key: "inventory",
    label: "库存不足 → 补货",
    trigger: "可用库存低于补货点",
    statusTool: "inventory.get_snapshot",
    policySummary: "目标差额受最小/最大订货量约束",
    workOrderKind: "replenishment",
    accent: "teal",
  },
  {
    key: "equipment",
    label: "设备告警 → 维修",
    trigger: "心跳过期、设备状态或允许告警触发",
    statusTool: "equipment.get_status",
    policySummary: "维护规则映射优先级",
    workOrderKind: "repair",
    accent: "amber",
  },
  {
    key: "task",
    label: "作业阻塞 → 恢复",
    trigger: "blocked/overdue 与重试次数触发",
    statusTool: "task.get_status",
    policySummary: "恢复策略约束动作",
    workOrderKind: "task_recovery",
    accent: "violet",
  },
] as const;

export const PUBLIC_LIMITATIONS = [
  "生产 IAM/SSO",
  "公开可写 HTTPS 后端",
  "限流、防滥用与高可用",
] as const;

export function sourceHref(path: string): string {
  return `https://github.com/KXHXK/opercerta/blob/main/${path}`;
}
