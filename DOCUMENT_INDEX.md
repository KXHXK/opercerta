# OperCerta 文档索引

新增 Agent Task 9 总证据：`docs/release-evidence/agent-core-architecture.md`（后端 566 条、前端 46 条、Agent 评测 9/9、真实 FastEmbed/pgvector RAG、Compose 三业务与重启恢复通过；后续已修复 Kimi replan 重复工具与 provider 异常 operation 原子收口，新鲜 unit 352 条/关键图集成 7 条，Draft PR run `29946792369` 完整后端 573 条与 Agent 评测 9/9；Real Kimi 完整 Compose 仍 failed，未回退 Mock）。review/main Compose 仍待完成，发布门禁保持 `CLOSED`。问题与修复见 `docs/development-log/daily/2026-07-23.md`。

Agent Task 8 证据：`docs/release-evidence/agent-workspace.md`（有限表单、Goal、真实 Agent Trace、MCP/RAG 引用、模型建议/确定性计划、审批/Verifier、工单与角色接力；前端 46 条、生产构建和 1440/1024/390 响应式检查通过）。

新增 Agent Task 7 证据：`docs/release-evidence/agent-trace-rbac.md`（Agent run/event/citation 持久化、序列与语义去重、脱敏、RAG 引用、恢复不重复、Trace snapshot/SSE 与 operation 级 RBAC；产品 545 条、最新定向 8 条与 Git 安全 4 条通过，Task 8--9 和生产门禁仍未完成）。Agent 核心计划 Task 1--7 已执行，Task 8--10 待执行。

新增 Agent Task 6 证据：`docs/release-evidence/agent-pgvector-rag.md`（pgvector 迁移、三份合成中文 SOP、FastEmbed、MCP RAG、LangGraph citation、降级/失败关闭、535+4 条回归与真实三场景检索；完整 Compose restart smoke 仍待 Task 9 在稳定 WSL 终端重跑，发布门禁保持 `CLOSED`）。对应过程日志：`docs/development-log/daily/2026-07-22.md`。

新增已批准、正在实施规格：`docs/superpowers/specs/2026-07-21-opercerta-agent-core-architecture-design.md`（将现有可靠工单工作流增强为受控 Plan-and-Execute Agent，补齐 Perception、Core LLM、Planning、Memory/pgvector、MCP Tools、Execution/Feedback、Prompt、Harness、RAG、Agent Trace 与角色控制台；保留审批、幂等、恢复和发布门禁）。对应十项 Inline TDD 计划：`docs/superpowers/plans/2026-07-21-opercerta-agent-core-architecture.md`。

新增零成本求职展示证据：`docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md`（公开静态专题、本地 `/engineering` 工程详解和 `/console` 控制台；前端 40 条、后端 430 条、Mock Compose 重启恢复与三档浏览器复核通过；PR #6 已合并，`main` 五个门禁及两个 Netlify 生产站已验证）。对应规格和计划为 `docs/superpowers/specs/2026-07-20-opercerta-zero-cost-showcase-engineering-walkthrough-design.md`、`docs/superpowers/plans/2026-07-20-opercerta-zero-cost-showcase-engineering-walkthrough.md`。

新增真实模型证据：`docs/release-evidence/real-model-representative-validation.md`（Moonshot AI `kimi-k2.6` 三业务 6 次代表操作/3 条真实模型路径；记录端到端耗时、无原文/密钥/token/成本虚构，并保留模型兼容、分层超时和凭据轮换复盘）。

新增本地发布候选证据：`docs/release-evidence/three-business-release.md`（提交 `a3994ef` 的 Caddy/release Compose、422 条后端回归、前端 25 条测试、一键三业务与重启 smoke；真实模型随后由独立证据补齐，公网交互和生产治理仍未完成）。

新增缓存矩阵独立证据：`docs/release-evidence/performance-cache-matrix.md`（12 格、60 次 query 的实际 MCP/cache hit 与本机延迟，明确小样本不构成生产性能承诺）。

新增中文学习包：`docs/learning/OperCerta核心技术手册.md`、`docs/learning/OperCerta手动实验手册.md`、`docs/learning/OperCerta面试讲解.md`（请求全链路、手动故障实验与 30 秒/3 分钟/10 分钟面试表达）。

