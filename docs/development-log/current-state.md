# OperCerta 当前状态

最后核验：2026-07-15 22:24 Asia/Shanghai，Git commit `3c55f3b`。

## 当前阶段

非法输入与状态恢复已实现；Windows 原生 PostgreSQL 18.4 测试环境已验证。审批领域契约设计已确认，Task 3 已补齐从领域契约 RED 到审批竞态 GREEN 的执行顺序。

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

## 当前阻塞与风险

- PostgreSQL 迁移、审批竞态、幂等写入与重启恢复尚未实现；集成测试可开始，但不能声称并发语义已验证。
- 当前 Git 没有配置远程仓库；本地 commit 不是远程备份。

## 下一步

执行 `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` Task 3 Step 2：先写审批领域契约 RED 测试，观察因模块缺失而失败后再实现最小模型与稳定错误。

## 发布门禁

`OperCerta release gate: CLOSED`。本地环境通过不等于发布通过；Linux/Docker 验证和完整可靠性内核证据仍待完成。
