# OperCerta｜智能运营处置 Agent：实施交接

## 当前检查点

- 2026-07-20 三业务主计划 Task 6 已完成代码与本地测试：Redis 只缓存初次/查询证据并在故障时旁路，批准后复核直连 MCP；OpenTelemetry 关联 API、LangGraph、MCP、Redis 和 PostgreSQL，关闭自动异常正文/堆栈记录；OpenAI-compatible adapter 只输出严格解释字段、最多两次尝试且真实模式失败不回退 Mock。最终完整测试 `409 passed in 101.15s`，锁文件/Ruff/131 文件 format/mypy 62 个源文件通过；真实模型调用、Redis 8.8 Compose 和跨业务评测仍待 Task 7–8，发布门禁保持关闭。
- 2026-07-19 作品集已完成单页视觉刷新并生产替换：无内部 hash 导航，四项目按 OperCerta、ForenTrail、SiteVerum、Federune 排列，后三项明确未启动；邮箱、用户明确授权公开的手机号和 public GitHub 已接入。production deploy `6a5c986587eaef5b3156f49b` 返回 200。源契约 3/3、镜像契约 8/8 及真实构建/导出通过。
- 2026-07-19 公开专题功能工作树最终本地门禁通过：后端 `342 passed in 65.94s`、Ruff clean、105 文件 format check、mypy 50 个源文件、仓库安全扫描、前端 11 文件/24 条测试和 Vite 构建均通过。首次门禁在后端通过后因测试文件多余空行触发 Ruff `I001`，最小修复后从头重跑整条门禁。PR #4 run `29652818349` 四个快速 job 成功并合并为 `0f262e0`；main run `29652991288` 五个 job（含 Compose smoke、API/MCP 重启恢复与清理）全部成功。原 release gate 仍为 `CLOSED`。
- 2026-07-18 已将不连接后端的 OperCerta 静态专题生产部署到 <https://opercerta-kxh.netlify.app>。专题资源与静态回退均已核验；个人作品集随后于 2026-07-19 完成独立 Netlify 部署和单页刷新。公开页面只展示合成数据证据，不改变生产 IAM、HTTPS 后端、自动部署和公开 API 的未完成边界。
- 2026-07-18 建立 `KXHXK/opercerta` 与分层 GitHub Actions；仓库已于 2026-07-19 由用户改为 public。历史 PR/main Actions 证据仍有效。当前 main branch protection 尚未配置，保护端点返回 404；配置前必须继续执行人工 PR 全绿后合并规则。
- 2026-07-18 已完成可观测性与安全回归基础：FastAPI `0.139.2`、服务端 request_id、异常后上下文清理、安全 JSON 日志、应用级低基数 Prometheus 指标、SSE 实际回放计数和默认关闭的 `/metrics`。完整后端门禁为 `332 passed in 74.58s`，Ruff、100 文件 format check、mypy 50 个源文件通过；证据见 `docs/release-evidence/observability-security-regression.md`。发布门禁仍为 `CLOSED`。

- 2026-07-18 已完成本地单页运营控制台：React/Vite、内存 JWT、创建/读取/审批编排与 fetch SSE 审计快照回放。前端门禁为 9 个测试文件、15 个测试通过，构建通过；证据见 `docs/release-evidence/single-page-console.md`。这不是生产身份、完整浏览器端到端或公开发布验证。

