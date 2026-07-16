# OperCerta 当前状态

最后核验：2026-07-16 12:24 Asia/Shanghai，Git 基线 commit `e93b551`。

## 当前阶段

非法输入、确定性恢复决策、数据库迁移、原子审批竞态、幂等工单和 Task 5 四点 LangGraph 重启恢复均已按 TDD 实现。Task 5 证据已归档；可靠性内核 Task 6 总门禁尚未执行。

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
- 进度规划估算：可靠性内核约 60%–65%；完整 OperCerta 发布范围约 25%–30%。这是按已定义里程碑及剩余范围估算，不是测试成绩或可对外指标。
- 风险分级复核只减少用户对内部技术细节的形式审批，不减少工程文档；规格、计划、RED/GREEN、故障诊断、数据库与重启证据、静态检查、迁移回滚、未完成范围和风险必须继续在本地留痕并纳入 Git。
- Task 5 聚焦计划已把快照领域模型、原子状态仓储、独立 checkpointer、JSON-only 图、RecoveryCoordinator、批准/拒绝与四点 A/B 重启矩阵拆成六个可提交阶段；占位匹配为零，14 个 Python 代码块语法编译通过。这是计划自审，不是生产实现或测试通过证据。
- Task 5 快照领域 RED 因稳定错误缺失退出 1；GREEN focused 为 `48 passed`、单元全集为 `77 passed`，Ruff/format 与 mypy（14 个源文件）通过，提交 `8fb054e`。
- Task 5 状态仓储 RED 因 Repository 模块缺失退出 1；GREEN focused 为 `7 passed`、数据库集成为 `24 passed`，Ruff/format 与 mypy（15 个源文件）通过，提交 `5bdacf7`。
- Task 5 checkpointer RED 因模块缺失退出 1；DSN 回归还真实发现 `+` 空格编码不兼容与 URL 密码残留。修复后 focused 为 `4 passed`，与数据库回归合并为 `28 passed`，Ruff/format 与 mypy（16 个源文件）通过，提交 `e9b2834`。
- Task 5 reliability graph RED 因 workflow 模块缺失退出 1；GREEN focused 为 `3 passed`、workflow 集成为 `7 passed`，Ruff/format 与 mypy（18 个源文件）通过。测试断言 interrupt 时零审批、零工单，并覆盖无崩溃的批准完成与拒绝终止；提交 `2e6cbb4`。
- Task 5 RecoveryCoordinator RED 因模块缺失退出 1；GREEN focused 为 `8 passed`、workflow 集成 `15 passed`，四点矩阵使用完全关闭的 saver A/graph A 与新 saver B/graph B。十个独立 Pytest 进程实测 `10/10`，每轮 `8 passed`。
- Task 5 完整新鲜门禁为 `116 passed in 9.96s`；Ruff lint 通过、32 个文件 format check 通过、mypy 检查 19 个源文件通过。证据见 `docs/release-evidence/langgraph-restart-recovery.md`，实现提交 `e93b551`。
- 进度规划估算：可靠性内核 Task 1–5 完成、Task 6 待执行，按既定 `10/10/20/20/30/10` 权重约为 90%。这是排期估算，不是测试成绩或对外指标。

## 当前阻塞与风险

- 可靠性内核 Task 6 的迁移升降级、完整总证据和交接门禁尚未执行，不能声称可靠性内核总门禁或发布门禁完成。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开旧的本地测试数据库连接密码；代码、Git 和文档未保存该值，fixture 已改为无密码 URL + 临时 `PGPASSWORD`，角色密码也已轮换和复验。
- 2026-07-16 checkpointer 首次 GREEN 的 Psycopg 连接失败 traceback 再次展开当时的本地测试角色密码。新封装已改为无密码 DSN、临时 `PGPASSWORD` 和 `%20` query 编码，代码/Git/文档未保存该值；用户随后同步轮换 PostgreSQL 角色与 `.env.local`，focused checkpointer 回归新鲜 `4 passed`。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

执行可靠性内核 Task 6：新鲜依赖同步、完整测试/静态检查、Alembic downgrade/upgrade、证据归档和边界交接；通过后冻结内核并转向 OperCerta 最小纵向闭环。

## 发布门禁

`OperCerta release gate: CLOSED`。本地环境通过不等于发布通过；Linux/Docker 验证和完整可靠性内核证据仍待完成。
