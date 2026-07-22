# OperCerta Agent 核心架构增强实施计划

> **执行约束：** 实施时必须使用 `superpowers:test-driven-development`，按任务 Inline Execution；除非用户另行要求，不启用 subagent。每个行为先观察 RED，再写最小 GREEN，再重构和提交。

**Goal:** 在不回退 OperCerta 三业务审批、竞态、幂等和重启恢复语义的前提下，把当前“固定工作流 + 模型说明文字”增强为真实、受控、可恢复的单 Agent Plan-and-Execute 闭环，并交付 Tool Calling、Prompt/Harness、Memory/RAG、Agent Trace、React 工作台和可复查证据。

**Architecture:** LangGraph 独占状态、条件边、有界循环、HITL 和恢复；`langchain-core`/`langchain-openai` 只承担消息、Tool Schema、结构化输出和 Kimi OpenAI-compatible 模型适配，不使用 `langchain.create_agent`。模型只能提出只读调查和建议，确定性 Policy Guard 计算业务事实，写工具只能在有效审批、批准后重新取证、Verifier `proceed` 和 binding 一致后由执行节点调用。RAG 在主 Agent 闭环通过后接入，只提供合成 SOP/确认案例引用，不替代 SQL/MCP 精确事实。

**Tech Stack:** Python 3.12、Pydantic v2、LangGraph、LangChain Core/OpenAI integration、FastAPI、FastMCP/MCP、PostgreSQL 18 + pgvector、FastEmbed、Redis、OpenTelemetry、React 19/TypeScript/Vite、Docker Compose、GitHub Actions。

## 0. 依赖核验基线（2026-07-21）

| 依赖 | 当前/计划版本 | 处理 |
| --- | --- | --- |
| `langgraph` | `1.2.9` | 当前已固定，PyPI 当前稳定版；不升级 |
| `mcp` | `1.28.1` | 当前已固定，2.0 仍为 prerelease；不升级 |
| `langchain-core` | `1.4.9` | 当前由 LangGraph 间接使用；改为直接固定依赖 |
| `langchain-openai` | `1.3.5` | Kimi 契约探针通过后加入直接依赖 |
| `pgvector` Python | `0.5.0` | RAG 任务加入 |
| `fastembed` | `0.8.0` | RAG 任务加入；本地中文模型使用 `BAAI/bge-small-zh-v1.5` |
| pgvector server image | `pgvector/pgvector:0.8.2-pg18-trixie` | 替换 Compose 中的普通 PostgreSQL 18 image，先验证数据迁移和健康检查 |

官方核验入口：

- <https://pypi.org/project/langgraph/>
- <https://pypi.org/project/mcp/>
- <https://pypi.org/project/langchain-core/>
- <https://pypi.org/project/langchain-openai/>
- <https://pypi.org/project/pgvector/>
- <https://pypi.org/project/fastembed/>
- <https://github.com/pgvector/pgvector>
- <https://qdrant.github.io/fastembed/examples/Supported_Models/>

版本加入时只运行带精确 `==` 约束的 `uv add package==version`，检查 lock diff，禁止顺带升级无关依赖。真实模型和 embedding 的 provider/model/version 必须写入运行证据，不把 Mock 结果当真实质量。

当前 WSL2 预检显示 `uv` 尚未安装。Task 1 开始前先按用户既定方式手动安装与 CI 一致的固定版本并验证；若手动失败，再由 Codex 协助自动安装：

```bash
curl -LsSf https://astral.sh/uv/0.11.28/install.sh | sh
source "$HOME/.local/bin/env"
uv --version
uv sync --frozen --all-groups
```

安装脚本来源：<https://docs.astral.sh/uv/getting-started/installation/>。安装工具不等于修改项目依赖，仍需保留 `pyproject.toml`/`uv.lock` 审查。

## 1. 全局不变量

- 只实施 OperCerta；本计划完成并通过门禁前不启动 ForenTrail。
- 三业务固定为库存补货、设备维修、作业异常恢复；输入来自有限表单，不增加自由聊天。
- 全部业务事实、SOP、案例、编号和截图从零合成，不复用旧公司材料。
- LangGraph 是唯一 Agent/Workflow 编排运行时；不得调用 `langchain.create_agent`。
- 模型不得决定权威数量、风险、优先级、阈值、权限、审批要求或写入参数。
- Planner 看不到 `work_order.create`；任意 Shell、SQL、Python、动态工具和未知 MCP server 一律拒绝。
- 批准前只读重新规划最多一次；批准后只能 `proceed | abort | escalate`。
- 新动作、新参数、新对象或 binding 不一致必须进入 `needs_reapproval`，零工单。
- 写入仍保持“节点至少一次，业务效果有效一次”，不宣称 exactly-once。
- RAG 只返回 SOP/确认案例和引用；精确业务事实始终来自 SQL/MCP。
- 不记录或展示 Chain-of-Thought、完整 Prompt、密钥、JWT、原始敏感工具正文或 traceback。
- 不预写新的通过数、时延、Token、费用、准确率或上线状态；只在真实运行后记录。
- 当前产品发布门禁保持 `CLOSED`，直到原公开交互、IAM/SSO、安全和发布条件另行满足。

