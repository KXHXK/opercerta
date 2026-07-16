# OperCerta 当前状态

最后核验：2026-07-16 15:44 Asia/Shanghai，Git 基线 commit `f5d2de7`。

## 当前阶段

可靠性内核 Task 1–6 已完成本地总门禁。首个业务闭环已确定为“库存不足 → 补货工单”，真实 MCP 后端纵向切片规格已获用户确认并落盘；尚未编写实施计划或生产代码。

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

## 当前阻塞与风险

- MCP 五工具、完整 workflow、API/SSE、认证、前端、评测、安全回归、可观测性、Linux/Docker 和公开部署尚未完成，发布门禁保持关闭。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开旧的本地测试数据库连接密码；代码、Git 和文档未保存该值，fixture 已改为无密码 URL + 临时 `PGPASSWORD`，角色密码也已轮换和复验。
- 2026-07-16 checkpointer 首次 GREEN 的 Psycopg 连接失败 traceback 再次展开当时的本地测试角色密码。新封装已改为无密码 DSN、临时 `PGPASSWORD` 和 `%20` query 编码，代码/Git/文档未保存该值；用户随后同步轮换 PostgreSQL 角色与 `.env.local`，focused checkpointer 回归新鲜 `4 passed`。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

用户复核已落盘的库存补货纵向闭环规格；确认无修改后使用 writing-plans 编写聚焦 TDD 实施计划，仍不提前编写生产代码。

## 发布门禁

`OperCerta release gate: CLOSED`。本地可靠性内核通过不等于发布通过；最小纵向业务闭环、完整产品门禁和 Linux/Docker 一致性验证仍待完成。
