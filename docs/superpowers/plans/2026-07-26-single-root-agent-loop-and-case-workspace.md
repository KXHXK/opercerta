# OperCerta 单根 Agent Loop 与业务对象工作台实施计划

> 日期：2026-07-26
> 状态：Task 0–11 本地实施完成，等待 Git/公网发布审批
> 方法：TDD，严格 RED → GREEN → REFACTOR
> 发布门禁：`CLOSED`

## 目标

在不破坏 OperCerta 已验证的 signal、审批、绑定、幂等和恢复内核的前提下，把当前串联多图的实现迁移为一个根 LangGraph 拥有的有界 Agent Loop，并把 React signal 平铺列表迁移为按业务对象聚合的 case 工作台。

## 执行约束

- 本计划只实施 OperCerta；不启动其他项目。
- 每个任务先提交能够证明缺口的 RED 测试，再写最小 GREEN 实现。
- Mock 与 Real Kimi 证据分开；禁止静默回退。
- 不预写测试数量、延迟、准确率或发布日期。
- 不删除旧编排，直到新路径完成三业务、重启和数据库等价验证。
- 未经用户再次授权，不 commit、push、merge 或公开部署。

## Task 0：冻结可靠性基线与迁移护栏

### 目的

记录迁移前可复查基线，避免重构时把现有 signal、审批和工单行为一起改坏。

### 动作

1. 记录 WSL Git 状态、当前提交、未提交文件和运行服务。
2. 运行与 signal 认领、审批竞态、事实绑定、幂等写入、重启恢复相关的定向测试。
3. 记录当前多图调用和重复事实读取的结构证据，作为纠偏前对照。
4. 不执行待审批 operation，不清理用户数据，不创建提交。

### 完成条件

基线命令和实际结果进入开发日志；若可靠性基线自身失败，先排障，不进入 Task 1。

## Task 1：用 RED 固定 Agent 回合与根状态契约

### 先写失败测试

- `AgentTurn` 必须在 `tool_calls` 与 `final_analysis` 二者中选一；
- Tool Call 必须有稳定 `call_id`、白名单工具名、严格参数和用途摘要；
- Observation 必须能作为 ToolMessage/状态返回下一次模型调用；
- 未知工具、写工具、重复 call、非法参数和预算耗尽安全失败；
- Trace 不保存 Chain-of-Thought、完整 Prompt 或敏感原文。

### 最小实现

新增严格 Domain/Model contracts、状态 reducer 和错误码，不接业务写入。

### 完成条件

失败测试先被观测，再由最小实现转绿；现有模型 adapter 测试不回归。

## Task 2：统一只读 Observation Gateway 与 Redis 语义

### 先写失败测试

- MCP 工具结果统一转换为 `Observation`；
- hit/miss/bypass/unavailable 可观察；
- Redis 不可用时旁路权威数据源；
- detection 与批准后 refresh 强制 bypass；
- 同一 graph state 已有新鲜 Observation 时不重复读取；
- RAG 结果含 citation 并可回送模型。

### 最小实现

把缓存放到 MCP read adapter/gateway 的统一入口；Agent 和 Policy 共享已验证 Observation，不改变现有工具协议和数据库事实。

### 完成条件

缓存与 RAG 语义有单元和集成证据，旧的双路径重复读取测试失败后被消除。

## Task 3：库存补货单根 LangGraph 纵向切片

### 先写失败测试

- 一次 operation 只有一个根图、一个 `thread_id`、一条 checkpoint 谱系；
- 模型先选库存工具，看到 Observation 后能再选 RAG 或形成最终分析；
- FastAPI 只传可信结构字段，不预选业务工具；
- 规则节点使用已验证 Observation；
- 查询路径无需审批，行动路径在根图内中断等待审批。

### 最小实现

建立新的根图：`receive_intent → model_decide ↔ execute_read_tools → validate_analysis → policy → approval_interrupt/final_report`。先只挂库存策略，并置于内部 feature flag 后。

### 完成条件

库存调查和待审批 operation 在新图内完成，Trace 可证明真实 Model↔Tool 循环；旧图仍可用于对照。

## Task 4：审批后刷新、Verifier、绑定和幂等写入接入根图

### 先写失败测试

- 批准后从同一 checkpoint 恢复；
- 重新取证绕过缓存并返回模型/Verifier；
- 事实漂移产生新审批周期或安全终止；
- binding 一致后才允许写入；
- 数据库已提交但 checkpoint 未保存时不会重复工单；
- 模型失败不能绕过确定性 Verifier。