## 2. 目标文件结构

| 路径 | 责任 |
| --- | --- |
| `src/opercerta/domain/agent.py` | Goal、计划、Tool Call、Observation、Analysis、Verifier、Report 严格契约 |
| `src/opercerta/agent/harness.py` | 上下文、预算、输出校验、失败关闭和调用协调 |
| `src/opercerta/agent/prompt_registry.py` | Prompt ID、版本、hash 和加载 |
| `src/opercerta/agent/tool_policy.py` | 节点级工具白名单、对象绑定和读写风险 |
| `src/opercerta/agent/tool_executor.py` | 经 ToolPolicy 验证后调用 MCP 并形成 Observation |
| `src/opercerta/prompts/*.md` | planner/analyst/verifier/reporter 版本化 Prompt |
| `src/opercerta/infrastructure/langchain_model_gateway.py` | LangChain Core/OpenAI-compatible Kimi adapter |
| `src/opercerta/workflow/agent_controlled_action_graph.py` | 三业务共享有界 Agent 图 |
| `src/opercerta/domain/knowledge.py` | 文档、chunk、citation、检索结果契约 |
| `src/opercerta/infrastructure/embedding_gateway.py` | Mock 与 FastEmbed 中文 embedding port/adapter |
| `src/opercerta/infrastructure/db/knowledge_repository.py` | pgvector 入库、过滤、检索和版本失效 |
| `src/opercerta/domain/agent_trace.py` | 安全产品 Trace 契约 |
| `src/opercerta/infrastructure/db/agent_trace_repository.py` | run/event 原子序列和恢复去重 |
| `migrations/versions/0005_agent_knowledge.py` | vector extension、knowledge document/chunk |
| `migrations/versions/0006_agent_trace.py` | Agent run/trace/citation 表 |
| `data/knowledge/*.md`、`manifest.json` | 三业务合成 SOP 与版本清单 |
| `data/evals/opercerta-agent-v1.json` | 透明的预期 Agent 轨迹与负例 |
| `web/src/agent/*` | 意图、Trace、证据引用、决策对比、下一角色 UI |

---

## Task 1: Agent 领域契约、Prompt Registry 与 Harness 骨架

**Files:**

- Create: `src/opercerta/agent/__init__.py`
- Create: `src/opercerta/domain/agent.py`
- Create: `src/opercerta/agent/prompt_registry.py`
- Create: `src/opercerta/agent/harness.py`
- Create: `src/opercerta/prompts/planner-v1.md`
- Create: `src/opercerta/prompts/analyst-v1.md`
- Create: `src/opercerta/prompts/verifier-v1.md`
- Create: `src/opercerta/prompts/reporter-v1.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/unit/domain/test_agent_contracts.py`
- Test: `tests/unit/agent/test_prompt_registry.py`
- Test: `tests/unit/agent/test_harness.py`
- Test: `tests/unit/runtime/test_agent_dependencies.py`

- [x] **Step 1: 写非法契约和依赖边界 RED 测试**

```python
def test_planner_cannot_propose_write_tool() -> None:
    with pytest.raises(ValidationError):
        InvestigationPlan.model_validate({
            "goal": valid_goal(),
            "steps": [{"tool_name": "work_order.create", "arguments": {}}],
            "replan_count": 0,
        })

def test_verifier_rejects_changed_action() -> None:
    with pytest.raises(ValidationError):
        VerificationDecision.model_validate({
            "decision": "proceed",
            "replacement_parameters": {"quantity": 99},
            "reason": "changed",
        })
```

同时断言：未知字段、对象漂移、超过一次 replan、空 Prompt、Prompt hash 不一致、Token/工具/超时预算为零全部失败；`pyproject.toml` 有直接 `langchain-core==1.4.9`，没有顶层 `langchain`。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/unit/domain/test_agent_contracts.py tests/unit/agent tests/unit/runtime/test_agent_dependencies.py -q
```

Expected: collection succeeds but fails because Agent contracts/registry/harness do not exist。

- [x] **Step 3: 加入最小严格契约和 Prompt Registry**

核心类型至少包括 `IntentEnvelope`、`GoalEncoding`、`InvestigationStep`、`InvestigationPlan`、`ToolCallProposal`、`ToolObservation`、`KnowledgeCitation`、`AgentAnalysis`、`DecisionPlan`、`VerificationDecision`、`FinalReport`、`AgentBudget`。全部 `extra="forbid"`、类型严格、JSON 可序列化；可信 `scenario/object/action` 从请求覆盖，不能接受模型改写。

Prompt Registry 返回 `(prompt_id, version, sha256, content)`，但 Trace 只保存 ID/version/hash，不保存完整内容。

- [x] **Step 4: 固定直接依赖并运行 GREEN**

```bash
uv add langchain-core==1.4.9
uv run pytest tests/unit/domain/test_agent_contracts.py tests/unit/agent tests/unit/runtime/test_agent_dependencies.py -q
uv run ruff check src tests
uv run mypy src
```

- [x] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock src/opercerta/agent src/opercerta/domain/agent.py src/opercerta/prompts tests/unit/agent tests/unit/domain/test_agent_contracts.py tests/unit/runtime/test_agent_dependencies.py
git commit -m "feat: add strict agent contracts and harness"
```

