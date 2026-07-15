# OperCerta PostgreSQL 审批原子性证据

## 证据范围

本文件只记录 Windows 原生 PostgreSQL 环境中的迁移和审批竞态实测结果，不代表 Linux/Docker 一致性、幂等工单、LangGraph 重启恢复或 OperCerta 发布门禁已经通过。

## TDD 轨迹

- 审批领域契约首次运行因 `opercerta.domain.approvals` 缺失而 RED；最小实现后目标测试 `10 passed`，提交 `b87ef7f`。
- 迁移契约首次有效运行因 Alembic 缺少 `script_location` 而 RED；创建迁移后目标测试 `1 passed`，迁移提交 `85e6538`。
- 审批竞态首次运行因 `opercerta.infrastructure` 缺失而 RED；实现表映射与 Repository 后目标文件 `4 passed`，提交 `b37a659`。

## 数据库事实

- Alembic 当前版本：`0001_reliability_kernel (head)`。
- 业务表：`operations`、`approvals`、`work_orders`、`audit_events`。
- 检查点 Schema：`langgraph`，与 `public` 业务表分离。
- `approvals.operation_id` 有唯一约束 `uq_approvals_operation_id`。
- `ApprovalRepository.submit_once` 在同一事务中锁定 operation、写入唯一审批、更新为 `resuming` 并追加一个 `approval_recorded` 事件。
- 不存在 operation 返回 `operation_not_found`；非 `awaiting_approval` 状态返回 `approval_already_decided`，两者均验证为零审批/审计写入。

## 新鲜命令结果

- 数据库集成测试：`5 passed`。
- 完整测试：`34 passed`。
- Ruff：`All checks passed!`。
- mypy：`Success: no issues found in 10 source files`。
- 十路审批竞态目标用例独立重复 20 轮：`20/20` 通过；每轮恰好一个 `ApprovalRecord`、九个 `ApprovalAlreadyDecided`，数据库中恰好一条审批和一条审批审计。

以上数字均来自 2026-07-15 Asia/Shanghai 的本机实际命令，不外推为生产性能或稳定性指标。

## Windows 与凭据安全观察

- Psycopg 异步连接不支持 Windows 默认 `ProactorEventLoop`；集成测试在 Windows 使用 `WindowsSelectorEventLoopPolicy`，其他平台不修改事件循环策略。
- Windows PowerShell 创建的 `.env.local` 带 UTF-8 BOM；fixture 使用 `utf-8-sig` 解码。
- 一次预期失败的 Pytest/Psycopg traceback 曾展开本地测试连接密码。该值没有写入源码、Git、本文档或开发日志；fixture 随后改为 `SecretStr`、无密码 SQLAlchemy URL 和临时 `PGPASSWORD`，避免驱动 traceback 携带密码参数。
- 由于密码已经出现在会话失败输出中，本地 `opercerta` 测试角色必须轮换密码并重新验证连接；完成前不得把本文件视为最终安全门禁证据。

## 发布状态

`OperCerta release gate: CLOSED`。
