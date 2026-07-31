# OperCerta 规格一致性与发布就绪审计（2026-07-31）

## 审计结论

OperCerta 当前实现与“受控单 Agent + 三业务共享可靠性内核”的有效设计主线一致。库存补货、设备维修和作业恢复共享同一条生产 LangGraph 生命周期，并接入 LLM 有界决策、FastMCP 工具、pgvector SOP 检索、人工审批、批准后复核、幂等写入、PostgreSQL 事实、Redis 只读缓存、Agent Trace 和重启恢复。

本次正式将当前版本定义为：

> **公开静态展示 + 本地可复现完整 Agent MVP + 3–5 分钟录屏。**

因此，原始详细设计中“线上地址跑通真实业务”的要求仍属于 Product Release，不能用静态 Showcase 冒充；但它不再阻塞本次 Showcase Release。修订依据见 `docs/superpowers/specs/2026-07-31-showcase-release-gate-amendment-design.md`。

## 当前门禁

| 门禁 | 状态 | 剩余条件 |
| --- | --- | --- |
| 工程与本地自动化 | `PASSED` | 本收口分支合并后补录新鲜 main CI/Compose 结果 |
| Showcase Release | `AWAITING_OWNER_VALIDATION` | 本人完整实演、源码讲解、恢复/幂等验证和录屏 |
| Product Release | `CLOSED` | 公网可写后端及完整生产治理未实现 |

## 核验依据

1. `docs/specs/2026-07-14-agent-project-naming-design.md`。
2. `docs/specs/ai-agent-portfolio-overall-design.md`。
3. `docs/specs/2026-07-14-agent-portfolio-design.md`。
4. `docs/specs/2026-07-14-opercerta-design.md`。
5. 三业务发布、Agent 核心架构、异常信号收件箱、信号对账、单根 Agent Loop 等后续已批准修订。
6. 当前源码、锁文件、迁移、Compose、固定评测、CI、真实模型代表报告和本机运行事实。

后来的明确修订优先于早期被修订条款；测试或文档不能代替真实运行证据。

## 设计—实现映射

| 设计要求 | 当前实现 | 结论 |
| --- | --- | --- |
| 库存、设备、作业三业务 | scenario registry、三类 detector、策略和工单 payload | 一致 |
| 有限输入而非自由聊天 | React 表单、Pydantic Goal/Intent、对象/动作 allowlist | 一致，符合受控业务边界 |
| 单 Agent Plan-and-Execute | `ControlledAgentRootGraph` 与 Model → Tool → Observation 有界回环 | 一致 |
| LangGraph 生命周期 | 同一 thread/checkpoint 覆盖调查、审批、复核、写入和终态 | 一致 |
| MCP 工具 | 7 个类型化事实、规则、知识和工单工具 | 一致；写工具受策略和审批约束 |
| RAG 与 Memory | FastEmbed、pgvector、SOP citation；checkpoint/事实/知识分层 | 一致；检索不提供权威数量或权限 |
| 审批与复核 | JWT/RBAC、绑定哈希、行锁、cache bypass、Verifier | 一致 |
| 幂等与恢复 | 幂等键、唯一约束、写后读、PostgreSQL checkpointer | 一致 |
| 前后端 | FastAPI 安全边界、React Case 工作台、SSE/Trace/审计 | 本地一致；公网 API 未部署 |
| 基础设施 | PostgreSQL 18/pgvector、Redis、Docker Compose、Caddy | 本地与 CI 一致 |
| 可观测性 | 关联 ID、结构化日志、OpenTelemetry、Prometheus | 代码/测试具备；无公网 collector/dashboard |
| 测试评测 | 本分支后端 671、前端 60、三业务 42/42、Agent 9/9、Compose | 后端为一次性 pgvector 库本地结果；最终 main 仍需 CI 复核；不是生产 SLA |

## 合理设计演进

- 三业务修订补齐了原始详细设计对作业阻塞的缺口，不是无审批扩展。
- MCP 从原始 5 个工具扩展为 7 个，是任务事实与 SOP 检索规格的明确结果。
- 入口从自由自然语言收敛为有限业务表单；LLM 仍负责图内语义、规划、Observation 后决策和批准后 Verifier。
- 生产图统一为单根 Agent Loop；历史场景图只承担回归和等价测试。

## 已验证事实

- 收口前最新 main 为 `61d5fa0`，PR #22 和 Actions run `30622621533` 五项成功。
- 收口前 main 为后端 668；本分支新增 3 条门禁契约后，本地一次性 pgvector 测试库结果为 `671 passed in 112.07s`。前端 19 文件/60 条、三业务 42/42、Agent 9/9、Compose 数据库副作用及 API/MCP 重启恢复此前均通过，等待本分支最终复验。
- Netlify 根路径与 `/api/*` 都是静态 SPA，证明公网未暴露 FastAPI。
- 本机 `opercerta-demo` 的 PostgreSQL、Redis、MCP、API 四服务 healthy，readiness 的 database/checkpoint/MCP 均 ready。
- README/CONTRIBUTING 使用标准 `English｜简体中文` 双文件互链；GitHub Markdown 不支持无跳转、无折叠且只显示一种语言的自定义状态切换。

## 本轮已解决的公开仓库缺口

- 新增 Apache-2.0 `LICENSE`。
- Dockerfile uv 与本地/CI 统一为 `0.11.28`。
- 仓库安全扫描扩展到双语公开文档、handoff 和索引。
- 用双门禁修订消除“静态 Showcase”与“公网 Product”完成定义冲突。
- 新增不得由 Codex 代签的项目所有者掌握验收表。

## 非 Showcase 阻塞项

以下事项继续阻塞 Product Release，但不阻塞诚实边界内的 Showcase：

- 生产身份、精确 CORS、公网 HTTPS API、限流、配额、防滥用与模型费用熔断。
- 托管密钥、托管 PostgreSQL、备份/恢复演练、高可用与迁移回滚。
- 线上日志/Trace/指标收集、dashboard、告警和公网端到端验收。
- main branch protection、`SECURITY.md`、Code of Conduct、Issue/PR 模板和独立 ADR 可继续增强开源治理。
- 独立人工标注质量集、更多真实模型重复运行、浏览器 E2E、无障碍和供应链扫描属于后续增强；不得虚构指标。

## 发布使用边界

| 使用方式 | 当前结论 | 合法表述 |
| --- | --- | --- |
| GitHub 源码 | 可用 | 经 CI 验证的受控运营 Agent MVP |
| Netlify | 已上线 | 公开静态项目展示 |
| 本地/现场演示 | 工程具备、待本人验收 | Docker Compose 单节点完整 Agent MVP |
| 公网交互 | 未实现 | 不得称为在线可操作 Agent |
| 企业生产 | 未实现 | 不得声称高可用、SLA 或真实 WMS/CMMS 接入 |

## 剩余 P0 收口

1. 本分支全门禁、PR、main CI 与 Compose 复验。
2. 项目所有者按 `docs/learning/opercerta-ownership-acceptance.md` 独立完成验收，并保存 `operation_id`、`work_order_id`、Trace、审计和数据库事实。
3. 完成 3–5 分钟录屏；之后才能签署本人掌握结果并创建最终 Showcase tag。

ForenTrail 暂不启动。FieldPilot 在 OperCerta 完成后另行规划，不混入本仓库。
