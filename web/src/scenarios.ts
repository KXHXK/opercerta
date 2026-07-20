export type OperationAction = "query" | "create_work_order";

export type ScenarioDefinition = {
  objectType: "inventory" | "equipment" | "task";
  objectId: string;
  label: string;
  message: string;
  action: Extract<OperationAction, "create_work_order">;
  explanation: string;
};

export const operationScenarios: readonly ScenarioDefinition[] = [
  {
    objectType: "inventory",
    objectId: "SKU-LOW-001",
    label: "库存不足 · 补货",
    message: "检查 SKU-LOW-001 并在库存不足时创建补货工单",
    action: "create_work_order",
    explanation: "按可用库存与版本化补货策略计算数量，审批后再次核验库存。"
  },
  {
    objectType: "equipment",
    objectId: "EQ-PUMP-001",
    label: "设备告警 · 维修",
    message: "检查 EQ-PUMP-001 并在告警或心跳异常时创建维修工单",
    action: "create_work_order",
    explanation: "告警严重度和心跳新鲜度决定维修优先级，模型只负责解释。"
  },
  {
    objectType: "task",
    objectId: "TASK-BLOCKED-001",
    label: "作业阻塞 · 恢复",
    message: "检查 TASK-BLOCKED-001 并在阻塞或逾期时创建恢复工单",
    action: "create_work_order",
    explanation: "阻塞状态、宽限期和重试上限共同决定是否允许人工重排。"
  }
];
