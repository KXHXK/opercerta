# OperCerta 最终收口审计（2026-08-10）

## 审计范围与优先级

本次审计覆盖四份 `docs/specs/` 基线设计、后续已批准的 `docs/superpowers/specs/` 修订、对应实施计划、当前源码、测试、评测、Compose、公开静态专题和发布证据。发生冲突时按“后批准、范围更具体的修订规格优先”解释；历史设计原文不回写，以保留决策演进。

当前版本仍定义为：

> **公开静态展示 + 本地可复现完整 Agent MVP + 3–5 分钟录屏。**

## 规格—实现—证据矩阵

| 规格目标 | 当前实现 | 自动化或文档证据 | 结论 |
| --- | --- | --- | --- |
| 只实施 OperCerta，不复用旧公司材料 | 仓库只包含 OperCerta 源码与合成业务数据 | `verify_repository_safety.py`、四份基础设计 | 符合 |
| 库存、设备、任务三业务闭环 | signal → case → Agent 调查 → 审批 → 复核 → 幂等工单 | 42/42 三业务契约、Compose 数据库断言 | 符合 |
| 异常先被合理发现，再启动 Agent | 确定性 signal scanner 读取事实与规则，创建/对账 signal；用户从 case 启动调查 | signal inbox、reconciliation 和 successor 测试/证据 | 符合 |
| 有限业务输入，不开放无边界聊天 | React 表单与 FastAPI/Pydantic 形成可信 `IntentEnvelope` | API、前端与非法输入测试 | 符合 |
| LLM 是认知层但不是写入权威 | Goal 编码、有界 ReAct 风格 Tool Loop、FinalAnalysis、批准后 Verifier | Agent Trace、9 条冻结轨迹、9 条 Kimi 固定路径 | 符合；已纠正旧“严格 Plan-and-Execute”表述 |
| LangGraph 承担 Agent 编排 | 单一 `ControlledAgentRootGraph` 负责循环、interrupt、checkpoint、resume 和 recovery | checkpoint/重启恢复测试与 Compose recovery-only | 符合 |
| MCP/Skill/Function Calling | 模型经 LangChain 原生 tool calling 选择 5 个只读 MCP 工具；写工具只由代码节点调用 | ToolPolicy、ToolExecutor、FastMCP 集成测试 | 符合 |
| RAG 与长期知识 | FastEmbed + pgvector 检索按场景、版本和有效状态过滤的合成 SOP，并返回 citation | RAG 隔离测试、真实模型 citation 指标 | 符合；SOP 不覆盖业务事实和审批规则 |
| 记忆与状态 | Graph State、PostgreSQL checkpoint、pgvector SOP、Trace/Audit 四类记忆 | 核心技术手册、数据库和恢复测试 | 符合；无用户画像或跨任务聊天记忆 |
| 高风险写入受控 | JWT/RBAC、审批绑定、批准后绕过 Redis 重取事实、Verifier、确定性 Binding | 审批、事实漂移、缓存绕过与权限测试 | 符合 |
| 审批竞态与幂等副作用 | PostgreSQL 行锁、审批周期唯一语义、operation 派生幂等键、唯一约束、写后读 | 并发审批、重复写入、数据库断言 | 符合 |
| 可恢复、可审计、可观测 | 业务表主导恢复 + checkpoint；Trace、Audit、SSE、低基数指标 | 9/9 安全恢复评测、Compose restart | 符合 |
| 前端可展示技术链路 | Case 隔离、角色切换、业务事实、审批、Agent Trace、架构与 Eval 专题 | 收口分支 19 个前端测试文件/63 条用例、Vite build | 符合 |
| 评测不虚构 | 682 条后端、63 条前端、42/42、9/9 Agent、9/9 Kimi 固定本地小样本 | JSON 报告与 release evidence | 符合；不等于生产准确率或 SLA |
| 静态公开展示与本地 MVP 分离 | Netlify 只读页面；可写 API、数据库和 demo JWT 仅在本地 | Showcase 门禁修订、README、Netlify 证据 | 符合 |

## 本次发现并处理的偏差

1. **主线 CI 状态漂移：** main `c4257ac` 的 Actions run `30744845403` 并非五项全绿。四项通过，`compose-smoke` 在 clean runner 构建镜像时因 `uv sync --offline` 缺少 `hatchling` 缓存而失败。收口分支用 RED/GREEN 测试移除错误的离线假设；PR #26 合并后的 main run `31519846029` 五项全绿，已关闭此项。
2. **Agent 模式术语漂移：** README 和讲解文档沿用 Plan-and-Execute，但当前实现是模型根据 Observation 逐轮选择工具的有界 ReAct 风格循环。已统一表述，避免面试或开源审查时与代码不符。
3. **前端数字漂移：** 已合并 main 实际为 62 条前端用例，部分 README、专题和状态文档仍显示 60。同步后又增加源码入口回归测试，因此收口分支最终为 63 条。
4. **前端传递依赖告警：** `npm ci` 后发现 nanoid、postcss、undici 的传递依赖漏洞。锁文件已升级到修复版本，CI 新增 high 级依赖审计。
5. **开源安全报告缺口：** CONTRIBUTING 曾写“计划增加安全策略”。已新增 `SECURITY.md` 并改为可执行的私密报告优先流程。
6. **Harness 学习材料分散：** Prompt、上下文、工具、编排、记忆、Eval、约束与恢复已集中补入核心技术手册，并明确 Mock/Real、token budget 和通用并行调度边界。

## 仍需项目所有者完成的关键节点

- 独立完成 `opercerta-ownership-acceptance.md` 的业务实演、源码讲解、重启/幂等实验和记录；Codex 不得代签。
- 录制 3–5 分钟演示并核对静态专题内容。
- 验收通过后创建最终 Showcase tag；不得提前把 Product Release gate 打开。

## 发布判定

- 工程与本地自动化门禁：`PASSED`，本分支完整本地结果已通过。
- 远程 CI 门禁：`PASSED`；PR #26 已合并为 `cde3dcd`，main run `31519846029` 五项全部通过。
- Showcase Release gate：`AWAITING_OWNER_VALIDATION`。
- Product Release gate：`CLOSED`。

公网 FastAPI、生产 IAM、限流、防滥用、托管密钥、备份恢复、高可用和线上告警不属于当前 Showcase 版本，不应为了“看起来完整”而伪装为已实现。
