# OperCerta | Auditable Operations Agent

OperCerta is a controlled AI operations agent for inventory exceptions,
equipment alerts, and operational work orders. It combines FastAPI,
LangGraph, FastMCP, PostgreSQL, approval checkpoints, idempotent tool calls,
and audit-focused observability in a reproducible reference implementation.

- [Project showcase](https://opercerta-kxh.netlify.app)
- [Portfolio overview](https://kxh-agent-portfolio.netlify.app)
- Status: engineering showcase; the public site is read-only and the
  production release gate remains closed.

## 中文说明

OperCerta 是面向库存异常、设备告警和运营工单的智能运营处置 Agent 独立作品仓库。

> 当前状态：库存补货、设备维修、作业异常恢复三条 FastAPI + 单根 LangGraph + 最小 LangChain + FastMCP + PostgreSQL/pgvector 闭环、演示 JWT/RBAC、Agent Trace、本地 React 控制台、Redis 只读证据缓存和真实 FastEmbed RAG 已有自动化证据。少量 Moonshot AI `kimi-k2.6` 代表验证覆盖三业务只读、库存批准写入和无效 provider fail-closed，未回退 Mock 冒充成功。[PR #8](https://github.com/KXHXK/opercerta/pull/8) 已合并为 `609f8f7`，对应 [main CI](https://github.com/KXHXK/opercerta/actions/runs/30203438564) 的仓库安全、Python 质量、完整后端、前端和 Compose 重启恢复全部通过。新版[零成本静态项目专题](https://opercerta-kxh.netlify.app)已于 2026-07-27 发布 deploy `6a6631d24958714a43ddc508`，[单页作品集](https://kxh-agent-portfolio.netlify.app)继续可只读访问；公开页面不提供后端写入口。生产身份、交互 HTTPS 后端、自动部署和公开 API 尚未完成，生产发布门禁：`CLOSED`。

## 当前已验证范围

- 严格非法输入与 JSON-only 恢复快照；
- PostgreSQL Schema、Alembic 升降级和审批原子竞态；
- 授权后幂等工单写入与并发安全重放；
- 独立 `langgraph` Schema checkpointer；
- LangGraph interrupt、审批绑定、批准后事实重取、拒绝终止和 A/B 重启恢复；
- 真实 MCP 工单幂等写入、写后读验证、预写工单安全重放和审批过期扫描；
- FastAPI 操作创建、业务事实查询、绑定审批、固定安全错误映射和生产 lifespan 启动恢复。
- 冻结依赖、`0002` 迁移升降级、审批竞态与 A/B 重启重复、真实 FastMCP + FastAPI 双服务进程和 PostgreSQL 终态事实。
- WSL2 Ubuntu Compose 的非 root 应用镜像、PostgreSQL/Redis、API/MCP 健康检查、三业务审批/拒绝/唯一工单、数据库断言和 API/MCP 重启恢复。
- 版本化 42 条固定评测（库存 30、设备 6、作业 6）与 2×2 缓存/工具模式矩阵；小样本只证明调用/命中行为，不作为生产 SLA。
- 服务端 UUIDv4 request_id、异常后上下文清理、安全 JSON 日志、应用级低基数 Prometheus 指标、SSE 实际回放计数，以及默认关闭的 `/metrics`。
- Public GitHub remote、只读且固定 Action SHA 的四个 PR 快速门禁，以及 `main` 上实际通过的 Compose 业务 smoke、API/MCP 重启恢复和无条件清理。
- Netlify 公开静态专题、真实部署资源指纹和证据图片响应验证；该站点不连接 API、数据库或 MCP。
- 历史解释型 adapter 曾完成 Moonshot AI `kimi-k2.6` 三业务代表运行；新 Plan-and-Execute Agent 的 Real Kimi Tool Calling 报告为 failed，不能沿用旧结果声称新架构已通过。报告不保存模型原文，provider 未返回 usage 时不估算 token/成本。
- 冻结 Agent 轨迹评测 9/9，覆盖非法 schema、提示注入、未知工具、对象漂移、RAG 隔离、批准后事实漂移、审批竞态、幂等写入与关键重启；这不是生产准确率。
- 零成本展示门禁：前端 16 个测试文件/40 条测试、后端 430 条测试、Ruff、138 文件格式、mypy 62 个源码文件和仓库安全检查全部通过；Mock release Compose 从全新卷启动并完成 API/MCP 重启恢复；1440/768/390 三档浏览器检查无项目固定模块、横向溢出、坏图或控制台告警；新版专题和作品集已经两阶段 Netlify 发布并完成生产 HTTP/浏览器核验。

新 Agent 核心的本地通过项与 Real Kimi 失败边界见 [Agent 核心架构交付证据](docs/release-evidence/agent-core-architecture.md)。旧三业务评测、Compose、缓存与解释型模型证据保留为历史阶段证据，不能替代新架构验证。中文学习入口为 [核心技术手册](docs/learning/opercerta-core-technical-guide.md)、[手动实验手册](docs/learning/opercerta-manual-experiment-guide.md)和[面试讲解](docs/learning/opercerta-interview-guide.md)。这些不是生产 IAM、交互 HTTPS 后端或公开 API 完成声明。

## 下一实施边界

下一阶段仍只实施 OperCerta。单根 Agent 纠偏已经合并，main Compose 和新版静态专题生产发布均已通过；下一步完成用户手动演示、源码讲解与口述掌握检查，再整理 Release Tag、简历话术和五分钟演示材料。是否建设公网可写 HTTPS 后端仍需单独选择托管环境并审批成本与安全治理。生产 IAM、限流/防滥用、备份、高可用、自动部署和正式 Release Tag 仍待完成。生产发布门禁为 `CLOSED`，关闭前不启动其他项目。

三业务收口规格与八项 TDD 主计划见 [设计](docs/superpowers/specs/2026-07-20-opercerta-three-business-release-design.md)和[计划](docs/superpowers/plans/2026-07-20-opercerta-three-business-release.md)。历史库存切片设计仍作为可靠性内核演进记录保留。

## 实施依据

按以下顺序阅读并实施：

1. [AI Agent 四项目命名设计规格](docs/specs/2026-07-14-agent-project-naming-design.md)
2. [AI Agent 四项目总体设计规格](docs/specs/ai-agent-portfolio-overall-design.md)
3. [AI Agent 四项目作品集组合设计](docs/specs/2026-07-14-agent-portfolio-design.md)
4. [OperCerta 详细设计](docs/specs/2026-07-14-opercerta-design.md)

新对话的启动约束和交接清单见 [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md)。

## 仓库边界

- 本仓库包含从零实现的可靠性内核代码、测试、设计、计划、开发日志、本地证据和公开静态专题；尚不包含可公开写入的完整生产应用。
- 代码、接口、数据和展示材料均从零实现，只使用公开或合成数据，不复制或依赖任何原单位资产。
- 性能、准确率、成本和稳定性数字只能引用可复现评测的实测结果。