## Task 2: Kimi Tool Calling 契约探针与 LangChain 模型适配

**Files:**

- Modify: `src/opercerta/domain/agent.py`
- Modify: `src/opercerta/domain/model_gateway.py`
- Create: `src/opercerta/infrastructure/langchain_model_gateway.py`
- Create: `scripts/probe_kimi_tool_call.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/unit/infrastructure/test_langchain_model_gateway.py`
- Test: `tests/unit/runtime/test_kimi_tool_probe.py`
- Test: `tests/unit/runtime/test_agent_dependencies.py`

- [x] **Step 1: 写 Tool Call、结构化输出和故障 RED 测试**

覆盖：合法只读 `tool_calls`、未知函数、非法/空模型响应、provider-safe wire name、结构化 Goal/Analysis/Verifier/Report、Real 失败绝不切换 Mock、原生 Tool Calling 不兼容时显式返回 `structured_plan` 模式，以及 CLI 错误脱敏。多轮 tool result 由固定真实只读探针验证；429/5xx 有限重试与 401/403 不重试由 Task 4 的 Harness/Graph runtime 统一负责，adapter 自身固定 `max_retries=0`，避免形成两套不可审计重试预算。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/unit/infrastructure/test_langchain_model_gateway.py tests/unit/runtime/test_kimi_tool_probe.py tests/unit/infrastructure/test_model_gateway.py -q
```

- [x] **Step 3: 实现 Gateway port 和 LangChain adapter**

`AgentModelGateway` 暴露：

```python
class AgentModelGateway(Protocol):
    async def encode_goal(self, context: GoalContext) -> GoalEncoding: ...
    async def plan(self, context: PlanningContext) -> InvestigationPlan: ...
    async def analyze(self, context: AnalysisContext) -> AgentAnalysis: ...
    async def verify(self, context: VerificationContext) -> VerificationDecision: ...
    async def report(self, context: ReportingContext) -> FinalReport: ...
```

使用 `ChatOpenAI(base_url=..., model=..., api_key=...)` 的 LangChain adapter；工具和结构化输出经 Pydantic 二次验证。保留现有 gateway 作为迁移兼容层，直到新图完全接管。

实现修订：领域工具 ID 保留 `inventory.get_snapshot` 等点号命名，模型 wire protocol 使用 Moonshot 可接受的 `inventory_get_snapshot` 等下划线名，并在 Gateway 边界双向映射；数据库 bootstrap 仍只负责数据库依赖，模型运行时装配延后到 Task 4，避免把无关职责塞入 bootstrap。

- [x] **Step 4: 固定依赖、运行 GREEN 和真实只读探针**

```bash
uv add langchain-openai==1.3.5
uv run pytest tests/unit/infrastructure/test_langchain_model_gateway.py tests/unit/runtime/test_kimi_tool_probe.py tests/unit/infrastructure/test_model_gateway.py -q
uv run python scripts/probe_kimi_tool_call.py --dry-run
```

在已授权且密钥只存在环境变量时，另运行一次真实固定只读 probe；输出只保留 provider/model、模式、函数名、Schema 状态、耗时和错误分类，不输出密钥、Prompt、原始响应或虚构 Token。

- [x] **Step 5: 提交**

```bash
git add pyproject.toml uv.lock src/opercerta/domain/agent.py src/opercerta/domain/model_gateway.py src/opercerta/infrastructure/langchain_model_gateway.py scripts/probe_kimi_tool_call.py tests/unit/infrastructure/test_langchain_model_gateway.py tests/unit/runtime/test_kimi_tool_probe.py tests/unit/runtime/test_agent_dependencies.py docs/superpowers/plans/2026-07-21-opercerta-agent-core-architecture.md docs/development-log/daily/2026-07-21.md
git commit -m "feat: add bounded Kimi tool calling adapter"
```

## Task 3: ToolPolicy、只读 MCP Tool Loop 与有界重规划

**Files:**

- Create: `src/opercerta/agent/tool_policy.py`
- Create: `src/opercerta/agent/tool_executor.py`
- Modify: `src/opercerta/infrastructure/mcp_gateway.py`
- Modify: `src/opercerta/domain/errors.py`
- Test: `tests/unit/agent/test_tool_policy.py`
- Test: `tests/unit/agent/test_tool_executor.py`
- Test: `tests/integration/mcp/test_gateway.py`
- Preserve/regress: `tests/integration/mcp/test_tool_server.py`

- [x] **Step 1: 写越权、对象漂移和预算 RED 测试**

```python
@pytest.mark.parametrize("tool", ["work_order.create", "shell.exec", "sql.query"])
def test_planner_tool_policy_blocks_write_and_unknown_tools(tool: str) -> None:
    with pytest.raises(ToolPolicyViolation):
        policy.authorize(planner_call(tool))

