# OperCerta 文档索引

最后核验：2026-07-16，Task 5 书面规格与聚焦 TDD 计划已完成；下一步从非法快照 RED 开始实施。

本文件是 OperCerta 重要文档的中文目录，不复制正文。自动压缩或新会话开始时先阅读本文件，再按“优先级”读取当前状态、过程日志、相关决策、交接和实施计划。

| 路径 | 用途 | 状态 | 最后核验 commit | 优先级 |
| --- | --- | --- | --- | --- |
| `README.md` | 项目概览与使用边界 | 需要随最小纵向闭环同步 | `a0564b1` | 2 |
| `IMPLEMENTATION_HANDOFF.md` | 会话交接与下一动作 | 已同步至 Task 5 计划完成与 RED 待开始 | 本次提交 | 3 |
| `docs/specs/2026-07-14-agent-project-naming-design.md` | 命名设计 | 已冻结基线 | `c7fa618` | 4 |
| `docs/specs/AI_Agent四项目总体设计规格.md` | 总体设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-agent-portfolio-design.md` | 组合设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-opercerta-design.md` | OperCerta 详细设计 | 已冻结基线 | `48d299c` | 4 |
| `docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md` | 本机数据库环境决策 | 已确认 | `51c1583` | 4 |
| `docs/superpowers/specs/2026-07-15-development-log-design.md` | 开发日志与上下文恢复规则 | 已确认 | `a0564b1` | 1 |
| `docs/superpowers/specs/2026-07-15-approval-domain-contract-design.md` | 审批领域契约与原子竞态边界 | 已确认 | `3c55f3b` | 1 |
| `docs/superpowers/specs/2026-07-16-work-order-idempotency-contract-design.md` | Task 4 幂等工单领域契约与竞态边界 | 已确认 | `9c71d7b` | 1 |
| `docs/superpowers/specs/2026-07-16-langgraph-restart-recovery-design.md` | Task 5 LangGraph 四点重启恢复契约 | 已确认 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` | 可靠性内核 TDD 总计划 | Task 4 完成；Task 5 计划完成、实现未开始 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md` | Task 5 四点重启恢复可执行 TDD 计划 | 已完成并自审；待执行 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-work-order-idempotency.md` | Task 4 幂等工单可执行 TDD 计划 | 已执行；证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` | PostgreSQL 环境计划 | 本机安装、连接与文档同步已完成 | `84a7b08` | 2 |
| `docs/superpowers/plans/2026-07-15-development-log-bootstrap.md` | 日志初始化计划 | 执行记录见开发日志 | `6c97d5d` | 1 |
| `docs/development-log/README.md` | 日志机制说明 | 已初始化 | `f70411f` | 1 |
| `docs/development-log/current-state.md` | 当前已验证状态 | 已同步至 Task 5 计划完成、代码未开始 | 本次提交 | 1 |
| `docs/development-log/daily/2026-07-15.md` | 当日过程记录 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/daily/2026-07-16.md` | 当日过程记录 | 已记录 Task 4 实施与 Task 5 设计落盘 | 本次提交 | 2 |
| `docs/development-log/decisions/2026-07-15-windows-native-postgres.md` | 环境架构决策 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/decisions/2026-07-16-risk-based-review-and-progress-control.md` | 风险分级复核、进度口径与纵向闭环保护 | 已采用 | 本次提交 | 1 |
| `docs/release-evidence/native-postgres-environment.md` | 本机数据库环境核验证据 | 已记录；不代表发布通过 | `fc974f5` | 2 |
| `docs/release-evidence/approval-atomicity.md` | PostgreSQL 迁移与审批竞态实测证据 | 已记录；本地密码已轮换复验 | `cb23362` | 1 |
| `docs/release-evidence/work-order-idempotency.md` | Task 4 幂等工单与十路并发实测证据 | 已记录；不代表发布通过 | 本次提交 | 1 |

## 计划创建

未来的 `docs/release-evidence/` 文件只在实际测试或发布验证产生可复查证据后创建。该目录不能替代 `docs/development-log/`，也不能在发布门禁关闭时被写成已完成发布。

## 维护规则

- 新增、移动、废弃或改变重要文档状态时，在同一 Git commit 更新本索引。
- 索引只列出已存在的文件；计划创建的目录只以普通文字说明，不伪造 Markdown 链接。
- 索引不保存密码、token、API key、私有连接串、真实客户数据或模型内部推理。
- 日志、Git、测试或实际服务状态冲突时，以新鲜命令输出为准，并在当日过程日志记录更正。
