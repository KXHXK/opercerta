# OperCerta 当前状态

最后核验：2026-07-16 00:18 Asia/Shanghai，Git 基线 commit `b44ffb0`。

## 当前阶段

非法输入、状态恢复、数据库迁移和原子审批竞态已按 TDD 实现。Task 3 已完成；本地测试数据库密码已轮换并复验。Task 4 已确认采用通用 JSON object payload 方案并固定新工单状态为 `created`；书面规格已落盘，仍待用户复核，生产代码尚未开始。

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
- Task 4 方案 1 与 `created` 初始状态已获确认；书面契约见 `docs/superpowers/specs/2026-07-16-work-order-idempotency-contract-design.md`，当前只进入用户复核门禁。

## 当前阻塞与风险

- 幂等写入与 LangGraph 重启恢复尚未实现，不能声称可靠性内核或发布门禁完成。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开旧的本地测试数据库连接密码；代码、Git 和文档未保存该值，fixture 已改为无密码 URL + 临时 `PGPASSWORD`，角色密码也已轮换和复验。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

请用户复核 Task 4 书面规格；确认后用 writing-plans 回填可执行步骤，再从非法输入、稳定幂等键与 canonical payload hash 的 RED 测试开始。

## 发布门禁

`OperCerta release gate: CLOSED`。本地环境通过不等于发布通过；Linux/Docker 验证和完整可靠性内核证据仍待完成。