def test_tool_policy_rejects_another_object_id() -> None:
    with pytest.raises(ObjectBindingMismatch):
        policy.authorize(inventory_call(sku="SKU-OTHER"))
```

还要验证按场景动态暴露工具、重复无效调用、超出工具次数、超时和一次 replan 上限。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/unit/agent/test_tool_policy.py tests/unit/agent/test_tool_executor.py tests/integration/mcp/test_gateway.py tests/integration/mcp/test_tool_server.py -q
```

- [x] **Step 3: 实现受控执行器**

Planner 每个场景只看到该场景事实工具和 `policy.list_constraints`。`ToolExecutor` 接受经验证的 `ToolCallProposal`，调用现有类型化 `McpToolGateway`，返回带 `tool_call_id/tool_name/arguments_hash/evidence_ref/status/safe_summary` 的 Observation。此任务不接入 RAG，也不开放写工具。

实现修订：现有 FastMCP server 已完整注册三业务事实工具、规则工具和审批后写工具，不重复修改 server；新增边界位于 Planner 的动态工具目录、纯 `ToolPolicy` 和 `McpToolGateway.read_agent_tool` 只读分派。写工具继续存在于执行侧，但不进入 Planner definitions 或 Agent read dispatcher。

- [x] **Step 4: 运行 GREEN 与安全回归**

```bash
uv run pytest tests/unit/agent tests/integration/mcp -q
uv run pytest tests/integration/db/test_approval_race.py tests/integration/db/test_work_order_idempotency.py -q
```

- [x] **Step 5: 提交**

```bash
git add src/opercerta/agent/tool_policy.py src/opercerta/agent/tool_executor.py src/opercerta/infrastructure/mcp_gateway.py src/opercerta/domain/errors.py tests/unit/agent/test_tool_policy.py tests/unit/agent/test_tool_executor.py tests/integration/mcp/test_gateway.py docs/superpowers/plans/2026-07-21-opercerta-agent-core-architecture.md docs/development-log/daily/2026-07-21.md
git commit -m "feat: enforce read-only agent tool loop"
```

## Task 4: 三业务共享 Agent 图、查询路径与确定性 DecisionPlan

**Files:**

- Create: `src/opercerta/workflow/agent_controlled_action_graph.py`
- Modify: `src/opercerta/workflow/controlled_action_graph.py`
- Modify: `src/opercerta/workflow/replenishment_graph.py`
- Modify: `src/opercerta/workflow/equipment_maintenance_graph.py`
- Modify: `src/opercerta/workflow/task_recovery_graph.py`
- Modify: `src/opercerta/workflow/replenishment_recovery.py`
- Modify: `src/opercerta/domain/model_gateway.py`
- Modify: `src/opercerta/application/scenario_registry.py`
- Modify: `src/opercerta/api/app.py`
- Test: `tests/integration/workflow/test_agent_controlled_action_graph.py`
- Test: `tests/unit/application/test_scenario_registry_agent.py`
- Test: `tests/integration/workflow/test_controlled_action_graph.py`
- Preserve/regress: existing three scenario workflow/API suites

- [x] **Step 1: 写无 RAG 的真实 Agent 主链 RED 测试**