### 最小实现

把现有批准后可靠性节点适配到根图状态，保持 Repository 和事务不变量不变。

### 完成条件

库存从 signal 到工单的完整闭环在单根图中通过，数据库后置条件与旧路径一致。

## Task 5：接入设备维修和阻塞任务策略

### 先写失败测试

- 三场景共享相同根图拓扑和审批/恢复节点；
- 场景只决定允许的事实工具、RAG scope、规则和工单 payload；
- 模型不能跨场景调用不相关工具；
- 三场景错误、拒绝和事实漂移均安全收口。

### 最小实现

将现有三个独立生命周期图收缩为策略模块，复用根图和 Observation Gateway。

### 完成条件

三业务在新图上完成调查、审批和受控写入等价验证，无复制的生命周期编排。

## Task 6：业务对象 case projection API

### 先写失败测试

- 多条 predecessor/successor signal 聚合为一个 `case_key`；
- 当前 signal、当前 operation、历史计数和 lineage 顺序正确；
- scan 只返回本次扫描事实与受影响 case；
- operator/approver/auditor 读取权限符合现有 RBAC；
- 原始 `/signals` 兼容接口仍可用于审计。

### 最小实现

新增 `SignalCaseView` 查询投影和 `GET /api/v1/signal-cases`，不复制业务事实，不做破坏性迁移。

### 完成条件

API 能稳定表达“一对象一主 case + 可展开历史”，不要求前端自行拼 lineage。

## Task 7：React case 工作台

### 先写失败测试

- 六条 lineage 行渲染为三个主卡片；
- 选择一张卡片只更新该 case 的详情；
- loading/error 按 case/action 隔离；
- 切换角色不触发扫描或覆盖选择；
- 首次登录可以点击真实扫描；
- 展开历史才显示 predecessor/successor；
- Trace 明确显示 Model、Tool、Observation、Policy、HITL、Verifier 和 Write 各阶段。

### 最小实现

引入 `selectedCaseKey`、`selectedOperationId` 和局部 action state；替换平铺 inbox，但保留现有视觉系统中可复用的颜色、响应式布局和无固定遮挡约束。

### 完成条件

组件测试、TypeScript、production build 和真实浏览器操作均通过；点击卡片无串扰和增殖。

## Task 8：新旧路径等价对照并移除旧编排

### 动作

1. 对同一冻结事实分别运行旧路径和新路径。
2. 比对 policy facts、approval binding、work-order payload、终态和审计不变量。
3. 对差异逐项判断是缺陷还是已批准语义变化。
4. 仅在三业务等价和恢复门禁通过后，删除 Python 多图包装器和旧编译图入口。

### 完成条件

产品运行时只剩一个根 LangGraph；没有隐藏 fallback 或第二套生命周期。

## Task 9：完整 Mock、数据库和 Compose 重启门禁

### 动作

- 运行后端单元、数据库集成、前端、静态检查和安全门禁；
- 在 Mock Compose 中跑三业务；
- 在模型决策后、工具后、审批中断、写入后进行重启恢复；
- 核对 signal、operation、approval、work order、trace 和 checkpoint 数据库事实；
- 记录实际命令、测试数量、耗时和限制。

### 完成条件

所有适用门禁真实通过；任何失败不得被“历史曾通过”替代。

## Task 10：Real Kimi 代表性验证

### 动作

1. 在 strict real mode 运行三业务各一次调查。
2. 证明每次 Tool Observation 确实回送模型。
3. 运行至少一次批准后的代表性完整写入和写后读。
4. 核对 native Tool Calling 或结构化兼容模式标签。
5. 注入 provider 失败，确认不回退 Mock、不产生写入。

### 完成条件

真实结果进入独立证据文档；若失败则如实记录，发布门禁保持 `CLOSED`。

## Task 11：交付、学习材料与审批点

### 动作

- 更新核心技术手册，按真实代码逐节点解释单根图、ToolLoop、MCP、Redis、RAG、PostgreSQL 和恢复；
- 更新手动实验手册、面试讲解、架构图和故障案例；
- 更新 `current-state.md`、每日开发日志和根文档索引；
- 生成实施证据，但只记录实际通过项；
- 做敏感信息扫描和 diff review。

### 停止点

在 commit/push/merge/部署前向用户报告范围、门禁、未完成边界和拟提交文件，等待明确授权。

## 推荐执行顺序

`Task 0 → 1 → 2 → 3 → 4 → 用户检查库存纵向切片 → 5 → 6 → 7 → 用户检查三业务工作台 → 8 → 9 → 10 → 11`