新增阶段证据：`docs/release-evidence/three-business-evaluation-compose.md`（42 条三业务固定评测、Compose 三业务/重启恢复，以及 12 格真实缓存矩阵；明确本机小样本边界）。三业务主计划 Task 7 已执行，Task 8 本地阶段随后完成。

Agent 核心架构阶段证据：`docs/release-evidence/agent-verifier-reapproval.md`（批准后 Verifier、审批周期、复审恢复、竞态和幂等执行；后续 Task 6 RAG 与 Task 7 Trace 已分别完成，发布门禁仍保持关闭）。

新增已确认规格：`docs/superpowers/specs/2026-07-20-opercerta-three-business-release-design.md`（将 OperCerta 收口范围固定为库存补货、设备维修、作业异常恢复三个真实闭环；共享 LangGraph 可靠性内核，并把六个 MCP 工具、Redis、OpenTelemetry、真实模型代表性验证、交互部署和中文学习包纳入门禁）。
新增执行中计划：`docs/superpowers/plans/2026-07-20-opercerta-three-business-release.md`（Task 1–7、Task 8 本地发布/学习和真实模型代表性验证已完成；公网交互、用户掌握与最终远程门禁待完成；采用 Inline Execution）。

新增阶段证据：`docs/release-evidence/cache-tracing-model-adapter.md`（Redis 安全旁路与审批后绕过、OpenTelemetry 脱敏关联、严格真实模型 adapter 和未验证边界；生产发布门禁仍关闭）。

新增已确认规格：`docs/superpowers/specs/2026-07-19-portfolio-netlify-static-mirror-design.md`（将既有 Vinext/Sites 作品集导出为独立 Netlify 静态镜像，解决当前 Sites 公网 403；只提供公开作品集入口与 OperCerta 静态专题跳转，不提供公开业务写入，原发布门禁保持关闭）。
新增已执行计划：`docs/superpowers/plans/2026-07-19-portfolio-netlify-static-mirror.md`（独立静态导出器、HTML/资源失败闭环、Netlify preview/production 验证与事实日志；不改现有 Sites 源码或 OperCerta 产品发布边界）。

新增验证证据：`docs/release-evidence/portfolio-netlify-static-mirror.md`（Sites 公网 403 对照、静态导出测试、Netlify preview/production deploy id、HTTPS 与浏览器核验；原发布门禁仍关闭）。

新增已确认规格：`docs/superpowers/specs/2026-07-18-github-actions-ci-security-gate-design.md`（设计时采用 Private GitHub 仓库，建立分层 Actions、PostgreSQL 18、前后端门禁、Compose smoke、供应链固定与主分支保护；仓库后来已由用户改为 public）。

新增已执行计划：`docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md`（仓库安全扫描器、四个快速 job、main Compose smoke、初始 Private remote、真实 Actions、主分支保护能力核验与证据交接六项任务）。

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

最后核验：2026-07-20，`KXHXK/opercerta` 已为 public；提交 `bbb67c9` 的 main run `29682353256` 成功。main branch protection 尚未配置，继续采用人工全绿后合并规则；生产发布门禁仍关闭。

本文件是 OperCerta 重要文档的中文目录，不复制正文。自动压缩或新会话开始时先阅读本文件，再按“优先级”读取当前状态、过程日志、相关决策、交接和实施计划。

