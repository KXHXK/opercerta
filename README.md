# OperCerta｜智能运营处置 Agent

OperCerta 是面向库存异常、设备告警和运营工单的智能运营处置 Agent 独立作品仓库。

> 当前状态：可靠性内核已在 Windows 原生 PostgreSQL 环境完成本地验证；完整 OperCerta 产品与发布门禁尚未完成。

## 当前已验证范围

- 严格非法输入与 JSON-only 恢复快照；
- 确定性恢复决策矩阵；
- PostgreSQL Schema、Alembic 升降级和审批原子竞态；
- 授权后幂等工单写入与并发安全重放；
- 独立 `langgraph` Schema checkpointer；
- LangGraph interrupt、批准/拒绝路径和四点 A/B 重启恢复。

新鲜总门禁与限制见 [可靠性内核证据](docs/release-evidence/reliability-kernel.md)。这不是完整五工具、API、前端、评测、Docker/Linux 或公开部署完成声明。

## 下一实施边界

下一阶段仍只实施 OperCerta，建立 event → evidence → risk/plan → approval → simulated MCP write → verification → audit → API response 的最小纵向闭环。可靠性内核在当前范围冻结，不继续增加与纵向闭环无关的底层功能。

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