每个场景至少覆盖：有限请求 → GoalEncoder → Planner → 允许的 MCP 只读工具 → Observation → Analyst → Policy Guard。查询必须完成且零审批/零工单；创建必须生成由确定性代码计算的 DecisionPlan 并进入 `awaiting_approval`。模型提出不同对象、数量或风险时由 Harness/Guard 覆盖或拒绝。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/integration/workflow/test_agent_controlled_action_graph.py tests/integration/api/test_agent_operation_detail.py -q
```

- [x] **Step 3: 构建共享 LangGraph 有界循环**

节点顺序：

```text
receive_intent → encode_goal → plan_investigation → validate_investigation
→ execute_read_tools → analyze_observations → calculate_policy_facts
→ validate_decision_plan → report_query | request_approval
```

证据不足且仍有预算时回到 `plan_investigation`，最多一次；其他非法状态进入显式安全终态。场景注册表负责把 Observation 转回现有三业务严格 evidence/assessment/plan，模型文本不能替代这些类型。

实现修订：Agent 子图用独立 checkpoint namespace 运行，完成后只把受限 `AgentAnalysis` 交给原三业务图；原图重新验证 evidence、重新计算 assessment/plan，并继续独占审批 interrupt、批准后复核、幂等写和恢复。Agent Trace/Observation 的持久化 API 与 SSE 展示统一留到 Task 7，避免在 Task 4 先造一套临时 operation detail 字段再迁移。

- [x] **Step 4: 运行 GREEN 和旧三业务回归**

```bash
uv run pytest tests/integration/workflow/test_agent_controlled_action_graph.py tests/integration/api/test_agent_operation_detail.py -q
uv run pytest tests/integration/workflow tests/integration/api/test_operations_api.py -q
```

- [x] **Step 5: 提交**

```bash
git add src/opercerta/workflow src/opercerta/domain/model_gateway.py src/opercerta/application/scenario_registry.py src/opercerta/api/app.py tests/integration/workflow/test_agent_controlled_action_graph.py tests/integration/workflow/test_controlled_action_graph.py tests/unit/application/test_scenario_registry_agent.py docs/superpowers/plans/2026-07-21-opercerta-agent-core-architecture.md docs/development-log/daily/2026-07-21.md
git commit -m "feat: run three scenarios through bounded agent graph"
```

## Task 5: 审批后 Verifier、重新审批、幂等执行与重启恢复

**Files:**

- Modify: `src/opercerta/workflow/agent_controlled_action_graph.py`
- Modify: `src/opercerta/workflow/recovery_coordinator.py`
- Modify: `src/opercerta/workflow/controlled_action_recovery.py`
- Modify: `src/opercerta/domain/recovery.py`
- Modify: `src/opercerta/domain/operation_state.py`
- Modify: `src/opercerta/infrastructure/db/replenishment_operation_repository.py`
- Modify: `src/opercerta/infrastructure/db/operation_state_repository.py`
- Modify: `src/opercerta/infrastructure/db/approval_repository.py`
- Modify: `src/opercerta/infrastructure/db/work_order_repository.py`
- Create: `migrations/versions/0004_approval_cycles.py`
- Test: `tests/integration/workflow/test_agent_verification.py`
- Test: `tests/integration/workflow/test_agent_restart_recovery.py`
- Test: existing approval race, binding and idempotency suites

- [x] **Step 1: 写 `proceed/abort/escalate` 与恢复 RED 测试**

必须覆盖：

- approve 后绕过 Redis 重新取证；
- `proceed` + binding 一致 → 一条工单；
- `abort` → 安全终态、零工单；
- `escalate` → `needs_reapproval`、新 binding、零工单；
- Verifier 返回新参数即使标为 proceed 也强制 reapproval；
- 重复审批仍 409；并发审批只有一条决策；
- 在 Verifier 前、工单写后回读前重启；Trace 持久化前重启随 Task 7 的真实 Trace 表统一实现；
- 恢复后工单业务效果有效一次。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/integration/workflow/test_agent_verification.py tests/integration/workflow/test_agent_restart_recovery.py tests/integration/db/test_approval_race.py tests/integration/db/test_bound_approval.py tests/integration/db/test_work_order_idempotency.py -q
```

- [x] **Step 3: 实现审批后图节点与恢复协调**

```text
interrupt → resume_decision → refresh_evidence → verify_after_approval
→ compare_approval_binding → execute_work_order → verify_work_order
→ build_final_report → terminal
```

`needs_reapproval` 必须创建新审批周期和新 binding，计划 hash 必须按新事实重新计算并在事实或参数变化时改变，旧批准不能复用。`work_order.create` 仍仅由确定性执行节点调用，idempotency key 继续由 operation 生成，写后用 `work_order.get` 回读。

- [x] **Step 4: 运行 GREEN、竞态和恢复回归**

```bash
uv run pytest tests/integration/workflow tests/integration/db/test_approval_race.py tests/integration/db/test_bound_approval.py tests/integration/db/test_work_order_idempotency.py -q
```

- [x] **Step 5: 提交**

```bash
git add src/opercerta/workflow src/opercerta/domain src/opercerta/infrastructure/db migrations/versions/0004_approval_cycles.py tests docs
git commit -m "feat: verify approvals before idempotent execution"
```

实施证据：三业务 `proceed/abort/escalate`、Verifier 参数漂移、两轮绑定审批、缺失检查点恢复、复审迁移重放、10 路审批竞态和幂等写入的定向门禁为 `48 passed`；完整 workflow 为 `62 passed`；后端产品测试为 `502 passed`，另有依赖 WSL 原生 Git 的仓库安全脚本 `4 passed`。发布门禁继续为 `CLOSED`。

## Task 6: PostgreSQL pgvector、中文 SOP RAG 与 Memory 边界

**Files:**

