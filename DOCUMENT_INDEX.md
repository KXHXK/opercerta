# OperCerta 文档索引

新增已确认规格：`docs/superpowers/specs/2026-07-19-portfolio-netlify-static-mirror-design.md`（将既有 Vinext/Sites 作品集导出为独立 Netlify 静态镜像，解决当前 Sites 公网 403；只提供公开作品集入口与 OperCerta 静态专题跳转，不提供公开业务写入，原发布门禁保持关闭）。
新增待执行计划：`docs/superpowers/plans/2026-07-19-portfolio-netlify-static-mirror.md`（独立静态导出器、HTML/资源失败闭环、Netlify preview/production 验证与事实日志；不改现有 Sites 源码或 OperCerta 产品发布边界）。

新增已确认规格：`docs/superpowers/specs/2026-07-18-github-actions-ci-security-gate-design.md`（Private GitHub 仓库、分层 Actions、PostgreSQL 18、前后端门禁、Compose smoke、供应链固定与主分支保护；实施计划已创建）。

新增已执行计划：`docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md`（仓库安全扫描器、四个快速 job、main Compose smoke、Private remote、真实 Actions、主分支保护能力核验与证据交接六项任务）。

新增验证证据：`docs/release-evidence/github-actions-ci.md`（Private remote、PR/main 真实 Actions、339 条后端回归、前端门禁、Compose 重启恢复和分支保护 HTTP 403 能力限制；发布门禁仍关闭）。

新增验证证据：`docs/release-evidence/public-portfolio-showcase.md`（本地合成库存审批、唯一工单、审计序列 1–10、静态专题、Netlify 生产 URL/资源指纹，以及 PR/main 远程门禁；原发布门禁仍关闭）。

新增公开展示设计与计划：`docs/superpowers/specs/2026-07-18-public-portfolio-showcase-design.md`、`docs/superpowers/plans/2026-07-18-public-portfolio-showcase.md`；面试流程见 `docs/demo-script.md`。静态专题已部署至 <https://opercerta-kxh.netlify.app>，原发布门禁仍关闭。

新增已实施规格：`docs/superpowers/specs/2026-07-18-observability-security-regression-design.md`（服务端请求关联、安全结构化日志、低基数 Prometheus 指标与安全回归；本地门禁已通过）。

新增已执行计划：`docs/superpowers/plans/2026-07-18-observability-security-regression.md`（FastAPI 补丁升级、请求上下文、安全 JSON 日志、低基数指标、HTTP/SSE 集成与完整门禁的七项原子任务）。

新增验证证据：`docs/release-evidence/observability-security-regression.md`（332 条后端回归、安全断言、前端防回退和已知限制；发布门禁仍关闭）。

新增验证证据：`docs/release-evidence/single-page-console.md`（本地单页运营控制台的前端测试与构建；不代表完整端到端或公开发布）。

新增开发日志：`docs/development-log/daily/2026-07-18.md`（前端 TDD、测试隔离诊断、依赖问题与真实验证结果）。

新增开发日志：`docs/development-log/daily/2026-07-19.md`（公开专题最终本地门禁、Ruff `I001` 根因与完整重跑证据）。

新增已实施规格：`docs/superpowers/specs/2026-07-17-demo-jwt-rbac-design.md`（本地演示 JWT、RBAC 与审批身份边界；本地验证已完成）。

新增已执行计划：`docs/superpowers/plans/2026-07-17-demo-jwt-rbac.md`（本地 JWT/RBAC 的四项 TDD 实施任务）。

新增验证证据：`docs/release-evidence/demo-jwt-rbac.md`（本地 JWT/RBAC、Compose smoke 与重启恢复；不代表公开发布）。

新增待实施规格：`docs/superpowers/specs/2026-07-18-replenishment-contract-evaluation-design.md`（30 条库存补货固定合成契约评测与反偏差规则）。

新增待执行计划：`docs/superpowers/plans/2026-07-18-replenishment-contract-evaluation.md`（固定 30 条契约评测的 TDD 实施任务）。

新增证据：`docs/release-evidence/replenishment-contract-evaluation.md`（固定 30 条本地合成契约评测；30 passed、0 failed；不代表公开发布）。

