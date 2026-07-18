# OperCerta 当前状态

## 下一实施边界：Private GitHub Actions 分层 CI

2026-07-18 已确认采用 Private GitHub 仓库与分层 Actions：PR/push 运行仓库安全、Python 静态门禁、PostgreSQL 18 完整后端测试和前端门禁；`main`/手动运行追加 Compose 业务 smoke 与重启恢复。设计见 `docs/superpowers/specs/2026-07-18-github-actions-ci-security-gate-design.md`，实施计划见 `docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md`。当前尚未创建远程仓库、workflow 或真实 GitHub run；发布门禁保持 `CLOSED`。

## 最新核验：可观测性与安全回归基础已完成

2026-07-18 已实现服务端 `request_id`、异常后上下文清理、安全 JSON 日志、应用级低基数 Prometheus 指标、SSE 实际回放计数与默认关闭的 `/metrics`。完整后端门禁为 `332 passed in 74.58s`；Ruff clean；100 个文件格式正确；mypy 检查 50 个源文件无问题。前端防回退仍为 9 个测试文件、15 条测试通过且构建成功。证据见 `docs/release-evidence/observability-security-regression.md`；发布门禁保持 `CLOSED`。

## 最新核验：单页运营控制台已完成本地前端验证

2026-07-18（Asia/Shanghai）新增 Vite + React 单页运营控制台：内存演示 JWT、operator 创建处置、详情读取、approver 绑定审批、fetch SSE 审计快照回放与明确的 CLOSED 门禁均已实现。前端门禁实测为 9 个测试文件、15 个测试通过，生产构建通过。同轮后端回归为 `325 passed in 91.25s`，Ruff/format/mypy 均通过。该证据只证明客户端编排、构建及本机回归；不替代完整浏览器端到端或公开发布。详见 `docs/release-evidence/single-page-console.md`。

## 最新核验：JWT/RBAC 与固定契约评测已完成

本地短时 JWT 与四角色 RBAC 已实施，审批主体只从 JWT `sub` 取得。库存补货固定合成契约评测当前有效版本为 `replenishment-v3`：真实 FastAPI、FastMCP、PostgreSQL 与恢复夹具运行 30 条，30 passed、0 failed。已新增 SSE 审计快照回放与 `Last-Event-ID` 续传；全量 pytest 为 325 passed。详见 `docs/release-evidence/demo-jwt-rbac.md`、`docs/release-evidence/replenishment-contract-evaluation.md` 和 `docs/release-evidence/sse-audit-replay.md`。

最后核验：2026-07-18 Asia/Shanghai；发布门禁仍为 `CLOSED`。

## 当前阶段

可靠性内核与库存补货纵向切片 Task 1–9 已完成 Windows 原生 PostgreSQL 后端本地门禁。后端已覆盖严格输入、证据与计划、绑定审批、真实 MCP 读写、批准后重取事实、写后读验证、拒绝、过期、A/B 重启恢复、FastAPI 创建/查询/审批以及独立服务进程真实传输。发布门禁仍关闭。

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

- 设备场景、生产 IAM/SSO、人工接管、CI/CD、Caddy/HTTPS、集中指标采集/告警和公开部署尚未完成，发布门禁保持关闭。
- Windows 原生真实服务需要显式 Selector loop；WSL2 Ubuntu Compose 已验证默认 Linux 容器进程、健康检查、MCP 服务名访问、独立 PostgreSQL volume 和 API/MCP 重启，但这不代表高可用或生产承诺。
- Docker/Linux 运行时已修订为 WSL2 → Ubuntu 26.04 LTS，不使用 Docker Desktop 或 Hyper-V VM。Ubuntu 官方仓库的 Docker `29.1.3`、Compose `2.40.3`、Buildx `0.30.1` 已安装；Docker Hub 直连超时后，经用户授权配置了三个可达的第三方 registry mirror。OperCerta Compose 已通过构建、健康、真实业务数据库断言与重启恢复；完整证据见 `docs/release-evidence/docker-linux-runtime.md`，供应链例外见 `docs/superpowers/specs/2026-07-17-wsl2-runtime-amendment-design.md`。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开旧的本地测试数据库连接密码；代码、Git 和文档未保存该值，fixture 已改为无密码 URL + 临时 `PGPASSWORD`，角色密码也已轮换和复验。
- 2026-07-16 checkpointer 首次 GREEN 的 Psycopg 连接失败 traceback 再次展开当时的本地测试角色密码。新封装已改为无密码 DSN、临时 `PGPASSWORD` 和 `%20` query 编码，代码/Git/文档未保存该值；用户随后同步轮换 PostgreSQL 角色与 `.env.local`，focused checkpointer 回归新鲜 `4 passed`。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

继续只实施 OperCerta。下一步按已确认计划实施本地安全扫描器和 Actions workflow；创建 Private 仓库前仍需确认实际 GitHub owner/身份。Caddy/HTTPS、生产 IAM、人工接管和公开部署不在本阶段。公共 registry mirror 的风险与后续每个实际镜像 digest 仍须留证。

## 发布门禁

`OperCerta release gate: CLOSED`。当前证据证明库存补货纵向切片、WSL2 Compose、演示身份、固定评测、单页控制台和可观测性安全基础在本地通过；完整产品面、生产身份、HTTPS、CI/CD 和公开部署仍待完成。