两个用户检查点只要求理解业务和体验是否正确；代码级细节仍完整记录到本地文档，不要求用户在看不懂代码时盲目批准技术实现。

## 2026-07-26 实施进度

### Task 0：完成

- 分支确认为 `feat/agent-core-implementation`，回滚提交为 `d49577b`；已有 signal/UI 未提交修改完整保留。
- Compose 的 API、MCP、PostgreSQL、Redis 和 Caddy 均在运行，API/MCP/PostgreSQL/Redis 健康检查通过。
- 可靠性定向单元测试 `71 passed`。
- 使用自动清理的一次性 pgvector/PostgreSQL 运行审批竞态、事实绑定、工单幂等、signal 仓储和重启恢复，结果 `43 passed`，未触碰演示数据库。

### Task 1：完成 RED → GREEN

- RED：新增回合契约测试后，因 `AgentTurn`、`ToolDecision`、`FinalAnalysis` 不存在而在收集阶段失败。
- GREEN：新增严格互斥联合契约、带用途的 Agent Tool Call、Final Analysis、confidence band，以及 Harness 累计模型/工具预算校验。
- 安全边界：写工具和未知工具仍由既有 `ToolPolicy` 拒绝；Final Analysis 禁止额外的 `reasoning_content`、`chain_of_thought` 和 `full_prompt`。
- 定向测试 `33 passed`，Ruff 与 Mypy 通过。

### Task 2：完成 RED → GREEN

- RED：新增 Observation Gateway 测试后，因缺少 `ReadToolResult` 和统一缓存网关而在收集阶段失败。
- GREEN：新增统一 `CachedReadToolGateway`；模型可见的库存、设备、任务、规则和知识检索均经过 cache-aside，并把 `hit/miss/bypass/unavailable` 投影到 `ToolObservation`。
- Agent 和旧场景的库存/设备/任务及规则读取共享同一缓存键；批准后刷新可使用 `bypass_cache=True` 强制读取权威事实。
- Redis get 失败标为 `unavailable` 并安全旁路；不改变事实和规则结论。
- 相关单元与静态范围 `76 passed`，Ruff 与 Mypy 通过；一次性 PostgreSQL 上 Agent 图、RAG 和 Agent 重启恢复 `11 passed`。
- 完整单元套件在显式使用仓库既定 `PYTHONPATH=.:src` 后为 `386 passed`；全项目 Ruff 和 Mypy 81 个源文件通过，`git diff --check` 通过。
- 首次完整单元命令没有设置工作树根导入路径，6 个 `scripts.*` 测试在收集阶段失败；同时 PowerShell 后续命令曾掩盖 WSL 非零退出码。复跑改用 `set -euo pipefail`，把该次结果排除，不冒充测试通过。

### 当前边界

- 尚未建立单根 LangGraph；现有多图编排仍是运行默认路径。
- 新 `AgentTurn` 和 Observation Gateway 是 Task 3 根图的可靠契约底座，不应被描述为纠偏已经全部完成。
- 未调用 Real Kimi，未 commit/push/merge，发布门禁保持 `CLOSED`。

### Task 3：完成 RED → GREEN

- RED：新增库存根图测试后，因 `AgentDecisionContext` 和根图构建器不存在而在收集阶段失败。
- GREEN：新增 `AgentLoopModelGateway.encode_goal/decide` 协议和库存 `InventoryAgentRootGraph`。模型每轮收到当前工具定义与全部结构化 Observation，只能返回 `ToolDecision` 或 `FinalAnalysis`。
- 查询用例中模型依次看到 0、1、2 条 Observation，按顺序选择库存快照、规则约束，再形成最终分析；实际记录为目标编码加三次决策、两次工具调用。
- `FinalAnalysis` 在缺少库存或规则证据、引用不匹配或声明仍缺证据时安全失败；写工具无法进入 `AgentTurn` Schema。
- 确定性 `ScenarioRegistry` 继续计算库存规则和计划；查询路径直接完成，创建路径在同一个根图进入 LangGraph 原生 `approval_interrupt`。
- 根图候选默认关闭，必须显式 `enabled=True` 才能构建，尚未接入默认 API 或 Compose。
- Memory checkpoint 和一次性 PostgreSQL checkpointer 均证明创建路径停在同一 `thread_id`；PostgreSQL 定向结果 `6 passed` 并自动清理。
- 包含旧 Agent 调查图的完整回归为 `398 passed`；全项目 Ruff、Mypy 82 个源文件和 `git diff --check` 通过。

