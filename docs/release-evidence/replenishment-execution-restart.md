# OperCerta 库存补货执行与重启恢复证据

## 结论与范围

2026-07-16 21:44 Asia/Shanghai，在 Windows 原生 PostgreSQL 环境完成库存补货纵向切片 Task 7 的本地验证。

本证据覆盖绑定审批后的拒绝、事实重取、幂等 MCP 工单写入、写后读验证、审批过期、应用层 Runner 和 A/B checkpointer 重启恢复。它不表示 FastAPI、前端、Linux/Docker 或公开部署已经完成。

```text
OperCerta release gate: CLOSED
Verified scope: inventory replenishment Task 7 only
Next project permitted: no
```

## TDD RED 证据

1. 审批后图测试首次执行为 `4 failed, 6 passed`。批准、拒绝、事实变化和回读不一致四个新测试均停在 `resuming`，证明原图在审批恢复后直接结束。
2. A/B 重启测试首次在收集阶段退出 1，错误为缺少 `opercerta.application.operation_runner`，当时 Runner 与补货专用恢复协调器均未实现。

## 审批后执行不变量

- 拒绝决定写入 `rejected`，不调用 `work_order.create`，数据库零工单。
- 批准决定在写入前重新调用 MCP 读取库存与规则，并保存两条 refresh evidence。
- 重取事实使用原批准计划的 summary/rationale 重建确定性计划，不再次调用模型，不覆盖原批准计划。
- 比较字段只包括规则版本、事实 hash、计划 hash 和建议数量；新鲜 evidence ID 仅作为刷新记录，不替换原审批 provenance。
- 事实变化时写入终态错误 `approval_snapshot_mismatch`，不创建工单。
- 工单命令 payload 精确包含 `sku`、`quantity` 和 `approved_plan_hash`。
- 工单回读比较 ID、operation ID、payload 和 payload hash；不一致时写入 `work_order_verification_failed`。
- 成功路径最后四个审计事件为 `execution_started`、`work_order_created`、`verification_started`、`operation_completed`。

## A/B 重启矩阵

每个重启测试都关闭 saver A，再创建 saver B：

| 断点 | 恢复动作或处理 | 最终业务事实 |
| --- | --- | --- |
| operation 已保存、首 checkpoint 前 | `REBUILD_FROM_BUSINESS_FACTS` | `awaiting_approval`；零审批、零工单 |
| 等待审批 interrupt | `KEEP_WAITING` | 业务事实不变；零审批、零工单 |
| 绑定批准已提交 | `RESUME_DECISION` | `completed`；一条审批、一条工单 |
| 绑定拒绝已提交 | `RESUME_DECISION` | `rejected`；一条审批、零工单 |
| 工单已预写 | 审批恢复后安全重放并验证 | 原工单 ID；一行工单；一条创建审计；`replayed=True` |
| 审批在停机期间到期 | Runner 先执行到期扫描 | `expired`；零审批、零工单 |

## 新鲜验证命令

- `uv run pytest tests/integration/workflow/test_replenishment_graph.py tests/integration/workflow/test_replenishment_restart.py -q`：`17 passed in 23.85s`。
- `uv run pytest tests/integration/workflow -q`：`32 passed in 26.63s`。
- 重启测试串行重复 10 次：每次 `7 passed`，共观察 70 个测试用例通过。
- `uv run pytest -q`：`275 passed in 43.78s`。
- `uv run ruff check src tests`：`All checks passed!`。
- `uv run ruff format --check src tests`：`60 files already formatted`。
- `uv run mypy src`：`Success: no issues found in 32 source files`。

上述次数和耗时只记录本次本地命令输出，不作为生产成功率、性能、容量或 SLA。

## 实现与回滚点

- 实现提交：`9b830d2 feat: execute approved replenishment`
- 主要实现：
  - `src/opercerta/workflow/replenishment_graph.py`
  - `src/opercerta/workflow/replenishment_recovery.py`
  - `src/opercerta/application/operation_runner.py`
- 主要测试：
  - `tests/integration/workflow/test_replenishment_graph.py`
  - `tests/integration/workflow/test_replenishment_restart.py`

## 未验证范围

- FastAPI 创建、查询和绑定审批 HTTP 边界；
- SSE、认证、React UI 和人工接管界面；
- 固定评测集、真实模型代表路径、安全回归和可观测性；
- Linux/Docker 一致性、云托管、HTTPS 和公开部署；
- 多 Worker 调度、租约、心跳、跨区域容灾或分布式 exactly-once。
