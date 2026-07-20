export type EngineeringStep = {
  id: string;
  title: string;
  purpose: string;
  source: readonly string[];
  inputOutput: string;
  databaseEffect: string;
  failureBehavior: string;
  evidence: string;
  interviewPrompt: string;
};

export const ENGINEERING_STEPS: readonly EngineeringStep[] = [
  {
    id: "react-request",
    title: "React 选择场景、角色和动作",
    purpose: "把使用意图约束为三种对象和 query/create_work_order 两种动作。",
    source: ["web/src/components/OperationControls.tsx", "web/src/scenarios.ts"],
    inputOutput: "ScenarioDefinition + OperationAction → POST /api/v1/operations",
    databaseEffect: "无；浏览器不直接接触数据库。",
    failureBehavior: "身份或 API 不可用时显示固定安全提示，不伪造结果。",
    evidence: "web/src/components/OperationControls.test.tsx",
    interviewPrompt: "为什么前端不能提交 approver identity？",
  },
  {
    id: "api-boundary",
    title: "FastAPI JWT/RBAC 与严格输入",
    purpose: "在 HTTP 边界拒绝非法对象、动作和伪造身份。",
    source: ["src/opercerta/api/app.py", "src/opercerta/api/auth.py"],
    inputOutput: "OperationRequest + JWT → OperationAccepted 或固定 ErrorResponse",
    databaseEffect: "非法输入不创建 operation。",
    failureBehavior: "422/401/403 使用安全 envelope，不返回 traceback。",
    evidence: "tests/integration/api/test_operations_api.py",
    interviewPrompt: "Pydantic 校验与业务规则校验为什么分层？",
  },
  {
    id: "operation-create",
    title: "PostgreSQL 建立 Operation 与审计",
    purpose: "在执行图之前建立可查询、可恢复的业务事实。",
    source: [
      "src/opercerta/application/operation_runner.py",
      "src/opercerta/infrastructure/db/operation_repository.py",
    ],
    inputOutput: "Validated request → operation UUID + operation_created event",
    databaseEffect: "插入 operation 与有序审计记录。",
    failureBehavior: "事务失败时不返回虚假 accepted。",
    evidence: "tests/integration/db/test_operation_state_repository.py",
    interviewPrompt: "为什么不能只依赖 LangGraph checkpoint？",
  },
  {
    id: "graph-dispatch",
    title: "LangGraph 三场景分派",
    purpose: "共享可靠性入口，同时保持三业务证据和计划类型隔离。",
    source: [
      "src/opercerta/workflow/controlled_action_graph.py",
      "src/opercerta/application/scenario_registry.py",
    ],
    inputOutput: "Operation state → inventory/equipment/task graph",
    databaseEffect: "保存图状态和节点审计。",
    failureBehavior: "未知场景安全失败，不自由选择工具。",
    evidence: "tests/integration/workflow/test_controlled_action_graph.py",
    interviewPrompt: "为什么没有使用开放式 ReAct 自由路由？",
  },
  {
    id: "evidence-tools",
    title: "Redis 与六个 MCP 工具取证",
    purpose: "用协议边界读取状态、规则和工单；缓存仅优化初次只读证据。",
    source: [
      "src/opercerta/infrastructure/cache.py",
      "src/opercerta/infrastructure/mcp_gateway.py",
      "src/opercerta/tools/server.py",
    ],
    inputOutput: "Typed tool arguments → validated evidence models",
    databaseEffect: "证据快照写入 evidence 表；Redis 不是事实源。",
    failureBehavior: "缓存错误旁路 MCP；未知工具被 allowlist 拒绝。",
    evidence: "tests/integration/mcp/test_gateway.py",
    interviewPrompt: "为什么批准后必须绕过 Redis？",
  },
  {
    id: "assessment-model",
    title: "确定性评估与受限模型解释",
    purpose: "代码决定动作参数，Kimi 只解释 summary/rationale。",
    source: [
      "src/opercerta/domain/replenishment.py",
      "src/opercerta/domain/maintenance.py",
      "src/opercerta/domain/task_recovery.py",
      "src/opercerta/infrastructure/model_gateway.py",
    ],
    inputOutput: "Evidence bundle → assessment + typed plan + optional explanation",
    databaseEffect: "保存 assessment/plan；query 在此 completed。",
    failureBehavior: "真实模型失败不回退 Mock 后继续写。",
    evidence: "tests/unit/infrastructure/test_model_gateway.py",
    interviewPrompt: "哪些字段永远不能由模型决定？",
  },
  {
    id: "interrupt-binding",
    title: "审批绑定、Checkpoint 与 Interrupt",
    purpose: "把批准对象绑定到证据、规则、事实和计划。",
    source: [
      "src/opercerta/domain/approvals.py",
      "src/opercerta/workflow/controlled_action_graph.py",
    ],
    inputOutput: "Plan → ApprovalBinding + awaiting_approval",
    databaseEffect: "保存 binding、状态和 LangGraph checkpoint。",
    failureBehavior: "缺少 checkpoint 或业务状态不一致时不猜测成功。",
    evidence: "tests/integration/workflow/test_restart_recovery.py",
    interviewPrompt: "审批为什么不能只是 approved=true？",
  },
  {
    id: "atomic-approval",
    title: "PostgreSQL 行锁原子审批",
    purpose: "让并发批准或拒绝只有一个数据库胜者。",
    source: ["src/opercerta/infrastructure/db/approval_repository.py"],
    inputOutput: "BoundApprovalCommand → stored decision or conflict",
    databaseEffect: "同一事务锁 operation、插入一条 approval、追加审计。",
    failureBehavior: "其余竞态请求返回稳定 409。",
    evidence: "tests/integration/db/test_approval_race.py",
    interviewPrompt: "为什么 Python Lock 不能代替数据库锁？",
  },
  {
    id: "revalidate-resume",
    title: "恢复后无缓存复核",
    purpose: "批准后重新读取真实事实并比较 binding。",
    source: [
      "src/opercerta/workflow/controlled_action_recovery.py",
      "src/opercerta/workflow/recovery_coordinator.py",
    ],
    inputOutput: "Checkpoint + fresh MCP evidence → continue or snapshot mismatch",
    databaseEffect: "保存 refresh evidence；不覆盖原批准计划。",
    failureBehavior: "任何关键哈希变化都零工单失败。",
    evidence: "tests/integration/workflow/test_restart_recovery.py",
    interviewPrompt: "为什么审批后还要重新取证？",
  },
  {
    id: "idempotent-write",
    title: "幂等工单、写后读、终态审计与 SSE",
    purpose: "把可能重放的图节点约束为一张有效业务工单。",
    source: [
      "src/opercerta/infrastructure/db/work_order_repository.py",
      "src/opercerta/tools/server.py",
      "src/opercerta/api/app.py",
    ],
    inputOutput: "Typed work-order command → unique work order + completed result",
    databaseEffect: "唯一键写入工单，读取验证后原子保存终态审计。",
    failureBehavior: "相同 idempotency key 返回同一工单；冲突 payload 安全失败。",
    evidence: "tests/integration/db/test_work_order_idempotency.py",
    interviewPrompt: "为什么只能称 effectively-once，而不是端到端 exactly-once？",
  },
];

