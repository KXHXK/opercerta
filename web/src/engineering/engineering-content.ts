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

export type IncidentFact = {
  id: string;
  title: string;
  observation: string;
  rootCause: string;
  fix: string;
  verification: string;
  limitation: string;
  interviewLine: string;
};

export const INCIDENTS: readonly IncidentFact[] = [
  {
    id: "wsl-component-source",
    title: "WSL2 功能启用后被 Windows 回滚",
    observation: "DISM 显示启用成功，但重启提示功能未完成并撤销；组件修复最初返回 0x800f081f。",
    rootCause:
      "Windows 组件存储损坏，原始 LTSC 2021 ISO 的版本又低于主机 19044.5011，不能充当匹配修复源。",
    fix: "挂载版本与内部构建均为 19044.5011 的 LTSC 源，依次完成 DISM RestoreHealth、SFC 修复，再重新启用 WSL 与虚拟机平台。",
    verification:
      "DISM CheckHealth 无损坏、SFC 无完整性冲突，Ubuntu 在 WSL2 初始化，Docker 显示 WSL2 内核与 cgroup v2。",
    limitation: "这是本机开发环境修复，不是应用部署能力；匹配安装源也必须验证来源与哈希。",
    interviewLine:
      "我先区分功能开关失败和组件源不匹配，用同构建源修复系统，再验证 WSL2 与容器运行时，而不是反复执行安装命令。",
  },
  {
    id: "postgres-secret-traceback",
    title: "PostgreSQL 密码进入 traceback",
    observation: "数据库连接失败的异常文本曾包含测试角色密码。",
    rootCause: "含密码的完整 DSN 被底层异常格式化；仓库未提交并不意味着旧凭据仍然安全。",
    fix: "立即轮换数据库角色密码，并改用无密码 DSN、临时 PGPASSWORD、SecretStr 与安全错误映射。",
    verification: "以不回显方式重新连接，checkpointer 与完整回归通过，Git 跟踪文件不含新值。",
    limitation: "应用层脱敏不能替代终端历史、日志平台与主机权限治理。",
    interviewLine:
      "我把事故拆成旧秘密处置和未来泄露面治理：前者靠轮换，后者靠连接与错误边界重构。",
  },
  {
    id: "fastmcp-host-421",
    title: "FastMCP readiness 正常但业务调用 421",
    observation: "MCP 健康检查为 200，API 的真实 Streamable HTTP 调用却返回 dependency_unavailable。",
    rootCause: "DNS rebinding 防护拒绝 Compose 服务名 Host: mcp:8001；loopback 健康检查没有覆盖业务 Host。",
    fix: "先添加真实会话 RED 测试，再为监听地址、loopback 与 mcp[:8001] 配置最小 allowed-hosts 白名单。",
    verification: "MCP 集成回归与 Compose 的创建、审批、工单、审计闭环通过。",
    limitation: "部署域名或服务拓扑变化时必须重新审查 Host 白名单。",
    interviewLine:
      "readiness 只证明服务在线，不证明业务协议路径可用，所以我把服务发现 Host 纳入集成契约。",
  },
  {
    id: "failed-test-data-leak",
    title: "失败测试污染共享集成库",
    observation: "恢复测试捞到六条旧 operation，预期空结果变成多条恢复记录。",
    rootCause:
      "测试 harness 只在收到 HTTP 202 后登记清理 ID；503 之前数据库已落行，清理列表却没有记录。",
    fix: "确认目标为专用测试库后精确清理，并在 repository 创建成功时立即追踪 operation ID。",
    verification: "API/恢复聚焦测试与完整后端回归通过，开发和演示数据库未被清理。",
    limitation: "共享集成库仍要求测试数据命名、所有权与 finally 清理契约。",
    interviewLine:
      "业务失败也可能留下合法持久化痕迹；测试清理必须绑定数据库创建时刻，不能依赖最终 HTTP 响应。",
  },
  {
    id: "stale-compose-image",
    title: "旧 Compose 镜像制造指标矛盾",
    observation: "业务请求成功且 Redis hit 正常，但新增 MCP 调用指标始终为零。",
    rootCause: "Compose 复用了含缓存指标但不含新 MCP 指标的旧镜像，源码、镜像与实例版本不一致。",
    fix: "让验证脚本强制 docker compose up --build -d，并用资产测试锁定重建行为。",
    verification: "禁用缓存时每场景 10 次 MCP；启用时 2 次 MCP 加 8 次 hit，60/60 终态 completed。",
    limitation: "本地重建不等于生产镜像供应链；线上还需不可变 digest 与 commit 关联。",
    interviewLine:
      "我没有因 HTTP 成功接受矛盾指标，而是沿源码、镜像、实例版本链证明运行物过期。",
  },
  {
    id: "time-derived-approval-hash",
    title: "时间派生字段破坏审批哈希",
    observation: "设备事实和规则未变，只因创建与批准跨过一秒就出现 approval_snapshot_mismatch。",
    rootCause: "decision_facts_hash 纳入每秒变化的 heartbeat_age_seconds，而它只是展示派生值。",
    fix: "以 RED 测试固定 60/61 秒分类不变时哈希稳定，并改为绑定 source version、heartbeat、severity、state、stale 分类等稳定事实。",
    verification: "维护、设备工作流、重启、API 回归和三业务 release Compose 通过。",
    limitation: "跨过 stale 阈值会改变分类和哈希，这是应有的安全行为。",
    interviewLine: "审批哈希绑定可审计决策事实，不绑定每次读取都变化的 UI 展示值。",
  },
  {
    id: "caddy-route-order",
    title: "Caddy 路由顺序与故障响应边界",
    observation: "API 容器 readiness 为 200，但经 Caddy 得到 React HTML；重启窗口还可能返回空正文 502。",
    rootCause: "SPA catch-all 吞掉 API 路径，且诊断器错误假设代理错误也一定符合应用 JSON envelope。",
    fix: "用互斥 handle @api 与静态 handle 固定优先级；readiness 轮询容忍暂态非 JSON，业务终态仍严格校验。",
    verification:
      "caddy fmt、validate、资产测试和一键重启恢复 smoke 通过，内部 metrics/MCP/数据库未暴露。",
    limitation: "本地 HTTP 验证不包含真实域名 DNS、自动 HTTPS 与公网入站端口。",
    interviewLine:
      "我比较代理前后响应类型，把路由错误和业务错误分层；只放宽启动窗口解析，不放宽业务完成条件。",
  },
  {
    id: "kimi-compatibility",
    title: "OpenAI-compatible 不等于参数完全兼容",
    observation:
      "模型列表与认证有效，但 Kimi K2.6 首次 chat 请求仍返回 400；默认 thinking 又让严格 JSON content 为空。",
    rootCause: "适配器强制 temperature=0，且未显式处理供应商 thinking 扩展和响应位置。",
    fix: "不再强制 temperature，增加显式 thinking 配置并关闭该模式，只接受 summary/rationale 两字段。",
    verification: "三业务各一条真实模型写路径与唯一工单通过，随后 Mock release Compose 再次通过。",
    limitation: "只证明当前供应商与模型的代表性兼容，其他兼容服务仍需契约测试。",
    interviewLine:
      "兼容协议复用 endpoint 和消息形状，不代表采样参数、扩展字段和响应位置相同。",
  },
  {
    id: "layered-timeout-inversion",
    title: "外层 10 秒早于内层 30 秒超时",
    observation: "模型服务端预算为 30 秒，验证客户端却在 10 秒先断开。",
    rootCause: "只调了 adapter timeout，没有审查浏览器、验证器、反向代理与服务端的完整 deadline 链。",
    fix: "将验证客户端 timeout 做成 1–120 秒有界配置，并用 75 秒包住模型 30 秒预算；重试最多两次。",
    verification: "三业务六个代表 operation 完成，报告只记录实测总时长与请求范围，不把单样本当 SLA。",
    limitation: "端到端时间包含网络、编排和存储，不等于供应商纯模型延迟。",
    interviewLine:
      "外层 deadline 必须覆盖内层最坏预算，否则内层的安全错误处理没有机会返回。",
  },
  {
    id: "compose-credential-rotation",
    title: "本地 Compose 配置误回显后立即轮换",
    observation: "一次本地诊断命令误回显被忽略配置中的数据库连接行；模型密钥未回显。",
    rootCause: "诊断方式输出整行配置，依赖事后替换来脱敏，泄露边界不可靠。",
    fix: "把该数据库凭据视为已暴露，同步轮换密码与连接 URL，后续只输出 SET/UNSET、长度或布尔一致性。",
    verification: "以不回显方式确认配置一致，代码、Git 与证据文档不保存旧值或新值。",
    limitation: "删除消息或日志不能证明秘密恢复安全；还要按外部系统留存策略处理。",
    interviewLine:
      "秘密进入可持久化输出后不能靠撤回，我会先轮换，再把诊断接口改成只暴露状态。",
  },
];

export const MASTERY_ITEMS = [
  ["explain-flow", "不看稿画出完整请求链路并说明三业务差异"],
  ["run-business", "亲手完成 query、创建、审批和终态查看"],
  ["diagnose-failure", "制造 MCP 故障或事实变化并解释为什么零工单"],
  ["change-rule", "按 TDD 修改一条合成规则并解释影响范围"],
] as const;