### Task 3 后的边界

- 根图目前只覆盖库存调查、确定性规则与审批中断，不处理审批提交后的恢复、重新取证、Verifier、绑定和工单写入。
- 默认运行仍是旧 `ControlledActionGraph` 多图路径；Task 4 门禁通过前不会切换。
- 下一步为 Task 4，把现有可靠性节点适配到同一根状态和 checkpoint 谱系。

### Task 4：完成 RED → GREEN

- RED：真实 PostgreSQL/MCP 用例最初因根图缺少 operation/action runtime 参数失败；补齐最小接口后，又先后真实触发证据 TTL 过期和刷新证据 ID 变化门禁。测试没有通过放宽断言转绿。
- GREEN：`AgentLoopModelGateway` 增加批准后 `verify`；同一根图从原生 `approval_interrupt` 恢复后，强制绕过缓存重新读取库存与规则，把新鲜事实返回 Verifier，再由确定性 binding 比较决定执行、二次审批或安全终止。
- binding 比较忽略每次读取必然更新的 evidence ID，只比较场景、规则版本、决策事实哈希、计划哈希和受控参数；事实不变时允许执行，数量变化时进入新的审批周期。
- 拒绝路径不写工单；模型 Verifier 异常时 operation 失败关闭；所有失败状态均经条件边转入 `mark_failed`，不能继续误入写节点。
- 工单仍由 PostgreSQL `create_or_get` 保证幂等。测试先在 checkpoint 仍停留于审批中断时预写同一工单，再恢复根图，结果 `replayed=True`、工单 ID 不变且只有一条 `work_order_created` 事件。
- 一次性 pgvector/PostgreSQL 的根图文件为 `11 passed`（其中新增批准完成、拒绝、事实漂移二次审批、checkpoint 间隙幂等回放和模型故障关闭）；完整单元套件 `386 passed`；全项目 Ruff、Mypy 81 个源文件与 `git diff --check` 通过。

### Task 4 后的边界

- 库存 operation 从 Agent ToolLoop、Policy、HITL、批准后刷新、Verifier 到幂等写后读已在候选单根图闭环，但 signal/API/Compose 默认路径尚未切换。
- 当前文件名仍为 `inventory_agent_root_graph.py`，设备和任务尚未复用该拓扑；Task 5 将先写三场景共享拓扑和跨场景工具拒绝测试，再做场景策略泛化。
- 未调用 Real Kimi，未 commit/push/merge，未公开部署；发布门禁继续 `CLOSED`。

### Task 5：完成 RED → GREEN

- RED：新增设备/任务共享根图测试后，因缺少 `build_controlled_agent_root_graph` 和通用初始状态构建器而在导入阶段失败，证明当前导出仍是库存专用。
- GREEN：保留同一份 StateGraph 拓扑，新增通用入口；场景策略只负责触发语义、允许的事实工具、证据/评估/计划解析、审批 binding 和工单 payload。库存旧入口仅作为兼容 wrapper，不新增第二套生命周期。
- `ToolPolicy` 按 GoalEncoding 限定场景工具和对象参数；设备目标尝试调用库存工具时以 `tool_policy_violation` 失败关闭。
- 设备与任务均真实通过 `Model → subject MCP tool → Observation → Model → policy MCP tool → Observation → Model → deterministic Policy → HITL → refresh/Verifier → write/readback`。
- 三业务批准、拒绝和事实漂移共用相同审批与恢复节点；设备与任务的事实漂移均进入新的 `approval_interrupt`，不产生工单。
- 新旧根图定向文件在一次性 pgvector/PostgreSQL + 本地 MCP 上合计 `20 passed`；完整单元 `386 passed`；全项目 Ruff、Mypy 82 个源文件与 `git diff --check` 通过。

### Task 5 后的边界

- 三业务候选根图已完成调查、审批和受控写入等价闭环，但默认 API/Compose 尚未切换，旧三图仍保留到 Task 8 等价门禁。
- 根图实现文件暂仍沿用历史名 `inventory_agent_root_graph.py`，公开通用入口名称已不含 inventory；最终清理时再做无行为变化的文件重命名，避免本轮同时扩大 diff。
- 下一步执行 Task 6：把多条 predecessor/successor signal 和 operation 投影成按业务对象聚合的 case API。

### Task 6：完成 RED → GREEN