最后核验：2026-07-18，Private `KXHXK/opercerta` 已建立，PR run `29642286517` 的四个快速门禁通过，main run `29642363033` 的五个 job（含 Compose 业务 smoke 与重启恢复）通过；Private 分支保护因账户能力返回 HTTP 403，未启用且采用人工 PR 规则；发布门禁仍关闭。

本文件是 OperCerta 重要文档的中文目录，不复制正文。自动压缩或新会话开始时先阅读本文件，再按“优先级”读取当前状态、过程日志、相关决策、交接和实施计划。

| 路径 | 用途 | 状态 | 最后核验 commit | 优先级 |
| --- | --- | --- | --- | --- |
| `README.md` | 项目概览与使用边界 | 已同步静态专题 URL、远程门禁与剩余发布边界 | 本次提交 | 2 |
| `IMPLEMENTATION_HANDOFF.md` | 会话交接与下一动作 | 已同步静态部署证据、远程 CI 与下一边界 | 本次提交 | 3 |
| `docs/specs/2026-07-14-agent-project-naming-design.md` | 命名设计 | 已冻结基线 | `c7fa618` | 4 |
| `docs/specs/AI_Agent四项目总体设计规格.md` | 总体设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-agent-portfolio-design.md` | 组合设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-opercerta-design.md` | OperCerta 详细设计 | 已冻结基线 | `48d299c` | 4 |
| `docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md` | 本机数据库环境决策 | 已确认 | `51c1583` | 4 |
| `docs/superpowers/specs/2026-07-15-development-log-design.md` | 开发日志与上下文恢复规则 | 已确认 | `a0564b1` | 1 |
| `docs/superpowers/specs/2026-07-15-approval-domain-contract-design.md` | 审批领域契约与原子竞态边界 | 已确认 | `3c55f3b` | 1 |
| `docs/superpowers/specs/2026-07-16-work-order-idempotency-contract-design.md` | Task 4 幂等工单领域契约与竞态边界 | 已确认 | `9c71d7b` | 1 |
| `docs/superpowers/specs/2026-07-16-langgraph-restart-recovery-design.md` | Task 5 LangGraph 四点重启恢复契约 | 已确认 | 本次提交 | 1 |
| `docs/superpowers/specs/2026-07-16-inventory-replenishment-vertical-slice-design.md` | 库存不足到补货工单真实 MCP 后端纵向闭环 | 已确认；实施计划已创建 | 本次提交 | 1 |
| `docs/superpowers/specs/2026-07-16-docker-linux-runtime-design.md` | Docker/Linux、健康检查与 Ubuntu VM 运行时边界 | 已确认；实施计划已创建 | 本次提交 | 1 |
| `docs/superpowers/specs/2026-07-17-wsl2-runtime-amendment-design.md` | WSL2 Ubuntu 26.04 环境修订、Docker 包来源与 registry mirror 例外 | 已确认；基础拉取已验证 | 本次提交 | 1 |
| `docs/superpowers/specs/2026-07-18-observability-security-regression-design.md` | 请求关联、安全日志、低基数指标与安全回归设计 | 已实施并完成本地门禁 | `29b2c97` | 1 |
| `docs/superpowers/specs/2026-07-18-github-actions-ci-security-gate-design.md` | Private GitHub Actions 分层 CI 安全门禁设计 | 已实施并完成远程门禁 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` | 可靠性内核 TDD 总计划 | Task 1–6 已执行 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md` | Task 5 四点重启恢复可执行 TDD 计划 | 已执行；证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-work-order-idempotency.md` | Task 4 幂等工单可执行 TDD 计划 | 已执行；证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md` | 首个库存补货后端纵向闭环可执行 TDD 计划 | Task 1–9 已执行 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-17-docker-linux-runtime.md` | Docker/Linux 运行时可执行 TDD 计划 | 已执行；Compose 证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` | PostgreSQL 环境计划 | 本机安装、连接与文档同步已完成 | `84a7b08` | 2 |
| `docs/superpowers/plans/2026-07-15-development-log-bootstrap.md` | 日志初始化计划 | 执行记录见开发日志 | `6c97d5d` | 1 |
| `docs/superpowers/plans/2026-07-18-observability-security-regression.md` | 可观测性与安全回归七项原子 TDD 计划 | 已执行；证据已归档 | `db69f71` | 1 |
| `docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md` | Private GitHub Actions CI 安全门禁实施计划 | 已执行；远程证据已归档 | 本次提交 | 1 |
| `docs/development-log/README.md` | 日志机制说明 | 已初始化 | `f70411f` | 1 |
| `docs/development-log/current-state.md` | 当前已验证状态 | 已同步 Private remote、真实 Actions 与剩余发布边界 | 本次提交 | 1 |
| `docs/development-log/interview-casebook.md` | 实施问题、诊断、修复与面试复盘案例 | 已初始化；只记录真实证据和限制 | 本次提交 | 1 |
| `docs/development-log/learning-method.md` | 学习掌握、单变量实验与面试训练方法 | 已初始化；后续随实施持续补充 | 本次提交 | 1 |
| `docs/development-log/daily/2026-07-15.md` | 当日过程记录 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/daily/2026-07-16.md` | 当日过程记录 | 已记录库存补货 Task 1–9 实施、调试与验证 | 本次提交 | 2 |
| `docs/development-log/daily/2026-07-18.md` | 当日过程记录 | 已记录前端、可观测性与 GitHub Actions 实施证据 | 本次提交 | 2 |
| `docs/development-log/decisions/2026-07-15-windows-native-postgres.md` | 环境架构决策 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/decisions/2026-07-16-risk-based-review-and-progress-control.md` | 风险分级复核、进度口径与纵向闭环保护 | 已采用 | 本次提交 | 1 |
| `docs/release-evidence/native-postgres-environment.md` | 本机数据库环境核验证据 | 已记录；不代表发布通过 | `fc974f5` | 2 |
| `docs/release-evidence/approval-atomicity.md` | PostgreSQL 迁移与审批竞态实测证据 | 已记录；本地密码已轮换复验 | `cb23362` | 1 |
| `docs/release-evidence/work-order-idempotency.md` | Task 4 幂等工单与十路并发实测证据 | 已记录；不代表发布通过 | 本次提交 | 1 |
| `docs/release-evidence/langgraph-restart-recovery.md` | Task 5 四点 A/B 重启恢复与 checkpointer 实测证据 | 已记录；不代表发布通过 | 本次提交 | 1 |
| `docs/release-evidence/reliability-kernel.md` | Task 1–6 可靠性内核新鲜总门禁与下一边界 | 已验证本地内核；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/replenishment-execution-restart.md` | Task 7 审批后执行、写后读与 A/B 重启证据 | 已记录；不代表发布通过 | 本次提交 | 1 |
| `docs/release-evidence/inventory-replenishment-vertical-slice.md` | 库存补货 Task 1–9 后端纵向闭环总证据 | Windows 本地后端闭环已验证；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/docker-linux-runtime.md` | WSL2 Ubuntu Compose 健康、业务 smoke 与重启恢复证据 | 单节点本地验证通过；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/single-page-console.md` | 本地单页运营控制台测试与构建证据 | 本地前端验证通过；不代表公开发布 | `f88ddc5` | 1 |
| `docs/release-evidence/observability-security-regression.md` | request_id、安全日志、低基数指标与安全回归证据 | 本地门禁通过；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/github-actions-ci.md` | Private remote、PR/main 分层 CI、Compose 重启恢复与保护能力证据 | 远程门禁通过；分支保护受账户能力限制；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/public-portfolio-showcase.md` | 公开专题的本地审批、工单、审计、截图与线上部署证据 | 静态 URL 已验证；原发布门禁仍关闭 | 本次提交 | 1 |

## 计划创建

未来的 `docs/release-evidence/` 文件只在实际测试或发布验证产生可复查证据后创建。该目录不能替代 `docs/development-log/`，也不能在发布门禁关闭时被写成已完成发布。

## 维护规则

- 新增、移动、废弃或改变重要文档状态时，在同一 Git commit 更新本索引。
- 索引只列出已存在的文件；计划创建的目录只以普通文字说明，不伪造 Markdown 链接。
- 索引不保存密码、token、API key、私有连接串、真实客户数据或模型内部推理。
- 日志、Git、测试或实际服务状态冲突时，以新鲜命令输出为准，并在当日过程日志记录更正。
