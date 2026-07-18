# OperCerta｜智能运营处置 Agent

OperCerta 是面向库存异常、设备告警和运营工单的智能运营处置 Agent 独立作品仓库。

> 当前状态：库存不足到补货工单的 FastAPI 后端纵向闭环、演示 JWT/RBAC、30 条固定合成契约评测、本地单页运营控制台以及可观测性与安全回归基础均已完成本地验证；真实生产身份、CI/CD、HTTPS 和公开发布尚未完成，发布门禁保持关闭。

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
- WSL2 Ubuntu Compose 的非 root 应用镜像、独立 PostgreSQL named volume、API/MCP 健康检查、真实库存补货审批闭环、数据库断言和 API/MCP 重启恢复。
- 服务端 UUIDv4 request_id、异常后上下文清理、安全 JSON 日志、应用级低基数 Prometheus 指标、SSE 实际回放计数，以及默认关闭的 `/metrics`。

Task 7 新鲜证据见 [补货执行与重启恢复证据](docs/release-evidence/replenishment-execution-restart.md)，Task 1–9 总证据见 [库存补货后端纵向闭环证据](docs/release-evidence/inventory-replenishment-vertical-slice.md)，Docker/Linux 证据见 [WSL2 Ubuntu Compose 运行时证据](docs/release-evidence/docker-linux-runtime.md)，评测证据见 [固定契约评测](docs/release-evidence/replenishment-contract-evaluation.md)，本轮证据见 [可观测性与安全回归](docs/release-evidence/observability-security-regression.md)。这不是生产 IAM、HTTPS 或公开部署完成声明。

## 下一实施边界

下一阶段仍只实施 OperCerta，进入发布门禁剩余范围；可在 CI 安全门禁与 Caddy/HTTPS 设计中择一继续，并在获得外部平台与发布权限后处理生产身份和公开部署，不启动其他项目。

首个闭环已确定为“库存不足 → 补货工单”，采用独立 FastMCP 服务、四个真实 MCP 工具、Mock 结构化模型、LangGraph 和 FastAPI；[设计规格](docs/superpowers/specs/2026-07-16-inventory-replenishment-vertical-slice-design.md)与[可执行 TDD 计划](docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md)已落盘并执行至 Task 9。

## 实施依据

按以下顺序阅读并实施：

1. [AI Agent 四项目命名设计规格](docs/specs/2026-07-14-agent-project-naming-design.md)
2. [AI Agent 四项目总体设计规格](docs/specs/AI_Agent四项目总体设计规格.md)
3. [AI Agent 四项目作品集组合设计](docs/specs/2026-07-14-agent-portfolio-design.md)
4. [OperCerta 详细设计](docs/specs/2026-07-14-opercerta-design.md)

新对话的启动约束和交接清单见 [IMPLEMENTATION_HANDOFF.md](IMPLEMENTATION_HANDOFF.md)。

## 仓库边界

- 本仓库包含从零实现的可靠性内核代码、测试、设计、计划、开发日志和本地证据；尚不包含可发布的完整应用或公开部署产物。
- 代码、接口、数据和展示材料均从零实现，只使用公开或合成数据，不复制或依赖任何原单位资产。
- 性能、准确率、成本和稳定性数字只能引用可复现评测的实测结果；未通过发布门禁前不宣称已经上线。
- 只完成并发布 OperCerta 后，才开始下一个项目 ForenTrail。
