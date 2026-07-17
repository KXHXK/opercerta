# OperCerta｜智能运营处置 Agent：实施交接

## 当前检查点

- 书面设计已经总审通过并冻结为实施基线；当前文档目录见根目录 `DOCUMENT_INDEX.md`。
- 可靠性内核 Task 1–6 已完成本地总门禁；Task 6 新鲜完整测试为 `116 passed`，迁移 downgrade→upgrade 后集成测试为 `39 passed`，Ruff/format/mypy 通过。总证据见 `docs/release-evidence/reliability-kernel.md`。
- Windows 原生 PostgreSQL 18.4 已验证为本地集成测试数据库：服务仅监听 `127.0.0.1:55432`，普通 IPv4 回环使用 SCRAM；证据见 `docs/release-evidence/native-postgres-environment.md`。
- 审批原子性证据见 `docs/release-evidence/approval-atomicity.md`。曾被失败 traceback 展开的本地测试角色密码已轮换并复验；新值不得粘贴到对话或写入 Git。
- Task 4 已按聚焦计划完成：领域契约 `6f99bf6`、共享数据库 fixture `8408f81`、幂等 Repository 与并发测试 `88c014c`；证据见 `docs/release-evidence/work-order-idempotency.md`。
- Task 5 已完成五个原子实现提交：快照领域边界 `8fb054e`、operation 原子状态仓储 `5bdacf7`、独立 checkpointer `e9b2834`、JSON-only reliability graph `2e6cbb4`、RecoveryCoordinator 与四点 A/B 重启矩阵 `e93b551`。证据见 `docs/release-evidence/langgraph-restart-recovery.md`。
- Task 5 最终完整测试为 `116 passed`，重启矩阵十个独立 Pytest 进程实测 `10/10`；Ruff、format 和 mypy（19 个源文件）通过。这些是本地验证，不是生产指标。
- checkpointer 首次连接失败 traceback 展开了当时的本地测试角色密码；代码、Git 和文档未保存该值，封装已改为无密码 DSN + 临时 `PGPASSWORD`。用户已同步轮换 PostgreSQL 角色密码与 `.env.local`，轮换后 focused checkpointer 回归新鲜 `4 passed`。
- 后续采用风险分级复核：用户决定产品范围、成本、外部账号和发布；内部技术细节由 Codex 以 TDD、静态检查和证据负责。进度必须区分可靠性内核与完整发布范围。
- 当前 Git 尚未配置远程仓库；本地 commit 不是远程备份。
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
- Windows Uvicorn 0.51 默认 Proactor loop 与 Psycopg async 不兼容；真实服务验证使用 Uvicorn custom loop factory 明确选择 Selector loop。Linux/Docker 仍未验证。
- Docker/Linux 运行时已修订为 WSL2、Ubuntu 26.04 LTS；不使用 Docker Desktop、Hyper-V VM。因 Docker 厂商 APT 源 TLS 被当前网络重置，经用户确认安装 Ubuntu 官方签名仓库的 Docker Engine `29.1.3`、Compose `2.40.3` 与 Buildx `0.30.1`，服务已启动。Docker Hub 直连超时后，经用户授权配置三个实测可达的第三方 registry mirror，`hello-world` 的普通名称拉取和运行已通过；OperCerta 真实验收仍未开始。修订与证据见 `docs/superpowers/specs/2026-07-17-wsl2-runtime-amendment-design.md`。

## 新对话必须先做

1. 先阅读 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md` 和最近每日日志，再阅读相关设计、计划、交接和 Git 状态。
2. 只实施 OperCerta；库存补货 Task 1–9 已完成本地后端闭环。下一步直接按 Docker/Linux TDD 计划构建镜像并完成 Compose 验收；公共 registry mirror 属于已记录的供应链例外，不启动其他项目。
3. 运行集成测试前，以不回显方式从已忽略 `.env.local` 加载 `OPERCERTA_DATABASE_URL`；不得提交该文件或任何凭据。
4. 每个效果数字都保留基线、测试数据、测量脚本和结果证据；指标未测出前使用目标值或空值，不写成已实现结果。
5. 使用公开或合成数据，从零编写全部代码和文档，不导入任何原单位源码、数据、截图、模型、品牌或内部规则。

## 第一阶段完成条件

- 非法输入、状态恢复、审批竞态和幂等写入测试先于对应实现并可重复运行。
- 最小纵向闭环能够在本地 PostgreSQL 环境运行，失败路径和人工接管路径可演示；Linux/Docker 一致性验证在发布门禁阶段完成。
- README、架构图、接口说明、评测报告、部署与回滚说明随实现同步更新。
- 通过详细设计中的发布门禁后，再部署公开演示、填写在线地址并开始 ForenTrail。

## 可复制到新对话的启动语

> 工作目录为本 OperCerta 仓库根目录。请先读取 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md`、最近每日日志、`README.md`、`IMPLEMENTATION_HANDOFF.md`、`docs/specs/` 下的四份设计文件、库存补货纵向闭环设计、实施计划和总证据；库存补货 Task 1–9 已完成 Windows 原生 PostgreSQL 后端本地门禁，发布门禁仍关闭。下一步只规划和实施 OperCerta 剩余发布范围，优先核对 Docker/Linux 一致性及运行健康边界，不复用旧公司材料，不虚构指标，不启动其他项目。