export type TechnologyFact = {
  name: string;
  responsibility: string;
  verifiedEffect: string;
};

export const TECHNOLOGIES: readonly TechnologyFact[] = [
  {
    name: "React",
    responsibility: "场景、角色、详情、审批和审计 UI",
    verifiedEffect: "三业务同页、公开页零 API、移动布局",
  },
  {
    name: "FastAPI",
    responsibility: "HTTP、JWT/RBAC、严格输入、错误 envelope 与 lifespan",
    verifiedEffect: "非法输入零 operation，调用者不能伪造审批身份",
  },
  {
    name: "LangGraph",
    responsibility: "状态机、interrupt、checkpoint 与恢复",
    verifiedEffect: "API/MCP 重启后仍保持等待审批并继续执行",
  },
  {
    name: "FastMCP",
    responsibility: "六个白名单工具与结构化协议边界",
    verifiedEffect: "独立服务、输入输出双向校验、写后读",
  },
  {
    name: "PostgreSQL",
    responsibility: "业务真相、行锁、唯一约束和有序审计",
    verifiedEffect: "审批竞态一个胜者，一个 operation 最多一张工单",
  },
  {
    name: "Redis",
    responsibility: "初次取证和 query 的短 TTL 只读缓存",
    verifiedEffect: "缓存失败旁路，批准后复核强制绕过缓存",
  },
  {
    name: "Kimi K2.6",
    responsibility: "只生成受限的 summary/rationale 解释字段",
    verifiedEffect: "三业务 3 条真实模型写路径，无权决定动作参数",
  },
  {
    name: "Docker Compose",
    responsibility: "PostgreSQL、Redis、bootstrap、MCP、API 与 Caddy 的本地编排",
    verifiedEffect: "只暴露 Caddy，服务重启后恢复业务",
  },
  {
    name: "OpenTelemetry",
    responsibility: "关联 API、Graph、MCP、Redis 与 SQL 观测跨度",
    verifiedEffect: "属性 allowlist，不记录 token、Prompt 或 SQL 参数",
  },
  {
    name: "GitHub Actions",
    responsibility: "锁文件、静态质量、测试与 Compose 远程门禁",
    verifiedEffect: "PR 快速检查与 main release smoke 分层",
  },
];
