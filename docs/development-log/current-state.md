# OperCerta 当前状态

## 2026-07-27：PR #8、main Compose 与新版静态专题已发布

单根 Agent Loop 与 case 工作台在 [PR #8](https://github.com/KXHXK/opercerta/pull/8) 合并为 `609f8f7dcbfbadb9d12f4371cf49815d48884a4e`。对应 [main run 30203438564](https://github.com/KXHXK/opercerta/actions/runs/30203438564) 的 `repository-safety`、`python-quality`、`backend-tests`、`frontend`、`compose-smoke` 全部成功；Compose 实际完成容器构建启动、Agent 轨迹与数据库副作用、API/MCP 重启、重启恢复和清理。

已验证静态候选 deploy `6a660a8f77aa692302ad00aa`，随后经用户批准发布 production deploy `6a6631d24958714a43ddc508`：<https://opercerta-kxh.netlify.app>。生产根页、独立 deploy URL、`/console` 与 `/api/v1/auth/demo-token` 均为 `200 text/html`；JS 资源为 `index-Ckvsq13U.js`，线上 SHA-256 `dcd31a4d6e1c53f06c1a16cc6fb65f7f5d347926a078dc56fe08606c8052abb1` 与本地候选一致。`/api/*` 返回静态 SPA HTML 是刻意的无后端边界，不代表 API 上线。上一生产 deploy `6a5e0bb5563acf4706a09c0d` 保留为回滚点。

当前完成的是“公开静态求职专题 + 本地可运行完整业务闭环”，不是公网可写生产系统。生产 IAM、公网 HTTPS API、托管 PostgreSQL/Redis、限流、防滥用、备份、高可用、自动部署和正式 Release Tag 仍未完成，发布门禁继续 `CLOSED`。下一步是用户手动运行与源码掌握验收、面试材料和 Release Tag 决策；未完成前不启动 ForenTrail。

## 2026-07-26 单根 Agent Loop 架构纠偏已批准，Task 0–3 完成

用户在真实控制台复核中指出：当前 LLM 没有形成“决策 → 工具 → Observation → 再决策”的 Agent 核心循环；LangGraph 调查图、Python 包装器和三个场景图被串联使用，完整 operation 并非由一个根图拥有；Redis 也只包裹旧场景初读，没有进入统一的 MCP Observation 链路。前端同时把 predecessor/successor signal 平铺为主卡片，并用全局详情和 busy 状态驱动交互，造成多卡、串卡和业务谱系失真。

完整复核四份原始设计、2026-07-21 Agent 核心设计和当前实现后确认：这不是用户临时改变需求，而是实现没有兑现已经批准的“LangGraph 唯一编排运行时 + AgentHarness ToolLoop”。可靠性内核仍有效并继续保留，包括 PostgreSQL 事实、signal 认领/对账、RBAC、审批竞态、批准后刷新、Verifier、事实绑定、幂等工单、MCP/RAG 和重启恢复；必须重构的是编排所有权、模型—工具循环、Redis 接入位置和 React case 状态模型。

纠偏规格 `docs/superpowers/specs/2026-07-26-single-root-agent-loop-and-case-workspace-design.md` 已获用户批准。Task 0 基线为 71 条可靠性单元测试和一次性 PostgreSQL 上 43 条审批/幂等/signal/恢复集成测试通过。Task 1 先观测 `AgentTurn` 缺失 RED，再新增 ToolDecision/FinalAnalysis 互斥联合契约和累计预算校验；定向 33 条通过。Task 2 先观测统一缓存结果缺失 RED，再新增 `CachedReadToolGateway` 和 `hit/miss/bypass/unavailable` Observation；相关范围 76 条通过，一次性 PostgreSQL 上 Agent 图/RAG/重启恢复 11 条通过。最终使用 `PYTHONPATH=.:src` 和 `set -euo pipefail` 复跑完整单元套件 `386 passed in 34.14s`，全项目 Ruff、Mypy 81 个源文件及 `git diff --check` 通过。

Task 3 已新增默认关闭的库存 `InventoryAgentRootGraph` 和 `AgentLoopModelGateway.decide` 协议。查询测试证明模型依次看到 0、1、2 条 Observation 后选择库存、规则并形成最终分析；创建路径在同一根图和 `thread_id` 停在原生 `approval_interrupt`。证据不足、引用不匹配和写工具均安全失败。一次性 PostgreSQL checkpointer 定向 `6 passed`；包含旧 Agent 图的完整回归 `398 passed in 35.32s`，全项目 Ruff、Mypy 82 个源文件和 diff 检查通过。

当前根图只到审批中断，尚未接入审批提交后的刷新、Verifier、绑定和幂等写入；候选必须显式 `enabled=True`，默认 API/Compose 仍使用旧路径。未审批当前 operation、未调用 Real Kimi、未 commit/push/merge，发布门禁保持 `CLOSED`。下一步是 Task 4 审批后可靠性节点接入根图。

## 2026-07-25 异常信号入口修订

已纠正“固定对象直接创建处置”缺少业务动机的问题：新增迁移 `0007_operational_signals`、并发去重信号仓储、信号与 operation 原子认领、三业务确定性 `SignalDetector`、扫描/列表/调查 API，以及 React 异常信号箱。生产模式下 `create_work_order` 没有 `trigger_signal_id` 会返回 422；query 仍作为诊断入口。真实本地 Compose 经 Caddy 扫描三对象得到库存短缺、设备异常、任务阻塞三条信号且零数据源错误；库存信号原子绑定新 operation 并进入 `awaiting_approval`。operation 完成或拒绝时 signal 原子收口为 `resolved`，失败、过期或中止时转为 `attention_required`，形成可再次介入的反馈闭环。新鲜证据：完整后端 `600 passed in 178.48s`；前端 18 文件/`56 passed` 与 production build；Ruff、Mypy 79 个源文件通过；隔离空卷 Mock release Compose 依次验证直接写 422、三信号、三业务审批/Verifier/工单、重复审批、数据库事实以及 API/MCP 重启恢复，退出码 0、耗时 175.1 秒并自动清理。远程 CI、修订后的 Real Kimi、PR 提交/合并与生产治理尚未执行，因此发布门禁继续 `CLOSED`。

同日用户复核发现首次页面必须切角色才能扫描，而且切角色会自动读取 PostgreSQL 历史 signal，造成“扫描按钮是假的”观感。修复后首次 operator 无需预先签发 JWT即可点击；首次点击在同一动作内签发内存 JWT 并调用真实 scan API；角色切换不再调用 `GET /signals`，刷新后在扫描完成前保持空信号箱。scan 响应新增服务端 `scanned_at`，页面显示本次范围、6 次只读 MCP、命中数、去重语义和三类具体规则事实。新鲜回归为完整后端 `600 passed in 189.97s`、前端 18 文件/`56 passed`、production build、Ruff 和 Mypy 79 个源文件全绿；本地 Compose 已重建并恢复 `18080` 端口。应用内浏览器因 localhost URL 策略拒绝自动复验，需用户手动刷新做视觉确认，不能将组件测试冒充浏览器证据。

## 最新核验：前端安全边界与审批写入语义已完成本地收口

2026-07-24，规格一致性复核继续发现并修复两项端到端边界：未知后端错误码不再把原始 `message` 暴露给用户；审批 API 已成功写入但后置读取因 RBAC/网络失败时，前端明确保留“审批已提交”事实并禁用重复决定，不再误报“审批未提交”。两项均先写 RED，再以最小实现转为 GREEN。

新鲜门禁：前端 17 文件/`53 passed` 与 production build；后端 unit `356 passed`、一次性 pgvector 测试库完整套件 `579 passed in 376.68s`；Ruff、189 文件格式、Mypy 76 个源文件、114 包锁定与仓库安全扫描通过；Mock release Compose 三业务、RAG/Trace、批准后 Verifier/绑定护栏/受控写入、数据库事实和 API/MCP 重启恢复退出码 0。`.env.local` 指向的 Windows 测试库未运行，失败 traceback 再次回显 ignored 旧凭据，该值必须视为已暴露并在恢复原生测试库前轮换；本轮完整套件改用运行时随机凭据的一次性本地容器且已清理。修改尚未 commit/push；Real Kimi、PR 合并、main Compose、生产发布和 ForenTrail 均未执行，发布门禁保持 `CLOSED`。过程见 `docs/development-log/daily/2026-07-24.md`。

## 最新核验：规格一致性审计与 Agent 展示收口通过本地门禁

2026-07-23 对四份原始设计、三业务修订、Agent 核心规格、当前源码和证据逐项复核，主线仍是“传统仓储/运营工单可靠性内核 + 受控单 Agent 增强”，没有退化为普通 CRUD，也没有扩成自由聊天或多 Agent。修复了前端吞掉 401/403/409/422/503 安全 envelope、产品 Trace 缺少独立 Verifier/绑定护栏、安全业务终态仍显示 running、主角色混入未完成 demo-admin，以及空 FastEmbed cache 离线冷启动说明不完整。

新鲜本地门禁：后端 unit `356 passed in 38.86s`；前端 17 文件/`51 passed` 与 TypeScript/Vite production build；Ruff 全绿、`182 files already formatted`、Mypy 76 个源文件；Mock Compose 三业务 Agent 验证退出码 0，并新增强制 `Verifier → binding guardrail → controlled execution` 顺序断言；API/MCP 重启恢复退出码 0，四服务 healthy。独立本地测试数据库端口未监听，数据库集成 Pytest 未形成新鲜绿色结果；本轮未用环境故障冒充业务失败，Compose 的真实 PostgreSQL 断言已通过。Real Kimi、PR 合并、main Compose、生产发布和 ForenTrail 均未执行，发布门禁保持 `CLOSED`。审计见 `docs/development-log/audits/2026-07-23-spec-conformance-audit.md`。

## 最新核验：Agent 核心 Draft PR 快速门禁已通过

2026-07-23，`feat/agent-core-implementation` 的 Kimi + RAG replan 已改为只暴露尚缺工具，provider/图异常 operation 已能原子收口为固定 `dependency_unavailable`；真实图 probe 完成 inventory → knowledge → policy。新鲜本地回归为 unit 352 条、关键 Agent 图集成 7 条、Ruff/188 文件格式/Mypy 76 个源文件；Draft PR run `29946792369` 的 repository-safety、python-quality、backend-tests、frontend 全绿，完整后端 `573 passed`、三业务评测 1 条和 Agent 评测 9/9。完整 Compose Real Kimi 仍未稳定通过，最终安全证据为 create operation 503 `dependency_unavailable`；未回退 Mock。测试 traceback 曾展开的本地 PostgreSQL 测试凭据已轮换，主仓库与 worktree ignored 配置一致，并由 Windows 原生 `psql` 执行 `SELECT 1` 安全验证。生产发布门禁保持 `CLOSED`。

同日此前已创建 [Draft PR #8](https://github.com/KXHXK/opercerta/pull/8)。首次 Actions 暴露 CI 普通 PostgreSQL 镜像不含迁移要求的 vector extension；提交 `ba53e70` 用资产契约统一为 pgvector 镜像后，最新基线 run `29937375023` 的 repository-safety、python-quality、backend-tests、frontend 全部通过。PR 事件按设计跳过 `compose-smoke`；PR 尚未 review/合并，main 新鲜 Compose 和生产治理仍未完成。

## 最新核验：Agent Task 8 React 工作台已完成前端与响应式门禁

2026-07-22，Agent 核心 Task 9 已提交 `642d3ba`：本地后端 566 条、前端 46 条、冻结 Agent 评测 9/9、真实 FastEmbed/pgvector RAG、三业务 Compose 与 API/MCP 重启恢复通过。Real Moonshot/Kimi `kimi-k2.6` 新 Agent 代表 query 未通过严格规划路径，报告为 failed，未回退 Mock；异常 operation 原子收口仍是 known limitation。Task 10 中文交付与 Draft PR 快速门禁已完成，review/main Compose 仍待执行，生产发布门禁保持 `CLOSED`。详见 `docs/release-evidence/agent-core-architecture.md`。

2026-07-22，本地 `/console` 已从简易工单三栏升级为受控 Agent 工作台：固定表单、结构化 Goal、真实后端 Agent Trace、MCP/RAG 证据、模型建议与确定性计划对照、审批 binding、Verifier 说明、工单回读和 operator→approver→auditor 引导均已接入，且 audit 不再冒充 Trace。完整前端为 17 个测试文件/46 条测试，TypeScript/Vite 生产构建通过；1440/1024/390 浏览器检查无横向溢出，应用内无 fixed/sticky。Task 9 Compose/RAG/重启已在后续证据完成，Real Kimi 新 Agent 路径仍未通过，生产发布门禁保持 `CLOSED`。详见 `docs/release-evidence/agent-workspace.md` 与 `docs/release-evidence/agent-core-architecture.md`。

## 最新核验：Agent Task 7 脱敏 Trace、API/SSE 与 RBAC 已完成本地门禁

2026-07-22 Task 7 检查点：迁移 `0006_agent_trace`、run/event/citation 数据模型、稳定 sequence/semantic key、递归脱敏、LangGraph 调查/审批/执行/反馈投影、RAG citation reference、Trace snapshot/SSE API 与 operation 级 RBAC 已实现。该检查点产品代码全量测试为 545 条通过；operator owner/非 owner 权限补强后定向 8 条通过，WSL Git 安全 4 条通过。Trace 不保存 prompt、reasoning content、原始工具正文、SOP 正文、秘密或 stack trace；也不以 Trace 替代业务审计或 OTel。Windows 本地测试密码在失败 traceback 展开后已立即轮换。Task 8--9 的后续结论以本文顶部新鲜记录为准。详见 `docs/release-evidence/agent-trace-rbac.md`。

## 最新核验：Agent Task 6 pgvector 中文 SOP RAG 已完成本地代码与真实检索门禁

2026-07-22，PostgreSQL `0005_agent_knowledge`、`vector(512)`/HNSW、三份从零编写的合成中文 SOP、固定 `BAAI/bge-small-zh-v1.5` FastEmbed、MCP `knowledge.search_sop`、LangGraph citation、普通场景降级和强制 SOP 失败关闭均已实现。新鲜门禁为新建空卷容器网络聚焦 75 条、产品 535 条、Git 安全 4 条，Ruff/173 文件格式/mypy 73 个源文件/114 包锁文件/安全扫描通过；真实模型完成 3 文档 12 chunk 入库、幂等 replay 与三场景隔离检索。空卷门禁还修复了迁移测试依赖预迁移数据库的隐式前置条件。新镜像构建成功并观察到 PostgreSQL/MCP healthy、API started；完整 Compose smoke 在 Codex 自动化 WSL 会话中因外层 Docker service 约 43--49 秒停止而未完成，须在 Task 9 稳定终端重跑。Task 7 Agent Trace/API/SSE/RBAC 与前端展示尚未实施，生产发布门禁保持 `CLOSED`。详见 `docs/release-evidence/agent-pgvector-rag.md`。

## 最新核验：Agent Task 5 审批后 Verifier 与多轮复审已完成本地代码门禁

2026-07-22，三业务已接入批准后 Verifier：重新取证绕过缓存，`proceed` 仅在 binding 一致时幂等写入，`abort` 零工单安全终止，`escalate` 或模型参数漂移进入新审批周期。PostgreSQL 迁移 `0004_approval_cycles` 保留历史审批并按当前周期授权写入；缺失检查点恢复和“数据库已提交、检查点未保存”重放均有自动化证据。定向门禁 `48 passed`，完整 workflow `62 passed`，后端产品测试 `502 passed`，WSL 原生 Git 安全脚本 `4 passed`，Ruff/mypy 通过。Task 6 的 pgvector/RAG、Task 7 的 Agent Trace/API/SSE/前端展示仍未实施，旧 Compose 应用镜像尚未重建，因此生产发布门禁保持 `CLOSED`。详见 `docs/release-evidence/agent-verifier-reapproval.md`。

## 最新核验：零成本公开专题、主线门禁与作品集同步已完成

2026-07-20 功能分支 `feat/zero-cost-showcase-walkthrough` 已完成公开根路径、本地 `/engineering` 与本地 `/console` 三种页面职责：公开专题零 API、零写入、只陈述三业务和已验证证据；工程详解仅在开发模式的 localhost/127.0.0.1 渲染，包含 10 步请求链路、三业务差异、10 项技术职责、10 个真实事故复盘和 4 项 localStorage 掌握检查；控制台保持真实本地交互。完整前端为 16 个测试文件/40 条测试，后端为 `430 passed in 106.25s`；Ruff、138 文件格式、mypy 62 个源码文件和仓库安全扫描通过。PR #6 已以 `e483665` 合并，`main` run `29738863357` 五个 job 全绿，包含 Compose 三业务和 API/MCP 重启恢复。OperCerta production deploy `6a5e0bb5563acf4706a09c0d` 与作品集 production deploy `6a5e1b8824ba2290cf63c897` 已通过 HTTP/浏览器核验；作品集移动端无横向溢出、坏图或 fixed/sticky 元素。公开页面仍不连接可写后端，生产门禁继续为 `CLOSED`。证据见 `docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md`。

## 最新核验：Task 8 真实模型代表性验证已完成

2026-07-20 经用户授权，Moonshot AI `kimi-k2.6` 在本地 release Compose 中完成库存、设备、作业各 1 条 query 与 1 条批准路径，共 6 个 operation、3 条真实模型路径；三条写路径分别生成唯一补货、维修、作业恢复工单。实现提交 `b517ab8`。模型兼容修复后完整后端 `429 passed in 110.61s`，Ruff、138 文件格式、mypy 62 个源文件、92 个锁定包和仓库安全扫描通过；Mock release Compose 新鲜退出码 0、耗时 129.1 秒并自动清理。报告没有模型原文，token/成本因 adapter 未暴露 usage 而标记不可用。证据见 `docs/release-evidence/real-model-representative-validation.md`。生产门禁仍为 `CLOSED`。

## 历史核验：Task 8 本地发布候选与中文学习包已完成

2026-07-20 提交 `a3994ef` 新增 Caddy/React 多阶段镜像、仅 Caddy 暴露端口的 `compose.release.yaml`、一键发布 smoke，以及中文核心技术、手动实验和面试讲解三份材料。本轮完整后端门禁为 `422 passed in 94.96s`，Ruff、136 文件格式、mypy 62 个源文件、锁定依赖和仓库安全扫描通过；前端 12 个测试文件/25 条测试与生产构建通过。`scripts/verify_release_compose.sh` 新鲜运行退出码 0、耗时 70.8 秒，三业务、拒绝、重复审批、数据库事实、Caddy 路由、API/MCP 重启恢复和 metrics 不公开均通过应用断言。该检查点之后真实模型代表性调用已由本文首节补齐；公网交互 HTTPS、生产 IAM/限流/备份、用户手动掌握、当前远程 CI 与 Release Tag 尚未完成，生产发布门禁保持 `CLOSED`。

## 最新核验：三业务固定评测、Compose 与缓存矩阵已通过

2026-07-20 Task 7 已完成：版本化套件在 FastAPI + FastMCP + PostgreSQL 边界运行 42 条（库存 30、设备 6、作业 6），42 passed、0 failed；Compose 三业务与 API/MCP 重启恢复通过。2×2 本机矩阵 60/60 个 query completed、零错误，缓存关闭为每场景 10 次 MCP/0 hit，开启为 2 次 MCP/8 hit。最终总门禁 414 passed in 103.80s，锁文件、Ruff、134 文件格式、mypy 62 个源文件和安全扫描通过。每格仅 5 次，延迟不作为生产指标。证据见 `docs/release-evidence/three-business-evaluation-compose.md`。Task 8 本地发布、中文学习与真实模型代表性验证随后已完成，发布门禁仍为 `CLOSED`。

## 最新核验：Redis、OpenTelemetry 与 Real model adapter 已完成代码门禁

2026-07-20 已实现只读证据 Redis 缓存、批准后缓存绕过、低基数缓存指标、API/LangGraph/MCP/Redis/PostgreSQL OpenTelemetry span、API→MCP trace context 传播，以及严格解释型 OpenAI-compatible adapter。Task 7 已完成 Redis 镜像、缓存矩阵与三业务 Compose smoke；Compose 默认仍使用 Mock，OTLP 默认关闭，真实模型代表性运行随后已由本文首节补齐。提交前安全审查修复了自动异常正文/堆栈进入 span 与指标故障破坏缓存旁路两项问题；Task 6 完整测试 `409 passed in 101.15s`。发布门禁保持 `CLOSED`。

## 最新核验：三业务后端与单页控制台已完成本地门禁

2026-07-20 已完成库存补货、设备维修、作业异常恢复三条合成业务闭环的领域契约、六个 FastMCP 工具、PostgreSQL 状态/审计/工单、LangGraph 审批与恢复路径，以及 React 单页控制台。三对象同时支持只读 `query` 和受控 `create_work_order`；查询只取证和评估，零审批、零工单。该阶段门禁为后端 392 条、Ruff、125 文件格式检查、mypy 59 个源文件，以及前端 12 文件/25 条测试和生产构建全部通过。后续 Redis/OpenTelemetry、跨业务评测/Compose 和本地发布学习交付现已完成；真实模型与公网交互仍未完成。

## 最新核验：公开作品集 Netlify 静态镜像已完成生产部署验证

2026-07-19 已将 `D:\CODEX\resume\portfolio` 的 SSR 首页导出为独立静态镜像并部署至 <https://kxh-agent-portfolio.netlify.app>。单页刷新后无内部 hash 导航，四项目依次为 OperCerta、ForenTrail、SiteVerum、Federune；后三项诚实标记未启动。源作品集契约 3/3、镜像契约 8/8、真实构建与静态导出均通过。production deploy `6a5c986587eaef5b3156f49b` 实测 200，邮箱、电话和 public GitHub 均存在。该镜像不提供 OperCerta API 或写入能力；原产品发布门禁仍为 `CLOSED`。证据见 `docs/release-evidence/portfolio-netlify-static-mirror.md`。

## 最新核验：公开静态项目专题已完成生产部署验证

2026-07-18 已把 Vite 根路径调整为不依赖后端的静态项目专题，`/console` 保留真实本地演示；公开主机未配置 API 时只显示本地启动说明，不提供公网写入。专题已部署至 <https://opercerta-kxh.netlify.app>。线上标题、JS/CSS 指纹、两张 PNG 证据图和 `/api/*` 静态回退均已验证。个人作品集入口当时只完成本地构建；2026-07-19 已通过上节所述的独立 Netlify 静态镜像完成公开部署。2026-07-19 最终本地门禁为后端 342 条、Ruff、105 文件格式检查、mypy 50 个源文件、安全扫描、前端 11 文件/24 条测试及生产构建全部通过。PR #4 run `29652818349` 四个快速 job 成功并合并为 `0f262e0`；main run `29652991288` 五个 job（含 Compose smoke 与 API/MCP 重启恢复）全部成功。原产品发布门禁仍为 `CLOSED`。

## 最新核验：GitHub Actions 分层 CI 已完成

2026-07-18 已建立 Private `KXHXK/opercerta` 和只读、固定 Action SHA 的分层 Actions。PR `#1` run `29642286517` 的四个快速 job 成功，`compose-smoke` 按设计跳过；main run `29642363033` 的五个 job 全部成功，远程实测后端 `339 passed in 29.46s`、前端 9 个测试文件/15 条测试、Ruff、104 文件格式检查、mypy 50 个源文件、Compose 业务 smoke、API/MCP 重启恢复与无条件清理。Private 分支保护 API 因当前账户能力返回 HTTP 403，未启用并采用人工 PR 全绿后合并规则。证据见 `docs/release-evidence/github-actions-ci.md`；发布门禁保持 `CLOSED`。

## 最新核验：可观测性与安全回归基础已完成

2026-07-18 已实现服务端 `request_id`、异常后上下文清理、安全 JSON 日志、应用级低基数 Prometheus 指标、SSE 实际回放计数与默认关闭的 `/metrics`。完整后端门禁为 `332 passed in 74.58s`；Ruff clean；100 个文件格式正确；mypy 检查 50 个源文件无问题。前端防回退仍为 9 个测试文件、15 条测试通过且构建成功。证据见 `docs/release-evidence/observability-security-regression.md`；发布门禁保持 `CLOSED`。

## 最新核验：单页运营控制台已完成本地前端验证

2026-07-18（Asia/Shanghai）新增 Vite + React 单页运营控制台：内存演示 JWT、operator 创建处置、详情读取、approver 绑定审批、fetch SSE 审计快照回放与明确的 CLOSED 门禁均已实现。前端门禁实测为 9 个测试文件、15 个测试通过，生产构建通过。同轮后端回归为 `325 passed in 91.25s`，Ruff/format/mypy 均通过。该证据只证明客户端编排、构建及本机回归；不替代完整浏览器端到端或公开发布。详见 `docs/release-evidence/single-page-console.md`。

## 最新核验：JWT/RBAC 与固定契约评测已完成

本地短时 JWT 与四角色 RBAC 已实施，审批主体只从 JWT `sub` 取得。库存补货固定合成契约评测当前有效版本为 `replenishment-v3`：真实 FastAPI、FastMCP、PostgreSQL 与恢复夹具运行 30 条，30 passed、0 failed。已新增 SSE 审计快照回放与 `Last-Event-ID` 续传；全量 pytest 为 325 passed。详见 `docs/release-evidence/demo-jwt-rbac.md`、`docs/release-evidence/replenishment-contract-evaluation.md` 和 `docs/release-evidence/sse-audit-replay.md`。

历史核验：2026-07-20 Asia/Shanghai；旧解释型真实模型路径、当时主线 CI/Compose、静态专题和作品集生产同步已完成。新 Agent 核心结论以本文顶部 2026-07-22 记录为准，产品发布门禁仍为 `CLOSED`。

## 当前阶段

可靠性内核、库存补货、设备维修、作业异常恢复、三业务单页控制台、本地 Caddy 发布候选、Mock Agent 与真实 RAG 已完成代码和本机运行门禁。后端已覆盖严格输入、证据与计划、绑定审批、真实 MCP 读写、批准后重取事实、写后读验证、拒绝、过期、A/B 重启恢复以及 FastAPI 查询/创建/审批。旧解释型真实模型路径有历史证据，但新 Plan-and-Execute Kimi Tool Calling 尚未通过。公网交互与生产治理仍未完成，发布门禁保持关闭。

## 已验证事实

- 非法输入契约提交：`642fc2f`。
- 确定性状态恢复策略提交：`8bcf7c3`。
- 单元测试命令 `uv run pytest tests/unit -q` 于 2026-07-15 退出码 0，结果为 `19 passed`。
- Windows 原生 PostgreSQL 环境设计提交：`d506c8c`；本机端口固定为 `127.0.0.1:55432`，规格修正提交：`51c1583`。
- 原生 PostgreSQL 环境实施计划提交：`85c04d1`。
- 开发日志与文档索引设计提交：`a0564b1`；日志初始化计划提交：`6c97d5d`。
- 开发日志已初始化：`f70411f`；根目录 `DOCUMENT_INDEX.md` 已创建并列出已有文档与计划创建的证据目录，提交：`b29e2a2`。
- PostgreSQL 18.4 已安装并验证：服务 `postgresql-x64-18` 为 `Running/Automatic`，唯一监听为 `127.0.0.1:55432`，普通 IPv4 回环使用 SCRAM，真实连接探针使用 `opercerta_test`/`opercerta` 成功。
- 默认 `uv run mypy` 已实际检查 5 个源文件并通过；PEP 561 标记修复提交：`84a7b08`。
- 审批领域契约设计已确认并提交：`3c55f3b`；批准与拒绝均先原子进入 `resuming`，再由恢复节点路由。
- 审批领域契约实现提交：`b87ef7f`；目标测试先因缺失模块 RED，再以 `10 passed` GREEN；完整单元测试为 `29 passed`，Ruff 通过，mypy 实际检查 6 个源文件通过。
- PostgreSQL 可靠性 Schema 与迁移提交：`85e6538`；Alembic 当前版本为 `0001_reliability_kernel (head)`。
- 原子审批 Repository 提交：`b37a659`；数据库集成测试 `5 passed`，完整测试 `34 passed`，Ruff 通过，mypy 实际检查 10 个源文件通过。
- 十路审批竞态目标用例独立重复 20 轮，实测 `20/20` 通过；每轮断言一个成功、九个冲突、一条审批、一条审计和 `resuming` 状态。
- 本地测试数据库密码已于 2026-07-15 轮换；不回显探针确认 `opercerta_test`/`opercerta`、`127.0.0.1:55432` 可连接，轮换后完整测试 `34 passed`、Ruff 和 mypy 通过，新密码未出现在 Git 跟踪文件中。
- 2026-07-16 重启 Codex 后，PowerShell、OperCerta 工作区和 `.git` 临时写入探针均成功，探针已清理，`main` 工作区恢复干净。
- Task 4 方案 1、`created` 初始状态和完整书面契约均已获用户确认；契约见 `docs/superpowers/specs/2026-07-16-work-order-idempotency-contract-design.md`。
- Task 4 聚焦计划见 `docs/superpowers/plans/2026-07-16-work-order-idempotency.md`；规格覆盖、占位文本、类型命名和 Python 代码块语法已自审，计划中的 Pydantic JSON 边界烟雾检查通过，但这些不是生产实现通过证据。
- Task 4 领域 RED 因新错误契约缺失而退出 1，Repository RED 因模块缺失而退出 1；对应 GREEN 分别为 `27 passed` 和 `12 passed`。
- Task 4 数据库集成测试为 `17 passed`，完整测试为 `73 passed`，Ruff lint、全量 format check 和 mypy（12 个源文件）通过。
- 工单十路并发目标用例以 20 个独立 Pytest 进程复验，实测 `20/20`；每轮断言一次创建、九次安全重放、同一 ID、一行工单和一条创建审计。证据见 `docs/release-evidence/work-order-idempotency.md`。
- Task 5 已确认复用 `operations.request_payload` 的 `schema_version=1` 快照，不新增数据库迁移；审批落库后同时覆盖批准和拒绝恢复；状态与终态审计由独立 `OperationStateRepository` 原子写入。
- 本地锁定版本核验：`AsyncPostgresSaver.from_conn_string` 提供 async context manager，`setup()` 必须显式调用；`LANGGRAPH_STRICT_MSGPACK` 在 `langgraph-checkpoint==4.1.1` 源码中有效，并需在默认 serializer 构造前设置。
- 风险分级复核只减少用户对内部技术细节的形式审批，不减少工程文档；规格、计划、RED/GREEN、故障诊断、数据库与重启证据、静态检查、迁移回滚、未完成范围和风险必须继续在本地留痕并纳入 Git。
- Task 5 聚焦计划已把快照领域模型、原子状态仓储、独立 checkpointer、JSON-only 图、RecoveryCoordinator、批准/拒绝与四点 A/B 重启矩阵拆成六个可提交阶段；占位匹配为零，14 个 Python 代码块语法编译通过。这是计划自审，不是生产实现或测试通过证据。
- Task 5 快照领域 RED 因稳定错误缺失退出 1；GREEN focused 为 `48 passed`、单元全集为 `77 passed`，Ruff/format 与 mypy（14 个源文件）通过，提交 `8fb054e`。
- Task 5 状态仓储 RED 因 Repository 模块缺失退出 1；GREEN focused 为 `7 passed`、数据库集成为 `24 passed`，Ruff/format 与 mypy（15 个源文件）通过，提交 `5bdacf7`。
- Task 5 checkpointer RED 因模块缺失退出 1；DSN 回归还真实发现 `+` 空格编码不兼容与 URL 密码残留。修复后 focused 为 `4 passed`，与数据库回归合并为 `28 passed`，Ruff/format 与 mypy（16 个源文件）通过，提交 `e9b2834`。
- Task 5 reliability graph RED 因 workflow 模块缺失退出 1；GREEN focused 为 `3 passed`、workflow 集成为 `7 passed`，Ruff/format 与 mypy（18 个源文件）通过。测试断言 interrupt 时零审批、零工单，并覆盖无崩溃的批准完成与拒绝终止；提交 `2e6cbb4`。
- Task 5 RecoveryCoordinator RED 因模块缺失退出 1；GREEN focused 为 `8 passed`、workflow 集成 `15 passed`，四点矩阵使用完全关闭的 saver A/graph A 与新 saver B/graph B。十个独立 Pytest 进程实测 `10/10`，每轮 `8 passed`。
- Task 5 完整新鲜门禁为 `116 passed in 9.96s`；Ruff lint 通过、32 个文件 format check 通过、mypy 检查 19 个源文件通过。证据见 `docs/release-evidence/langgraph-restart-recovery.md`，实现提交 `e93b551`。
- Task 6 新鲜总门禁：依赖冻结同步成功；完整测试 `116 passed in 8.76s`；Ruff、32 文件 format check、mypy（19 个源文件）通过；secret-safe Alembic downgrade→upgrade 后为 `0001_reliability_kernel (head)`，迁移后集成测试 `39 passed in 8.74s`。
- 可靠性内核按既定权重已达到 100% 的阶段完成口径；这只表示 Task 1–6 本地门禁完成，不是完整 OperCerta 发布进度、生产指标或对外效果数字。
- 首个业务闭环确认采用确定性库存规则：`available = on_hand - reserved`，不足条件为 `available < reorder_point`，建议补货量为 `target_stock - available`；正常库存零审批、零工单。
- 所有补货写入强制审批；证据不可用时安全关闭；审批绑定证据 ID、规则版本、事实哈希、计划哈希和建议数量，批准后写入前必须重新取证并比较事实。
- 纵向切片采用独立 FastMCP 服务、四个真实 MCP 工具、Mock 结构化模型、LangGraph 和 FastAPI；React、SSE、JWT、真实模型与公开部署不在本轮。
- 设计规格见 `docs/superpowers/specs/2026-07-16-inventory-replenishment-vertical-slice-design.md`。这是已确认设计，不是功能完成或测试通过证据。
- 实施计划见 `docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md`，拆为领域规则、`0002` 数据边界、绑定审批、真实 FastMCP、类型化 MCP 客户端、审批前 workflow、审批后执行与恢复、FastAPI、总门禁九个原子 Task。
- 2026-07-16 核验官方 PyPI 与本地锁定 API：MCP Python SDK `1.28.1`、FastAPI `0.139.0`、HTTPX `0.28.1`、LangGraph `1.2.9`、`langgraph-checkpoint-postgres 3.1.0`、Pydantic `2.13.4`、SQLAlchemy `2.0.51`、Alembic `1.18.5` 均无需在本切片升级；FastMCP Streamable HTTP、`ClientSession` 和 HTTPX `ASGITransport` 的实际签名已用于计划。
- 库存补货 Task 1–6 已分别完成严格领域规则、`0002` 数据边界、绑定审批、真实 FastMCP 四工具、类型化 MCP gateway 和审批前 LangGraph；实现提交依次归档于 Git 历史。
- Task 7 图测试先取得 4 个失败：批准、拒绝、事实变化与写后读不一致均停在原有 `resuming`，证明审批后分支缺失；实现后图 focused 为 `10 passed`。
- Task 7 恢复测试先因 `operation_runner` 模块缺失在收集阶段退出 1；实现补货专用恢复协调器与 Runner 后，A/B restart focused 为 `7 passed`。
- 批准后执行会重新读取库存与规则、保存 refresh evidence、使用原批准说明重建确定性计划，并只比较规则版本、事实哈希、计划哈希和数量；不覆盖原批准计划，也不再次调用模型。
- 拒绝路径零工单；事实变化以 `approval_snapshot_mismatch` 失败；工单回读 ID、operation ID、payload 或 payload hash 不一致时以 `work_order_verification_failed` 失败。
- 工单预写恢复返回原工单 ID、最终 graph state 为 `replayed=True`，数据库保持一行工单和一条 `work_order_created`；过期扫描在恢复前把到期等待操作终止为 `expired`。
- Task 7 工作流全集为 `32 passed in 26.63s`；A/B restart 测试串行重复 10 次，每次 `7 passed`，共观察到 70 个恢复用例通过，不解释为生产成功率。
- Task 7 最终新鲜门禁：完整测试 `275 passed in 43.78s`；Ruff `All checks passed!`；60 文件 format check 通过；mypy 检查 32 个源文件通过。实现提交 `9b830d2`，证据见 `docs/release-evidence/replenishment-execution-restart.md`。
- Task 8 首次 API RED 因 `opercerta.api` 缺失在收集阶段退出 1；三条 API、严格模型和错误映射实现后 focused 首次为 `6 passed`。
- API 查询显式返回 `approval_binding`，客户端用其六个精确字段提交绑定审批；批准完成、拒绝零工单、重复审批、过期、旧绑定失配、库存缺失和固定 503 均有 HTTP 回归。
- API 边界额外拒绝非 `create_work_order + inventory + object_id` 请求；该回归先观察到设备查询错误返回 `202` 并创建失败 operation，修正后固定返回安全 `422`。
- OpenAPI 回归先证明 `created_at: object` 缺少 `date-time` format；收紧为 timezone-aware `datetime` 类型后 focused 恢复通过。
- 生产 factory 从环境读取数据库 URL、MCP URL、超时、审批 TTL 和 `mock` 模式；不自动迁移 Schema 或调用 checkpointer `setup()`，启动执行一次恢复扫描，关闭释放 Engine/checkpointer。
- 生产 lifespan 资源自审先证明 Engine 构造失败会遗留临时 `PGPASSWORD`；将 Engine 构造纳入 `try/finally` 后，错误路径恢复原环境的回归通过。
- Task 8 API focused 最终为 `8 passed in 10.11s`；MCP + workflow + API 回归为 `55 passed in 40.77s`；完整测试为 `283 passed in 55.73s`；Ruff、65 文件 format check、mypy（35 个源文件）通过。实现提交 `c4ac3ab`。
- Task 9 `uv sync --frozen --all-groups` 成功；初始完整测试为 `283 passed in 57.94s`，文档完成后提交前复验为 `283 passed in 56.41s`；Ruff clean；68 文件 format check；mypy 检查 35 个源文件通过。
- secret-safe Alembic 已完成 `0001_reliability_kernel` 降级与 `0002_inventory_replenishment (head)` 恢复；迁移后集成测试 `131 passed in 55.39s`。
- 绑定审批十路竞态以 10 个独立 Pytest 进程复验 `10/10`；补货 A/B 重启恢复以 10 个独立进程复验 `10/10`，每轮 `7 passed`。不解释为生产指标。
- 真实传输使用独立 FastMCP 服务、独立 FastAPI 服务和独立客户端进程；四工具名称精确匹配。低库存创建为 `awaiting_approval`，绑定数量 `18`，批准后 `completed`，重复审批 HTTP `409`。
- 同一真实 operation 的 PostgreSQL 查询确认一条审批、一条工单；最后四个审计事件为 `execution_started → work_order_created → verification_started → operation_completed`；测试 checkpoint 和业务行随后清理。
- 真实服务首次启动在业务调用前失败，根因是 Uvicorn 0.51 Windows 单进程默认 `ProactorEventLoop` 与 Psycopg async 不兼容。读取本机 Uvicorn loop factory 后，最小验证证明显式 `asyncio:SelectorEventLoop` 可启动，再完成三进程闭环。未修改业务实现。
- Task 1–9 总证据见 `docs/release-evidence/inventory-replenishment-vertical-slice.md`。

## 当前阻塞与风险

- Redis 只读缓存、OpenTelemetry Trace、真实模型 adapter 与代表性运行、Redis 8.8/三业务 Compose、跨业务固定评测和本地 Caddy 发布候选已完成；生产 IAM/SSO、公网 HTTPS、限流/备份和公开 API 尚未完成。只读静态专题和独立静态作品集镜像已完成部署，发布门禁保持关闭。
- Windows 原生真实服务需要显式 Selector loop；WSL2 Ubuntu Compose 已验证默认 Linux 容器进程、健康检查、MCP 服务名访问、独立 PostgreSQL volume 和 API/MCP 重启，但这不代表高可用或生产承诺。
- Docker/Linux 运行时已修订为 WSL2 → Ubuntu 26.04 LTS，不使用 Docker Desktop 或 Hyper-V VM。Ubuntu 官方仓库的 Docker `29.1.3`、Compose `2.40.3`、Buildx `0.30.1` 已安装；Docker Hub 直连超时后，经用户授权配置了三个可达的第三方 registry mirror。OperCerta Compose 已通过构建、健康、真实业务数据库断言与重启恢复；完整证据见 `docs/release-evidence/docker-linux-runtime.md`，供应链例外见 `docs/superpowers/specs/2026-07-17-wsl2-runtime-amendment-design.md`。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开旧的本地测试数据库连接密码；代码、Git 和文档未保存该值，fixture 已改为无密码 URL + 临时 `PGPASSWORD`，角色密码也已轮换和复验。
- 2026-07-16 checkpointer 首次 GREEN 的 Psycopg 连接失败 traceback 再次展开当时的本地测试角色密码。新封装已改为无密码 DSN、临时 `PGPASSWORD` 和 `%20` query 编码，代码/Git/文档未保存该值；用户随后同步轮换 PostgreSQL 角色与 `.env.local`，focused checkpointer 回归新鲜 `4 passed`。
- 当前 GitHub 仓库 `KXHXK/opercerta` 已由用户改为 public，公共 API 已复验。`main` branch protection 端点当前返回 HTTP 404，说明保护规则尚未配置；在配置前仍人工坚持 PR、快速 job 全绿后合并，并在合并后核验 `compose-smoke`。

## 下一步

继续只实施 OperCerta。Real Kimi replan、provider 异常 operation 原子收口、Draft PR 快速 Actions、inline 合并前审查和本地凭据轮换验证已完成。下一步进行用户手动演示/口述掌握检查与 PR 合并审批，合并后执行 main Compose。生产 IAM/限流/备份、自动部署和 Release Tag 尚未完成。

## 发布门禁

`OperCerta production release gate: CLOSED`。当前证据证明三业务本地 Mock Agent、真实 FastEmbed/pgvector RAG、Agent Trace、审批/幂等/恢复、单页控制台、历史静态展示、replan/异常原子收口、Draft PR 快速 CI 和凭据轮换；新 Agent 核心的 Real Kimi 完整 Compose 稳定通过、合并/main Compose、生产身份、公网 HTTPS 后端、限流/备份、自动部署、用户掌握和 Release Tag 仍待完成。求职演示发布门禁不能与生产门禁混用。

## 2026-07-25 异常信号历史对账待办

- 当前本地持久卷的三条关联 operation 均为 `expired`，但库存与任务 signal 仍为 `investigating`；设备 signal 已为 `attention_required`。
- 代码当前终态契约是 `completed/rejected → resolved`、`aborted/expired/failed → attention_required`，新路径测试已通过；旧卷状态形成于该映射上线前，尚无启动 backfill/reconciliation。
- 该问题不会否定新事务映射，但会使人工演示误以为仍在调查。下一实现任务应先为历史对账写 RED 测试，再实现启动对账或显式管理动作，并验证幂等、审计和重启恢复。
- 同时存在失败恢复入口缺口：`attention_required` signal 当前只能查看关联处置，同一事实哈希的再次扫描又会命中原去重行。下一规格需在“受控 reopen”与“创建带 lineage 的 superseding signal”之间作出选择，并覆盖并发重试、旧审批失效和审计链。
- 在修复并重新验证前，不把当前旧卷作为完整成功闭环证据，发布门禁继续保持 `CLOSED`。

## 2026-07-25 异常信号历史对账与后继调查已完成

- 上述待办已通过独立规格和 TDD 实现，不删除历史行：production 先恢复 operation，再把历史 `investigating` signal 对账为 `resolved` 或 `attention_required`。
- 新增 `0008_signal_successor_lineage`、唯一 predecessor 约束、幂等启动对账、operator-only retry API 和 React 后继谱系展示。
- 旧持久卷三个根 signal 已全部对账为 `attention_required`，三条旧 operation 仍为 `expired`。
- 库存 predecessor `57cb635c-07bb-41b3-bd7e-b579b810bb01` 已创建 successor `2cef23d3-1b30-436b-82b0-7a29125c6372` 和 operation `157347ee-ba5b-4911-bfe9-3f64a47ad162`；API/MCP 重启后仍为 `awaiting_approval`，重复 retry 为 HTTP 409。
- 新鲜门禁：完整后端 `607 passed in 329.96s`；前端 18 文件 `58 passed` 且 build 成功；Ruff、format 199 文件和 mypy 80 个源文件通过。
- 当前关键节点是人工审批新 operation；未 commit、未 push、未 merge，Real Kimi 未在本轮调用，生产发布门禁仍为 `CLOSED`。

## 2026-07-26 单根 Agent 图实施状态

- Task 1–3 已建立严格 AgentTurn、统一 Observation/Redis 语义和库存单根 ToolLoop。
- Task 4 已把批准后强制刷新、模型 Verifier、确定性事实绑定、拒绝/二次审批、安全失败、幂等工单和写后读接入同一 `operation_id/thread_id` 的根图。
- 一次性 PostgreSQL/MCP 根图用例 `11 passed`；完整单元 `386 passed`；Ruff、Mypy 81 个源文件与 diff 检查通过。
- 这仍是显式 `enabled=True` 的内部候选；默认 FastAPI/Compose 仍走旧多图路径，设备与任务尚未接入共享根图。
- 当前执行 Task 5：把设备维修与阻塞任务收敛为策略，不复制生命周期编排。Real Kimi、默认路径切换、旧图删除、公开部署、commit/push/merge 均尚未发生，发布门禁为 `CLOSED`。

## 2026-07-26 Task 5 更新

- 库存、设备维修和阻塞任务已共用通用根图入口和完全相同的生命周期节点。
- 场景差异只存在于策略函数：允许的 MCP 事实工具、对象键、证据/评估/计划类型、审批 binding 和工单 payload。
- 一次性 PostgreSQL/MCP 的三场景根图测试合计 `20 passed`；完整单元 `386 passed`；Ruff、Mypy 82 个源文件与 diff 检查通过。
- 默认运行入口仍未切换，旧图仍在；下一步为 Task 6 case projection API，生产发布门禁继续 `CLOSED`。

## 2026-07-26 Task 6 更新

- 后端新增 `/api/v1/signal-cases`，实时投影“一对象一 case”，包含当前 signal、当前 operation、历史计数和有序 lineage。
- `/signals/scan` 返回本次受影响 case；原始 `/signals` 保留，不迁移或复制业务事实。
- PostgreSQL signal API 用例 `4 passed`，目标静态检查通过。React 尚未消费新接口，当前执行 Task 7。

## 2026-07-26 Task 7 React case 工作台更新

- React 已从平铺 signal 列表迁移为按 `case_key` 聚合的一对象一主卡；选中、加载、错误、打开处置和历史展开均只作用于当前卡片。
- 真实浏览器扫描显示三类业务各一张主卡，单独展开任务历史时全页只有一个“收起历史”。验收同时发现并修复了 case current 选择缺陷：有 successor 后不得回退到仍为 `attention_required` 的祖先，当前事实永远是 lineage 叶节点。
- 前端 19 个文件共 `60 passed` 且生产构建成功；signal API `5 passed`，目标 Ruff/Mypy 通过。API 镜像已重建；重建后的浏览器 reload 被本地 URL 安全策略阻止，未虚构最终浏览器复验结果。
- 默认 API/Compose 尚未切到新根图；下一步执行 Task 8 新旧路径等价与旧编排收敛，生产发布门禁保持 `CLOSED`。

## 2026-07-26 Task 8–11 单根运行时与最终本地门禁

- production factory 已切换为只构造一个 `ControlledAgentRootGraph`；首次运行和重启恢复都通过同一 root runner/coordinator。历史图模块仅供回归与等价测试，产品运行时不存在隐藏 fallback。
- 三业务新旧路径等价测试 `3 passed`；production lifespan `2 passed`；核心 API/root/equivalence 合集 `41 passed`。同时修复恢复时把失败 read observation 重新提交、触发 `duplicate_tool_call` 的缺陷：成功或失败 Observation 都计入 attempted，证据不完整时最终分析 fail closed。
- Task 9 本地总门禁：单元 `392 passed`，完整集成 `260 passed`，前端 19 个文件 `60 passed` 且 build 成功，Ruff/format/Mypy（85 个源文件）通过。隔离 Compose 的三业务、RAG、数据库断言和 API/MCP 重启恢复通过，临时环境已清理。
- Task 10 少量真实 Kimi 代表验证完成：三业务各一次只读、库存一次批准写入、无效 provider 一次 fail-closed。真实路径没有回退 Mock；证据不保存 API key、完整 prompt、模型原文或隐藏推理。
- 真实门禁暴露并修复三项 Mock 无法发现的兼容问题：LLM 错用 MCP 2 秒 timeout；Kimi 强制 tool calling 需关闭 thinking；通用 structured output 在 Final Analysis/Verifier 上波动。现由独立 90 秒模型 timeout、provider 配置和两个内部原生提交工具收口。
- Task 11 学习文档、事故复盘、实施证据、每日日志、handoff 和根目录唯一文档索引已更新。当前仅剩外部审批动作与生产能力：commit/push/PR/merge、公开交互部署、生产 IAM/限流/备份/自动发布/Release Tag。
- 文档完成后的最终复验为完整单元 `395 passed`、受影响隔离 PostgreSQL 集成 `32 passed`、Ruff/213 文件 format check/Mypy 85 个源文件/仓库安全全绿；同步 worktree 当日日志后文档索引核对 544 份、零漏项。
- 生产发布门禁保持 `CLOSED`；未启动 ForenTrail。
