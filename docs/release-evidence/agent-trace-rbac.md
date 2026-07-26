# Agent Trace 持久化、恢复与访问控制证据

日期：2026-07-22
范围：Agent 核心架构计划 Task 7
结论：本地代码与自动化门禁通过；生产发布门禁仍为 `CLOSED`。

## 实施内容

- 新增迁移 `0006_agent_trace`，建立 `agent_runs`、`agent_trace_events` 和 `agent_trace_citations` 三张表。
- 每个事件同时绑定 `operation_id`、`run_id`、递增 `sequence` 和稳定 `semantic_key`；数据库唯一约束与行锁共同保证重放不重复、并发追加不乱序。
- Trace 类型限定为 `perception`、`model`、`tool`、`rag`、`rule`、`human`、`execution`、`feedback`、`guardrail`，记录真实组件结果，不伪造模型隐藏思维链。
- 递归脱敏器采用禁止字段、深度、集合长度和文本长度边界，拒绝保存 authorization、API key、密码、完整 prompt、messages、reasoning content、原始工具正文和异常堆栈。
- RAG Trace 只保存文档、chunk、版本、分数等 citation reference，不复制 SOP 正文或原始结构化载荷。
- LangGraph 首次调查、人工审批、批准后执行/复核和最终反馈均写入 Trace；检查点丢失后从业务状态重建，语义事件保持相同 ID 与序列。
- 新增 `GET /api/v1/operations/{operation_id}/agent-trace` 与 SSE snapshot replay 路由。该 SSE 是已持久化事件快照回放，不声称具备数据库通知驱动的实时 tail。
- 权限边界：operator 只能读取本人 operation；approver 只能读取当前待审批/待复审 operation；auditor 可跨场景只读脱敏 Trace；demo-admin 只在显式本地开关启用。

## 测试驱动证据

1. RED 从缺失 `opercerta.agent.trace_recorder` 开始；随后脱敏结构测试先暴露了断言写法过宽的问题，修正为精确结构断言。
2. 真实图恢复测试首次因合成 MCP 证据时间与测试时钟不一致触发 `EvidenceExpired`；对齐批准规格中的固定时钟后通过，没有放宽生产证据有效期。
3. 开启 Trace 的 API 回归暴露“主体工具失败后仍 replan，Mock planner 生成空计划，最终 503”的缺陷；修复为主体/策略工具失败立即安全终止并传播原始稳定错误码，缺失对象恢复为预期 422。
4. 全量测试最初出现 `RPL-024` 语义变化：旧冻结评测被测试 harness 全局切换为 Agent 模式。修复为旧评测默认保留确定性基线，只有 Agent Trace 新测试显式启用 Agent 模式。

## 新鲜验证结果

- 产品测试：`545 passed in 187.62s`。此结果覆盖 Task 7 产品代码及当时全部用例。
- 最新 RBAC 断言补强后的 Task 7 定向回归：`8 passed in 27.39s`。
- WSL 原生 Git 安全测试：`4 passed in 0.30s`。
- 最新静态门禁：Ruff 通过、181 个文件格式正确、mypy 检查 77 个源文件通过；仓库安全扫描和 `git diff --check` 通过。

## 环境故障与边界

- Windows 原生 PostgreSQL 18.4 未安装 pgvector，不能承担 Task 6 之后的完整集成门禁；定向测试改用 Compose 的 `pgvector/pgvector:0.8.2-pg18-trixie`。
- WSL 不能通过当前 `127.0.0.1` 访问 Windows PostgreSQL；测试通过 Compose 容器网络地址运行，连接串仅存在于测试进程且不写入 Git。
- 一次失败 traceback 展开了 Windows 本地测试角色旧密码；该密码已立即轮换并用新凭据验证。文档不保存旧值或新值。
- Windows `uv` 不得操作 WSL `.venv`；本轮误操作造成 Linux 虚拟环境部分缺失，随后严格按 `uv.lock` 由 WSL `uv sync --frozen` 重建。后续平台虚拟环境必须分别命名。
- 完整 Compose API/MCP 重启 smoke、真实 Kimi Trace 和浏览器端 Agent 工作台属于 Task 8--9，尚未完成，不能据此宣称已上线。

## 面试表达

> 我把 Agent Trace 与审计日志、OpenTelemetry 分开：Trace 面向业务解释，记录感知、模型建议、工具事实、RAG 引用、规则、人工审批和执行反馈；审计日志证明业务状态变化；OTel 用于跨组件性能与故障定位。三者都不保存隐藏思维链或秘密。恢复时用 operation、run、sequence 和 semantic key 做数据库级去重，所以 LangGraph 重放不会制造第二套业务轨迹。
