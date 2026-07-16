# OperCerta LangGraph 四点重启恢复证据

## 验证范围

本证据只覆盖可靠性内核 Task 5：冻结业务快照、operation 状态与审计原子迁移、独立 PostgreSQL checkpointer、JSON-only LangGraph、批准/拒绝正常路径、四点进程等价重启和工单幂等重放。

验证使用合成业务 payload，不调用模型、MCP、真实库存/维修/付款系统，不覆盖多 Worker、Docker/Linux、API/SSE、前端或公开部署。

## 环境与锁定版本

核验时间：2026-07-16 12:24 Asia/Shanghai。

- Python 3.12.13
- PostgreSQL 18.4
- Pydantic 2.13.4
- SQLAlchemy 2.0.51
- Psycopg 3.3.4
- LangGraph 1.2.9
- langgraph-checkpoint 4.1.1
- langgraph-checkpoint-postgres 3.1.0
- Pytest 9.1.1
- pytest-asyncio 1.4.0
- Ruff 0.15.21
- mypy 2.3.0

数据库 URL、角色密码和 `.env.local` 内容未写入本文件或 Git。

## RED 证据

按生产实现之前的实际执行顺序观察到以下失败：

1. `uv run pytest tests/unit/domain/test_operation_state.py -q`：退出码 1，收集时缺少 `InvalidOperationSnapshot`。
2. `uv run pytest tests/integration/db/test_operation_state_repository.py -q`：退出码 1，缺少 `operation_state_repository` 模块。
3. `uv run pytest tests/integration/workflow/test_checkpoints.py -q`：退出码 1，缺少 `opercerta.infrastructure.checkpoints`。
4. DSN 专项回归先证明 URL 中仍包含密码，随后证明 SQLAlchemy `URL.set(password=None)` 不会清除密码；两次均退出 1。
5. `uv run pytest tests/integration/workflow/test_reliability_graph.py -q`：退出码 1，缺少 `opercerta.workflow`。
6. `uv run pytest tests/integration/workflow/test_restart_recovery.py -q`：退出码 1，缺少 `recovery_coordinator`。

这些失败均发生在对应生产实现之前。一次 checkpointer 连接失败 traceback 展开了当时的本地测试密码；该值未进入代码或 Git，DSN 封装修复后用户已轮换角色密码与 `.env.local`，轮换后 focused checkpointer 回归为 `4 passed`。

## GREEN 证据

- 快照领域与 Task 4 JSON 回归：focused `48 passed`；单元全集 `77 passed`。
- operation 状态仓储：focused `7 passed`；数据库集成全集 `24 passed`。
- checkpointer：focused `4 passed`；与数据库集成组合 `28 passed`。
- reliability graph：focused `3 passed`；当时 workflow 集成 `7 passed`。
- RecoveryCoordinator 与重启矩阵：focused `8 passed`；最终 workflow 集成 `15 passed`。
- 最终完整命令 `uv run pytest -q`：`116 passed in 9.96s`，退出码 0。
- `uv run ruff check src tests`：`All checks passed!`。
- `uv run ruff format --check src tests`：`32 files already formatted`。
- `uv run mypy src`：`Success: no issues found in 19 source files`。
- `git diff --check`：退出码 0。

## Checkpointer Schema 与严格序列化

- `checkpointer.setup()` 只由测试 session bootstrap 显式执行一次。
- 测试直接查询 `information_schema.tables`，确认 `checkpoint_migrations`、`checkpoints`、`checkpoint_blobs`、`checkpoint_writes` 只位于 `langgraph` Schema，不位于 `public`。
- graph A 写入 plain JSON 后释放 saver A；graph B 使用新 saver 读取相同 operation ID 与嵌套 JSON payload。
- `LANGGRAPH_STRICT_MSGPACK` 缺失时 `open_checkpointer()` 明确拒绝构造 saver。
- checkpointer DSN 不包含密码，SQLAlchemy 驱动名转换为 Psycopg URL，`search_path` 空格使用 `%20` 编码。

## 四点 A/B 重启矩阵

每个场景都关闭 saver A 的 Psycopg 连接并丢弃 graph A，再用 saver B/graph B 恢复。

| 重启点 | 实测动作 | 数据库最终事实 |
| --- | --- | --- |
| operation 已保存、首个 checkpoint 前 | `REBUILD_FROM_BUSINESS_FACTS` | `awaiting_approval`；零审批、零工单；一条 `approval_requested` |
| 图已在审批处 interrupt | `KEEP_WAITING` | 恢复前后业务事实完全相同；零自动审批、零工单 |
| 审批批准已提交、图未恢复 | `RESUME_DECISION` | `completed`；一条审批、一条工单、一条 `work_order_created`、一条 `operation_completed` |
| 审批拒绝已提交、图未恢复 | `RESUME_DECISION` | `rejected`；一条审批、零工单、一条 `operation_rejected` |
| 工单已提交、图仍停在旧 interrupt | `RESUME_DECISION` | 最终 graph state 为原工单 ID、`replayed=True`；数据库仍只有一条工单和一条 `work_order_created` |

## 数据库最终事实

- 每个批准恢复场景只有一条 `approval_recorded`。
- 拒绝恢复场景没有 `work_order_created`。
- 工单预写恢复返回原 ID，没有第二条工单或创建审计。
- checkpoint operation ID 与业务 thread ID 不一致时抛出 `RecoveryStateConflict`，目标 operation 业务事实不变。
- 终态业务行仍带 pending interrupt 时抛出 `RecoveryStateConflict`，不选择方便路径继续。
- graph/checkpointer 已关闭时保留真实 Psycopg 基础设施异常；已提交审批保持 `resuming`，没有工单或伪造成功终态。

## 独立进程重复验证

执行命令：

```powershell
1..10 | ForEach-Object {
    uv run pytest tests/integration/workflow/test_restart_recovery.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

实际结果：十个独立 Pytest 进程全部退出 0，每轮 `8 passed`，汇总输出 `IndependentRestartRuns=10/10`。这是本地确定性复验次数，不是生产成功率、SLA 或效果指标。

## 基础设施失败保持的业务事实

关闭 saver B 后调用 `RecoveryCoordinator.recover()`，测试捕获真实 `psycopg.OperationalError`。随后直接查询 PostgreSQL，确认 operation 仍为 `resuming`、原审批 ID 仍唯一、工单数为零、`approval_recorded` 仍只有一条。

## 限制、未验证范围与发布门禁

- 本证据不证明多 Worker 调度、租约、心跳、跨区域容灾或分布式 exactly-once。
- 本证据不覆盖真实模型、MCP、五工具完整服务、API/SSE、认证、React UI、固定 30-case 评测、Linux/Docker 或公开部署。
- Task 5 的恢复保证是 PostgreSQL 业务事实优先、checkpoint 可重放、业务副作用 effectively-once，不声称 checkpoint 与业务事务构成分布式原子提交。
- Task 6 可靠性内核总证据与迁移升降级门禁尚未执行。

```text
OperCerta release gate: CLOSED
Verified scope: Task 5 restart recovery only
Next project permitted: no
```

## Git 回滚点

- Task 5 聚焦计划：`b8b9ae2`
- 快照领域边界：`8fb054e`
- operation 原子状态仓储：`5bdacf7`
- 独立 checkpointer：`e9b2834`
- JSON-only reliability graph：`2e6cbb4`
- RecoveryCoordinator 与重启矩阵：`e93b551`