| 路径 | 用途 | 状态 | 最后核验 commit | 优先级 |
| --- | --- | --- | --- | --- |
| `README.md` | 项目概览与使用边界 | 已同步三业务、本地发布候选、学习入口与剩余门禁 | `a3994ef` | 2 |
| `IMPLEMENTATION_HANDOFF.md` | 会话交接与下一动作 | 已同步真实模型验证与公网发布下一边界 | 本次提交 | 3 |
| `docs/superpowers/specs/2026-07-20-opercerta-zero-cost-showcase-engineering-walkthrough-design.md` | 零成本公开专题、本地工程详解与发布边界 | 已确认并完成本机实施门禁 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-20-opercerta-zero-cost-showcase-engineering-walkthrough.md` | 零成本展示与工程详解八项 TDD 计划 | Task 1--8 已执行；主线与 Netlify 同步完成 | 本次提交 | 1 |
| `docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md` | 新版展示、工程详解、Mock Compose、响应式和远程/生产证据 | PR #6、main Compose 与两个 Netlify 生产站已验证 | 本次提交 | 1 |
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
| `docs/superpowers/specs/2026-07-19-portfolio-netlify-static-mirror-design.md` | 作品集 Netlify 独立静态镜像设计 | 已实施并完成公网验证 | 本次提交 | 1 |
| `docs/superpowers/specs/2026-07-20-opercerta-three-business-release-design.md` | 三业务闭环、技术栈补齐、求职发布与学习交付修订 | 已确认；实施计划已创建 | `632f0a1` | 1 |
| `docs/superpowers/specs/2026-07-21-opercerta-agent-core-architecture-design.md` | 六层 Agent 核心架构、Plan-and-Execute、Harness、pgvector Memory、RAG 与 Agent Trace 纠偏 | 已确认；已按有界循环、最小 LangChain 和 RAG 边界修订 | `bf3b6da` + 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-21-opercerta-agent-core-architecture.md` | Agent 核心架构十项 Inline TDD 实施计划 | Task 1--10 与 replan/异常原子收口快速 CI 已完成；凭据轮换、review/main Compose 待完成 | `221fe3d` + 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-20-opercerta-three-business-release.md` | 三业务求职发布八项 Inline TDD 主计划 | 真实模型代表性验证已执行；公网和远程门禁待完成 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` | 可靠性内核 TDD 总计划 | Task 1–6 已执行 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-langgraph-restart-recovery.md` | Task 5 四点重启恢复可执行 TDD 计划 | 已执行；证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-work-order-idempotency.md` | Task 4 幂等工单可执行 TDD 计划 | 已执行；证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md` | 首个库存补货后端纵向闭环可执行 TDD 计划 | Task 1–9 已执行 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-17-docker-linux-runtime.md` | Docker/Linux 运行时可执行 TDD 计划 | 已执行；Compose 证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` | PostgreSQL 环境计划 | 本机安装、连接与文档同步已完成 | `84a7b08` | 2 |
| `docs/superpowers/plans/2026-07-15-development-log-bootstrap.md` | 日志初始化计划 | 执行记录见开发日志 | `6c97d5d` | 1 |
| `docs/superpowers/plans/2026-07-18-observability-security-regression.md` | 可观测性与安全回归七项原子 TDD 计划 | 已执行；证据已归档 | `db69f71` | 1 |
| `docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md` | Private GitHub Actions CI 安全门禁实施计划 | 已执行；远程证据已归档 | 本次提交 | 1 |
| `docs/superpowers/plans/2026-07-19-portfolio-netlify-static-mirror.md` | 作品集静态导出与 Netlify 两阶段发布计划 | 已执行；公网证据已归档 | 本次提交 | 1 |
| `docs/development-log/README.md` | 日志机制说明 | 已初始化 | `f70411f` | 1 |
| `docs/development-log/current-state.md` | 当前已验证状态 | 已同步真实模型代表性验证与剩余外部门禁 | 本次提交 | 1 |
| `docs/development-log/interview-casebook.md` | 实施问题、诊断、修复与面试复盘案例 | 已补充 Agent、RAG、Trace 与 CI pgvector 漂移案例 | 本次提交 | 1 |
| `docs/development-log/daily/2026-07-23.md` | Agent 核心 Draft PR、CI/replan/异常收口根因、RED/GREEN 修复与 Real 诊断 | run `29946792369` 快速 job 全绿；凭据轮换、review/main Compose 待完成 | 本次提交 | 1 |
| `docs/development-log/learning-method.md` | 学习掌握、单变量实验与面试训练方法 | 已加入三业务学习包和手动闭环建议 | `a3994ef` | 1 |
| `docs/learning/OperCerta核心技术手册.md` | 一次请求的全技术链路、可靠性设计与技术边界 | 本地学习交付已完成；需用户实践 | `a3994ef` | 1 |
| `docs/learning/OperCerta手动实验手册.md` | WSL2/Compose/业务/规则/MCP 故障的手动实验 | 命令已记录；用户掌握检查待执行 | `a3994ef` | 1 |
| `docs/learning/OperCerta面试讲解.md` | 30 秒、3 分钟、10 分钟表达和常见追问 | 材料已完成；需用户口述训练 | `a3994ef` | 1 |
| `docs/release-evidence/agent-core-architecture.md` | Agent 核心 Task 9 新鲜本地门禁、Mock/Real/RAG 边界与 blocker | replan/异常收口及快速 CI 通过；Real Kimi 完整 Compose、review/main Compose 未完成 | `221fe3d` + 本次提交 | 1 |
| `docs/development-log/daily/2026-07-15.md` | 当日过程记录 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/daily/2026-07-16.md` | 当日过程记录 | 已记录库存补货 Task 1–9 实施、调试与验证 | 本次提交 | 2 |
| `docs/development-log/daily/2026-07-18.md` | 当日过程记录 | 已记录前端、可观测性与 GitHub Actions 实施证据 | 本次提交 | 2 |
| `docs/development-log/daily/2026-07-19.md` | 当日过程记录 | 已记录公开专题门禁与作品集静态镜像发布 | 本次提交 | 2 |
| `docs/development-log/daily/2026-07-20.md` | 当日过程记录 | 已记录三业务 Task 1–8、发布调试与当前门禁 | 本次提交 | 2 |
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
| `docs/release-evidence/cache-tracing-model-adapter.md` | Redis 只读缓存、OpenTelemetry 与 Real model adapter 阶段证据 | adapter 阶段证据；真实模型运行随后由独立证据补齐 | 本次提交 | 1 |
| `docs/release-evidence/three-business-evaluation-compose.md` | 42 条三业务评测、Compose 重启恢复与 2×2 缓存矩阵证据 | 本地 Task 7 通过；不代表生产发布 | 本次提交 | 1 |
| `docs/release-evidence/agent-verifier-reapproval.md` | 三业务批准后 Verifier、复审周期、恢复、竞态和幂等写证据 | Agent Task 5 本地通过；不代表生产发布 | 本次提交 | 1 |
| `docs/release-evidence/performance-cache-matrix.md` | 12 格缓存/工具模式的 MCP、hit 和本机延迟证据 | 60 次 query 已测；不作生产性能承诺 | 本次提交 | 1 |
| `docs/release-evidence/three-business-release.md` | Caddy/release Compose、本地总门禁与一键发布候选 smoke | 本地候选通过；真实模型已另证，公网交互待完成 | 本次提交 | 1 |
| `docs/release-evidence/real-model-representative-validation.md` | 三业务真实模型代表性验证、兼容调试与安全边界 | 本地 6 次代表操作通过；公网/生产仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/github-actions-ci.md` | 初始 Private remote、PR/main 分层 CI、Compose 重启恢复与保护能力历史证据 | 远程门禁通过；仓库现为 public，main 保护尚未配置；发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/public-portfolio-showcase.md` | 公开专题的本地审批、工单、审计、截图与线上部署证据 | 静态 URL 已验证；原发布门禁仍关闭 | 本次提交 | 1 |
| `docs/release-evidence/portfolio-netlify-static-mirror.md` | Sites 403 对照、作品集静态导出与 Netlify 发布证据 | 公开作品集 URL 已验证；原发布门禁仍关闭 | 本次提交 | 1 |

## 计划创建

未来的 `docs/release-evidence/` 文件只在实际测试或发布验证产生可复查证据后创建。该目录不能替代 `docs/development-log/`，也不能在发布门禁关闭时被写成已完成发布。

## 维护规则

- 新增、移动、废弃或改变重要文档状态时，在同一 Git commit 更新本索引。
- 索引只列出已存在的文件；计划创建的目录只以普通文字说明，不伪造 Markdown 链接。
- 索引不保存密码、token、API key、私有连接串、真实客户数据或模型内部推理。
- 日志、Git、测试或实际服务状态冲突时，以新鲜命令输出为准，并在当日过程日志记录更正。