- 书面设计已经总审通过并冻结为实施基线；当前文档目录见根目录 `DOCUMENT_INDEX.md`。
- 可靠性内核 Task 1–6 已完成本地总门禁；Task 6 新鲜完整测试为 `116 passed`，迁移 downgrade→upgrade 后集成测试为 `39 passed`，Ruff/format/mypy 通过。总证据见 `docs/release-evidence/reliability-kernel.md`。
- Windows 原生 PostgreSQL 18.4 已验证为本地集成测试数据库：服务仅监听 `127.0.0.1:55432`，普通 IPv4 回环使用 SCRAM；证据见 `docs/release-evidence/native-postgres-environment.md`。
- 审批原子性证据见 `docs/release-evidence/approval-atomicity.md`。曾被失败 traceback 展开的本地测试角色密码已轮换并复验；新值不得粘贴到对话或写入 Git。
- Task 4 已按聚焦计划完成：领域契约 `6f99bf6`、共享数据库 fixture `8408f81`、幂等 Repository 与并发测试 `88c014c`；证据见 `docs/release-evidence/work-order-idempotency.md`。
- Task 5 已完成五个原子实现提交：快照领域边界 `8fb054e`、operation 原子状态仓储 `5bdacf7`、独立 checkpointer `e9b2834`、JSON-only reliability graph `2e6cbb4`、RecoveryCoordinator 与四点 A/B 重启矩阵 `e93b551`。证据见 `docs/release-evidence/langgraph-restart-recovery.md`。
- Task 5 最终完整测试为 `116 passed`，重启矩阵十个独立 Pytest 进程实测 `10/10`；Ruff、format 和 mypy（19 个源文件）通过。这些是本地验证，不是生产指标。
- checkpointer 首次连接失败 traceback 展开了当时的本地测试角色密码；代码、Git 和文档未保存该值，封装已改为无密码 DSN + 临时 `PGPASSWORD`。用户已同步轮换 PostgreSQL 角色密码与 `.env.local`，轮换后 focused checkpointer 回归新鲜 `4 passed`。
- 后续采用风险分级复核：用户决定产品范围、成本、外部账号和发布；内部技术细节由 Codex 以 TDD、静态检查和证据负责。进度必须区分可靠性内核与完整发布范围。
- 当前 Git 已配置 `origin` 为 Private `KXHXK/opercerta`，本地 `main` 跟踪 `origin/main`；禁止 force push、删除远程历史或未经全绿 PR 直接合并。
- 发布门禁保持 `CLOSED`，不启动 ForenTrail 或其他项目。
- 首个纵向业务闭环已确定为“库存不足 → 补货工单”；设计见 `docs/superpowers/specs/2026-07-16-inventory-replenishment-vertical-slice-design.md`，可执行计划见 `docs/superpowers/plans/2026-07-16-inventory-replenishment-vertical-slice.md`。
- 库存补货 Task 1–7 已完成。Task 7 实现提交为 `9b830d2`：批准后重新读取库存与规则、比较审批绑定事实、幂等创建工单、写后读验证、拒绝终止、审批过期扫描、`OperationRunner` 和补货专用恢复协调器。
- Task 7 新鲜门禁为完整测试 `275 passed in 43.78s`、Ruff clean、60 文件 format check、mypy 检查 32 个源文件通过；A/B 重启矩阵额外串行重复 10 次，每次 `7 passed`。证据见 `docs/release-evidence/replenishment-execution-restart.md`，这些不是生产成功率或 SLA。
- Task 8 实现提交为 `c4ac3ab`：新增严格 FastAPI 模型、三条 `/api/v1/operations` 路由、固定中文安全错误 envelope、OpenAPI 非可信 actor 声明和从环境构造的生产 lifespan。
- Task 8 API focused 为 `8 passed`；MCP + workflow + API 回归为 `55 passed`；提交前完整测试为 `283 passed in 55.73s`，Ruff clean、65 文件 format check、mypy 检查 35 个源文件通过。
- 生产 lifespan 不自动运行迁移或 checkpointer `setup()`；启动执行一次 `recover_all()`，关闭释放 checkpointer 与 Engine，并在 Engine 构造失败时恢复原 `PGPASSWORD`。
- Task 9 本地总门禁已执行：初始完整测试 `283 passed in 57.94s`，文档完成后提交前复验 `283 passed in 56.41s`；锁定依赖、Ruff、68 文件 format check、mypy 35 个源文件均通过。
- secret-safe 迁移完成 `0001_reliability_kernel → 0002_inventory_replenishment (head)`，迁移后集成测试 `131 passed in 55.39s`。
- 审批十路竞态独立重复 `10/10`；A/B 重启恢复独立重复 `10/10`，每轮 `7 passed`。这些只是本地重复证据。
- 真实 FastMCP、FastAPI 和独立客户端三进程闭环通过：四工具名称匹配，创建进入 `awaiting_approval`，批准后 `completed`，重复审批 `409`，数据库一条审批、一条工单且终态审计顺序正确。证据见 `docs/release-evidence/inventory-replenishment-vertical-slice.md`。
- Windows Uvicorn 0.51 默认 Proactor loop 与 Psycopg async 不兼容；真实服务验证使用 Uvicorn custom loop factory 明确选择 Selector loop。Linux/Docker Compose 已完成本地单节点验证，但未形成生产高可用承诺。
- Docker/Linux 运行时已修订为 WSL2、Ubuntu 26.04 LTS；不使用 Docker Desktop、Hyper-V VM。因 Docker 厂商 APT 源 TLS 被当前网络重置，经用户确认安装 Ubuntu 官方签名仓库的 Docker Engine `29.1.3`、Compose `2.40.3` 与 Buildx `0.30.1`。Docker Hub 直连超时后，经用户授权配置三个实测可达的第三方 registry mirror。OperCerta Compose 的构建、健康、真实审批工单数据库断言和 API/MCP 重启恢复已通过；完整证据见 `docs/release-evidence/docker-linux-runtime.md`，发布门禁仍关闭。

## 新对话必须先做

1. 先阅读 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md` 和最近每日日志，再阅读相关设计、计划、交接和 Git 状态。
2. 只实施 OperCerta；库存补货 Task 1–9、WSL2 Docker Compose、演示 JWT/RBAC、固定 30 条契约评测、单页控制台、可观测性安全基础、GitHub Actions、静态专题和作品集已有证据。下一步按求职演示最小发布口径补齐可重复演示与交接；生产身份、Caddy/HTTPS 后端、自动部署与公开 API 作为独立生产演进项，不启动其他项目。
3. 运行集成测试前，以不回显方式从已忽略 `.env.local` 加载 `OPERCERTA_DATABASE_URL`；不得提交该文件或任何凭据。
4. 每个效果数字都保留基线、测试数据、测量脚本和结果证据；指标未测出前使用目标值或空值，不写成已实现结果。
5. 使用公开或合成数据，从零编写全部代码和文档，不导入任何原单位源码、数据、截图、模型、品牌或内部规则。

## 第一阶段完成条件

- 非法输入、状态恢复、审批竞态和幂等写入测试先于对应实现并可重复运行。
- 最小纵向闭环能够在本地 PostgreSQL 环境运行，失败路径和人工接管路径可演示；Linux/Docker 一致性验证在发布门禁阶段完成。
- README、架构图、接口说明、评测报告、部署与回滚说明随实现同步更新。
- 通过详细设计中的发布门禁后，再部署公开演示、填写在线地址并开始 ForenTrail。

## 可复制到新对话的启动语

> 工作目录为本 OperCerta 仓库根目录。请先读取 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md`、最近每日日志、`README.md`、`IMPLEMENTATION_HANDOFF.md`、`docs/specs/` 下的四份设计文件及当前相关规格、计划和证据；库存补货、WSL2 Compose、JWT/RBAC、固定评测、单页控制台、可观测性、GitHub Actions、静态专题和作品集已有自动化证据。下一步只规划和实施 OperCerta 求职演示最小发布范围，不复用旧公司材料，不虚构指标，不启动其他项目。