- Create: `src/opercerta/domain/knowledge.py`
- Create: `src/opercerta/infrastructure/embedding_gateway.py`
- Create: `src/opercerta/infrastructure/db/knowledge_repository.py`
- Create: `migrations/versions/0005_agent_knowledge.py`
- Create: `data/knowledge/manifest.json`
- Create: `data/knowledge/inventory-replenishment-v1.md`
- Create: `data/knowledge/equipment-maintenance-v1.md`
- Create: `data/knowledge/task-recovery-v1.md`
- Create: `scripts/ingest_knowledge.py`
- Modify: `src/opercerta/tools/catalog.py`
- Modify: `src/opercerta/tools/server.py`
- Modify: `src/opercerta/infrastructure/mcp_gateway.py`
- Modify: `src/opercerta/workflow/agent_controlled_action_graph.py`
- Modify: `compose.yaml`
- Modify: `compose.release.yaml`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/integration/db/test_agent_knowledge_migration.py`
- Test: `tests/integration/db/test_knowledge_repository.py`
- Test: `tests/unit/infrastructure/test_embedding_gateway.py`
- Test: `tests/integration/mcp/test_tool_server.py`
- Test: `tests/integration/workflow/test_agent_rag.py`

- [x] **Step 1: 写迁移、幂等、过滤、引用和降级 RED 测试**

覆盖 `CREATE EXTENSION vector`、upgrade/downgrade/upgrade、document version/checksum、chunk 序号唯一、场景/active/version metadata filter、无合格引用返回 `knowledge_insufficient`、重复入库不重复、废弃版本不召回、跨场景 chunk 不泄露。CI repository test 使用固定可解释向量，不伪称真实语义质量。

- [x] **Step 2: 运行 RED**

```bash
uv run pytest tests/integration/db/test_agent_knowledge_migration.py tests/integration/db/test_knowledge_repository.py tests/unit/infrastructure/test_embedding_gateway.py tests/integration/mcp/test_knowledge_tool.py tests/integration/workflow/test_agent_rag.py -q
```

- [x] **Step 3: 固定依赖、迁移 image 并实现入库/检索**

```bash
uv add pgvector==0.5.0 fastembed==0.8.0
```

Compose PostgreSQL image 固定为 `pgvector/pgvector:0.8.2-pg18-trixie`。本地真实 embedding 使用 `BAAI/bge-small-zh-v1.5`，维度 512；模型缓存目录显式配置且不提交模型文件。新增 MCP `knowledge.search_sop`，返回 document/chunk/version/score/safe snippet。

- [x] **Step 4: 把 RAG 接入已通过的 Agent 主闭环**

Planner 可选择 `knowledge.search_sop`；Analyst 的知识性主张必须绑定 citation。RAG 不可用时返回 `knowledge_unavailable`：普通场景允许 Guard 依据精确事实继续并展示降级，明确要求 SOP 的规则则失败关闭。

- [x] **Step 5: 运行 GREEN 和真实本地代表检索**

```bash
uv run pytest tests/integration/db/test_agent_knowledge_migration.py tests/integration/db/test_knowledge_repository.py tests/unit/infrastructure/test_embedding_gateway.py tests/integration/mcp/test_tool_server.py tests/integration/workflow/test_agent_rag.py -q
uv run python scripts/ingest_knowledge.py --check
docker compose config
```

网络允许时下载并缓存固定 FastEmbed 模型，运行三业务代表查询；记录模型、维度、文档版本和返回引用，不预设或虚构准确率。

实施证据：新建空卷容器网络聚焦 `75 passed`、产品测试 `535 passed`、WSL 原生 Git 安全 `4 passed`；Ruff、173 文件格式、mypy 73 个源文件、114 包锁文件与仓库安全扫描通过。三份合成 SOP 共 12 个 chunk，真实固定模型完成首次入库、三文档幂等 replay 和三场景隔离检索；空卷门禁修复了迁移测试依赖预迁移数据库的隐式前置条件。新镜像构建并观察到 PostgreSQL/MCP healthy、API started；额外完整 Compose smoke 因当前 Codex 自动化 WSL 会话外层在约 43--49 秒停止 Docker service 未完成，保留到 Task 9 稳定交互式终端门禁，发布门禁继续 `CLOSED`。

- [x] **Step 6: 提交**

```bash
git add pyproject.toml uv.lock compose.yaml compose.release.yaml migrations/versions/0005_agent_knowledge.py src/opercerta/domain/knowledge.py src/opercerta/infrastructure/embedding_gateway.py src/opercerta/infrastructure/db/knowledge_repository.py src/opercerta/tools src/opercerta/infrastructure/mcp_gateway.py src/opercerta/workflow/agent_controlled_action_graph.py data/knowledge scripts/ingest_knowledge.py tests
git commit -m "feat: add cited pgvector SOP retrieval"
```

## Task 7: Agent Trace 持久化、API/SSE 与 RBAC

**Files:**

- Create: `src/opercerta/domain/agent_trace.py`
- Create: `src/opercerta/agent/trace_recorder.py`
- Create: `src/opercerta/infrastructure/db/agent_trace_repository.py`
- Create: `migrations/versions/0006_agent_trace.py`
- Modify: `src/opercerta/api/models.py`
- Modify: `src/opercerta/api/app.py`
- Modify: `src/opercerta/api/auth.py`
- Modify: `src/opercerta/workflow/agent_controlled_action_graph.py`
- Test: `tests/unit/agent/test_trace_redaction.py`
- Test: `tests/integration/db/test_agent_trace_repository.py`
- Test: `tests/integration/api/test_agent_trace_api.py`
- Test: `tests/integration/workflow/test_agent_trace_recovery.py`

- [ ] **Step 1: 写序列、去重、权限和泄露 RED 测试**

Trace 类型限定为 `perception/model/tool/rag/rule/human/execution/feedback/guardrail`。禁止字段测试至少包括 authorization、api_key、完整 prompt、reasoning_content、stack trace 和原始工具正文。operator 只能读授权 operation，approver 读待审批证据，auditor 只读跨场景脱敏 Trace，demo-admin 仅本地模式。

- [ ] **Step 2: 运行 RED**

```bash
uv run pytest tests/unit/agent/test_trace_redaction.py tests/integration/db/test_agent_trace_repository.py tests/integration/api/test_agent_trace_api.py tests/integration/workflow/test_agent_trace_recovery.py -q
```

- [ ] **Step 3: 实现 run/event/citation 与 SSE snapshot**

每个 event 使用 operation/run/sequence/semantic key 唯一约束，恢复重放不能产生重复业务 Trace。API 返回安全摘要、状态、时间、prompt/tool/citation refs，不返回 OTel span 或隐藏推理。

- [ ] **Step 4: 运行 GREEN 与安全扫描**

```bash
uv run pytest tests/unit/agent/test_trace_redaction.py tests/integration/db/test_agent_trace_repository.py tests/integration/api/test_agent_trace_api.py tests/integration/workflow/test_agent_trace_recovery.py -q
uv run python scripts/verify_repository_safety.py
```

- [ ] **Step 5: 提交**

```bash
git add migrations/versions/0006_agent_trace.py src/opercerta/domain/agent_trace.py src/opercerta/agent/trace_recorder.py src/opercerta/infrastructure/db/agent_trace_repository.py src/opercerta/api src/opercerta/workflow/agent_controlled_action_graph.py tests
git commit -m "feat: expose redacted agent trace"
```

## Task 8: React 单页 Agent 工作台与完整角色引导

**Files:**

- Create: `web/src/agent/IntentCard.tsx`
- Create: `web/src/agent/AgentTrace.tsx`
- Create: `web/src/agent/EvidenceAndCitations.tsx`
- Create: `web/src/agent/DecisionComparison.tsx`
- Create: `web/src/agent/NextRoleGuide.tsx`
- Modify: `web/src/api/contracts.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/components/OperationControls.tsx`
- Modify: `web/src/components/OperationDetail.tsx`
- Modify: `web/src/components/ApprovalPanel.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Test: corresponding `web/src/agent/*.test.tsx`
- Test: existing `App`/components/API client tests

