# OperCerta｜智能运营处置 Agent

OperCerta 是面向库存异常、设备告警和运营工单的智能运营处置 Agent 独立作品仓库。

> 当前状态：库存补货、设备维修、作业异常恢复三条 FastAPI + LangGraph + FastMCP + PostgreSQL 闭环、演示 JWT/RBAC、42 条固定合成契约评测、Redis 只读缓存、OpenTelemetry 适配、本地 React 控制台与 GitHub Actions 均已有自动化证据；Moonshot AI `kimi-k2.6` 已完成三业务 6 次代表操作/3 条真实模型路径的本地验证；[公开静态项目专题](https://opercerta-kxh.netlify.app)、[单页作品集](https://kxh-agent-portfolio.netlify.app)和 [public GitHub](https://github.com/KXHXK/opercerta)已验证。公开页面不提供后端写入口；生产身份、交互 HTTPS 后端、自动部署和公开 API 尚未完成，生产发布门禁：`CLOSED`。

## 当前已验证范围

- 严格非法输入与 JSON-only 恢复快照；
- 确定性恢复决策矩阵；
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
- 用户授权的 Moonshot AI `kimi-k2.6` 代表性验证：三业务各 1 条 query 与 1 条批准路径，共 6 个 operation、3 条真实模型解释路径；报告不保存模型原文，token/成本因 adapter 未暴露 usage 而明确标记不可用。

三业务评测、Compose 与缓存证据见 [三业务发布前证据](docs/release-evidence/three-business-evaluation-compose.md)，真实模型结果见[真实模型代表性验证](docs/release-evidence/real-model-representative-validation.md)，可靠性内核与历史库存切片证据保留在 `docs/release-evidence/`。中文学习入口为 [核心技术手册](docs/learning/OperCerta核心技术手册.md)、[手动实验手册](docs/learning/OperCerta手动实验手册.md)和[面试讲解](docs/learning/OperCerta面试讲解.md)。这些不是生产 IAM、交互 HTTPS 后端或公开 API 完成声明。

## 下一实施边界

下一阶段仍只实施 OperCerta。真实模型本地代表性验证已完成；下一关键节点是选择并审批公网交互 HTTPS 的成本与安全方案，其后执行固定提交远程 CI、Release Tag 和个人手动掌握检查。生产发布门禁为 `CLOSED`，关闭前不启动其他项目。

三业务收口规格与八项 TDD 主计划见 [设计](docs/superpowers/specs/2026-07-20-opercerta-three-business-release-design.md)和[计划](docs/superpowers/plans/2026-07-20-opercerta-three-business-release.md)。历史库存切片设计仍作为可靠性内核演进记录保留。

## 实施依据

按以下顺序阅读并实施：

1. [AI Agent 四项目命名设计规格](docs/specs/2026-07-14-agent-project-naming-design.md)
2. [AI Agent 四项目总体设计规格](docs/specs/AI_Agent四项目总体设计规格.md)
3. [AI Agent 四项目作品集组合设计](docs/specs/2026-07-14-agent-portfolio-design.md)
4. [OperCerta 详细设计](docs/specs/2026-07-14-opercerta-design.md)

新对话的启动约束和交接清单见 [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md)。

## 仓库边界

- 本仓库包含从零实现的可靠性内核代码、测试、设计、计划、开发日志、本地证据和公开静态专题；尚不包含可公开写入的完整生产应用。
- 代码、接口、数据和展示材料均从零实现，只使用公开或合成数据，不复制或依赖任何原单位资产。
- 性能、准确率、成本和稳定性数字只能引用可复现评测的实测结果；未通过发布门禁前不宣称已经上线。
- 只完成并发布 OperCerta 后，才开始下一个项目 ForenTrail。