- RED：新增 API 用例后，`GET /api/v1/signal-cases` 返回 404；原始 `/api/v1/signals` 同时保持 200，证明缺口只在 case 投影。
- GREEN：新增只读 `SignalCaseView`，按 `(object_type, object_id)` 从现有 signal 和 operation 表实时聚合，不新增事实表、不复制数据、不做破坏性迁移。
- case 返回稳定 `case_key`、当前 signal、当前 operation/status、历史计数和按 predecessor → successor 排列的 lineage；当前卡片优先选择最新活动 signal。
- `GET /api/v1/signal-cases` 对 operator、approver、auditor 和 demo-admin 开放；原始 `/signals` 保留为行级审计兼容接口。
- `/signals/scan` 新增 `affected_cases`，只投影本次 scan 返回 signal 对应的业务对象，不把数据库中其他 case 混入本次扫描结果。
- 一次性 PostgreSQL 上 signal API 文件 `4 passed`；目标 Ruff/Mypy 通过。完整后端门禁留到 Task 9 统一执行。

### Task 6 后的边界

- 后端已经能稳定表达“一业务对象一主 case + 可展开历史”；现有 React 仍读取平铺 `/signals`，尚未消费新投影。
- 下一步 Task 7 将先用组件失败测试固定三张主卡、局部选择/加载/错误状态和展开 lineage，再切换前端数据源。

### 2026-07-26 Task 7 实施结果

- RED：`SignalCaseInbox` 导入缺失；实现后固定六条 signal 只显示三张业务主卡，展开历史和打开处置均只影响被点击 case。
- React 已消费 `/signal-cases` 与 scan 的 `affected_cases`，选择、busy、错误和 lineage 展开均按 `case_key` 隔离；保留旧 API 回退只用于滚动升级兼容。
- 浏览器真实验证先观察到三张主卡且只有任务卡展开历史；随后发现聚合把有终态 successor 的可操作 ancestor 当作 current，导致无效重试。仓储投影已修正为始终选择 lineage 叶节点，并补终态叶节点回归。
- 前端门禁为 19 个文件、`60 passed`，生产构建成功；signal API 为 `5 passed`，目标 Ruff/Mypy 通过。浏览器在 API 镜像重建后的最终 reload 被本地 URL 安全策略阻止，因此不把该次未执行的 reload 写成已通过证据。
- 下一步 Task 8：对照新旧运行路径的业务终态、审计、审批、工单和恢复语义；等价门禁通过后才切换默认 API/Compose 并移除旧编排入口。

### 2026-07-26 Task 8–11 实施结果

- **Task 8：** 生产入口现在只构造一个 `ControlledAgentRootGraph`，由 `ControlledAgentRootRunner` 与 `ControlledAgentRootRecoveryCoordinator` 负责首次运行和恢复。三业务新旧路径等价测试同时核对 assessment、计划哈希、审批绑定、工单 payload、终态和审计事件，结果 `3 passed`；生产 lifespan `2 passed`。旧图模块暂保留给历史回归和等价测试，产品运行时没有隐藏 fallback。
- **Task 9：** 后端单元 `392 passed`，完整集成 `260 passed`；前端 19 个文件 `60 passed` 且 production build 成功；Ruff、format check、Mypy（85 个源文件）通过。隔离 Compose 项目完成三业务、RAG 引用、数据库断言、API/MCP 重启及 recovery-only 验证，不修改原演示卷。
- **Task 10：** 在隔离 Compose 中以 Moonshot `kimi-k2.6` 完成三业务各一次只读代表调用、库存一次批准写入和一次无效 provider fail-closed 验证。修复了模型与 MCP 共用 2 秒 timeout、Kimi 强制工具调用与 thinking mode 不兼容、最终分析和 Verifier structured output 波动三类真实兼容问题。真实路径没有回退 Mock；证据分文件保存且不包含密钥或模型原始推理。
- **Task 11：** 核心技术手册、手动实验手册、面试讲解、事故复盘、实施证据、current-state、handoff、每日开发日志和根目录文档索引已收口。生产 IAM、公网可写 HTTPS 后端、限流/备份、自动发布、Release Tag 仍未完成。
- **最终复验：** 完整单元 `395 passed`，受影响隔离 pgvector/PostgreSQL 集成 `32 passed`，Ruff、213 文件 format check、Mypy 85 个源文件和仓库安全通过；同步 worktree 当日日志后根目录文档索引核对 544 份 Markdown、零漏项。

### 本计划完成边界

Task 0–11 的本地实现与证据收口完成，并不等于生产上线。未经用户授权不 commit、push、merge 或公开部署；生产发布门禁继续为 `CLOSED`，也不启动 ForenTrail。