- [ ] **Step 1: 写用户无法走通完整业务的 RED 测试**

测试 operator 有限表单、结构化 Goal、真实 Trace 分类、MCP 事实、SOP 引用、模型建议与确定性计划差异、审批 binding、批准后 Verifier、幂等工单回读和下一角色提示。禁止聊天输入、伪造逐字思考、fixed 浮层和用 audit event 冒充 Agent Trace。

- [ ] **Step 2: 运行 RED**

```bash
cd web
npm test -- --run
```

- [ ] **Step 3: 实现单页工作台**

单页按“表单 → Goal → 调查计划 → Tool/RAG → Observation → 建议/规则 → 审批 → Verifier → 工单/报告”渐进展示；角色切换保留 operation，明确下一步由谁操作。Mock/Real、合成数据、发布门禁和错误状态始终可见。动画只使用轻量 CSS transition，尊重 `prefers-reduced-motion`。

- [ ] **Step 4: 运行 GREEN、构建和响应式复核**

```bash
cd web
npm test -- --run
npm run build
```

在 1440px、1024px、390px 浏览器宽度手动检查，无固定遮挡、横向溢出、不可点击控件和状态丢失。

- [ ] **Step 5: 提交**

```bash
git add web/src
git commit -m "feat: build the OperCerta agent workspace"
```

## Task 9: Agent 轨迹评测、Compose 重启与真实代表验证

**Files:**

- Create: `data/evals/opercerta-agent-v1.json`
- Create: `scripts/run_agent_evaluation.py`
- Create: `scripts/verify_agent_compose.py`
- Modify: `scripts/verify_compose.py`
- Modify: `scripts/verify_real_model.py`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/unit/evaluation/test_agent_contracts.py`
- Test: `tests/integration/evaluation/test_agent_suite.py`
- Test: `tests/unit/runtime/test_verify_agent_compose.py`

- [ ] **Step 1: 先冻结透明预期轨迹和负例**

每个用例声明输入、允许工具、禁止工具、是否允许 replan、所需 citation、预期审批状态、Verifier 分支、终态和数据库断言。覆盖非法 Schema、Prompt Injection、未知工具、对象漂移、RAG 跨场景、批准后事实变化、并发审批、重复写入和关键节点重启。用例与实现分离，不能删除失败用例迎合结果。

- [ ] **Step 2: 运行 RED**

```bash
uv run pytest tests/unit/evaluation/test_agent_contracts.py tests/integration/evaluation/test_agent_suite.py tests/unit/runtime/test_verify_agent_compose.py -q
```

- [ ] **Step 3: 实现评测器和 Compose 断言**

报告区分：任务终态、工具选择、引用、审批、数据库效果、恢复和安全。Mock 固定套件与 Real 代表调用分开输出；没有 provider usage 就不写 Token/费用。

- [ ] **Step 4: 运行完整新鲜门禁**

```bash
uv run ruff check src tests migrations scripts
uv run mypy src
uv run pytest -q
cd web && npm test -- --run && npm run build && cd ..
docker compose up --build -d
uv run python scripts/verify_agent_compose.py
docker compose restart api mcp
uv run python scripts/verify_agent_compose.py --recovery-only
uv run python scripts/verify_repository_safety.py
```

再进行已授权的少量真实 Kimi Tool Calling 和本地 FastEmbed RAG 代表验证；任何失败都如实保留，不能用 Mock 补写为 Real 通过。

- [ ] **Step 5: 提交**

```bash
git add data/evals/opercerta-agent-v1.json scripts .github/workflows/ci.yml tests
git commit -m "test: gate OperCerta agent trajectories"
```

## Task 10: 中文技术手册、人工实验、面试材料与交付证据

**Files:**

- Modify: `README.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `docs/learning/OperCerta核心技术手册.md`
- Modify: `docs/learning/OperCerta手动实验手册.md`
- Modify: `docs/learning/OperCerta面试讲解手册.md`
- Modify/Create: `docs/development-log/daily/*.md`
- Create only after fresh evidence: `docs/release-evidence/agent-core-architecture.md`
- Modify: `docs/demo-script.md`

- [ ] **Step 1: 写文档防漂移测试或清单**

文档必须能回答：为什么 LangGraph + 最小 LangChain、为什么不是聊天框、六层如何映射代码、四类 Memory 区别、RAG 与 SQL/MCP 边界、Tool Calling 如何校验、为何批准后重新取证、Agent Trace 与 audit/OTel 区别、重启如何恢复、哪些仍未上线。

- [ ] **Step 2: 完成中文学习与手动实验路径**

手动实验必须让用户独立完成：启动 → operator 提交三业务之一 → 查看 Goal/Tool/RAG/Observation → approver 审批 → Verifier → 工单回读 → auditor Trace → 数据库断言 → 重启恢复。每步写“输入、预期、为何如此、常见错误、面试可怎么讲”。

- [ ] **Step 3: 只根据 Task 9 原始结果写证据**

不得手填通过数量。证据引用命令、报告路径、Git commit、模型模式、数据边界和仍关闭的门禁；如果真实模型或 RAG 没通过，明确列为 blocker/known limitation。

- [ ] **Step 4: 最终本地和远程门禁**

```bash
git diff --check
uv run python scripts/verify_repository_safety.py
uv run ruff check src tests migrations scripts
uv run mypy src
uv run pytest -q
cd web && npm test -- --run && npm run build && cd ..
```

推送 feature branch，创建 PR，等待 GitHub Actions 全绿并完成 review；未合并/未验证前不改 `main` 结论、不启动 ForenTrail。

- [ ] **Step 5: 提交文档**

```bash
git add README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs
git commit -m "docs: deliver OperCerta agent architecture evidence"
```

## 3. 完成定义

本计划只有在以下条件同时满足时才能标记完成：

- 三业务都经过真实 LangGraph Agent 节点而不是旧固定说明路径；
- LangChain 组件在代码中有真实、可定位用途，且不存在嵌套 `create_agent`；
- 模型产生受约束只读 Tool Call/结构化计划，MCP 返回真实类型化 Observation；
- 无 RAG 时主 Agent 闭环可完成，RAG 接入后有 pgvector、真实中文 embedding、版本过滤和引用证据；
- `proceed/abort/escalate`、重新审批、竞态、幂等和关键节点恢复都有自动化数据库断言；
- Agent Trace 来自真实后端事件，UI 不展示伪思考且四角色流程可走通；
- Mock 与 Real 证据严格分开，未虚构指标、材料、上线或安全状态；
- 中文核心技术手册、人工实验、面试讲解、开发日志和文档索引同步；
- 用户能不依赖 Codex 完成至少一个业务闭环，并讲清感知、规划、工具、Memory、执行反馈和安全边界；
- GitHub Actions 新鲜全绿；产品公开发布门禁是否打开仍按原发布条件单独判断。
