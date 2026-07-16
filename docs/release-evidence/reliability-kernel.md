# OperCerta 可靠性内核总门禁证据

## 结论与范围

2026-07-16 12:34 Asia/Shanghai，在 Windows 原生 PostgreSQL 开发环境完成可靠性内核 Task 1–6 的新鲜总门禁。验证范围是非法输入、确定性恢复决策、数据库迁移、审批竞态、幂等工单、LangGraph interrupt/checkpoint 和四点重启恢复。

本证据不表示 OperCerta 完整业务闭环、前后端、真实模型/工具、Linux/Docker 或公开部署已经完成。

```text
OperCerta release gate: CLOSED
Verified scope: reliability kernel only
Unverified scope: full five-tool MCP service, complete workflow, API/SSE, React UI, fixed 30-case evaluation, real-model representative paths, public deployment
Next project permitted: no
```

## 基线

- 操作系统：Microsoft Windows 10 企业版 LTSC，Version 10.0.19044，Build 19044
- Python：3.12.13
- PostgreSQL：18.4
- Task 6 开始 Git commit：`88760be`
- 数据库：本机测试数据库；连接 URL 和密码未记录
- 数据：公开概念与合成测试数据，不含旧公司材料

## 锁定依赖

- Pydantic 2.13.4
- SQLAlchemy 2.0.51
- Psycopg 3.3.4
- Alembic 1.18.5
- LangGraph 1.2.9
- langgraph-checkpoint 4.1.1
- langgraph-checkpoint-postgres 3.1.0
- Pytest 9.1.1
- pytest-asyncio 1.4.0
- Ruff 0.15.21
- mypy 2.3.0

## Task 6 新鲜门禁

按顺序执行并观察：

1. `uv sync --frozen --all-groups`：退出码 0，输出 `Checked 84 packages in 3ms`。
2. `uv run pytest tests/unit tests/integration -q`：退出码 0，`116 passed in 8.76s`。
3. `uv run ruff check src tests`：退出码 0，`All checks passed!`。
4. `uv run ruff format --check src tests`：退出码 0，`32 files already formatted`。
5. `uv run mypy src`：退出码 0，`Success: no issues found in 19 source files`。
6. 首次直接执行 `uv run alembic downgrade base`：退出码 1，原因是独立 Alembic 进程未注入 `OPERCERTA_DATABASE_URL`；错误发生在迁移连接与 downgrade 之前，未修改数据库，也未展开密码。
7. 复用集成测试的 SecretStr、无密码 URL 和临时 `PGPASSWORD` 边界后，在同一 secret-safe 进程执行 `downgrade base → upgrade head → current`：退出码 0，当前版本为 `0001_reliability_kernel (head)`。
8. 迁移升降级后执行 `uv run pytest tests/integration -q`：退出码 0，`39 passed in 8.74s`。
9. `git diff --check`：退出码 0；门禁开始与迁移复验后工作区均为干净 `main`。

测试数量和耗时仅是本次命令输出，不作为生产容量、稳定率或 SLA。

## 已验证不变量

### 非法输入与快照

- 严格 Pydantic 模型拒绝未知字段、错误 UUID、非法枚举、非 JSON 值、非字符串 object key、tuple、`NaN` 和正负无穷。
- 恢复快照缺字段或错误 `schema_version` 时不调用模型或默认值补齐。

### 确定性恢复决策

- `RecoveryFacts` 对相同业务事实返回唯一 `RecoveryAction`。
- 工单无审批、received 状态已有审批等不可能组合被明确拒绝。

### 审批原子性

- 十路并发审批只接受一个决定，其余九个为分类冲突。
- 审批、operation `resuming` 状态和 `approval_recorded` 审计同事务提交。
- 独立进程重复证据见 `docs/release-evidence/approval-atomicity.md`。

### 工单幂等性

- 十路相同命令只创建一个工单，其余安全重放并返回同一 ID。
- 同键异参分类为冲突；未批准或错误状态不能首次写入。
- 工单、审计序号和 `work_order_created` 同事务提交。
- 独立进程重复证据见 `docs/release-evidence/work-order-idempotency.md`。

### LangGraph 重启恢复

- checkpoint 表只位于独立 `langgraph` Schema；state 只保存 plain JSON。
- 首 checkpoint 前重建、等待审批保持、批准后恢复、拒绝后恢复、工单预写安全重放均使用关闭的 A 实例和新 B 实例验证。
- 等待路径零自动审批/零工单；拒绝路径零工单；批准路径一条审批/一条工单；预写路径返回原工单 ID 与 `replayed=True`。
- 关闭 checkpointer 时保留真实基础设施异常和最后已提交业务事实。
- 十个独立 Pytest 进程的 Task 5 矩阵实测 `10/10`，每轮 `8 passed`；详细证据见 `docs/release-evidence/langgraph-restart-recovery.md`。

## 未验证范围

- MCP 五工具实现和真实外部工具调用；
- 完整 event → evidence → risk → plan → approval → write → verify → audit 纵向业务闭环；
- FastAPI、SSE、JWT、RBAC、React UI 和人工接管界面；
- 固定 30-case 评测、真实模型代表路径、安全回归和可观测性；
- Docker、Linux 一致性、云托管、域名、HTTPS 和公开部署；
- 多 Worker、租约、心跳、跨区域容灾和分布式 exactly-once。

## 下一实施边界

可靠性内核在当前本地范围冻结，不继续增加底层框架功能。下一阶段仍只实施 OperCerta，优先建立一个可运行纵向闭环：

```text
event input
  → evidence collection
  → deterministic risk/plan
  → approval interrupt
  → simulated MCP write
  → verification
  → audit
  → API structured response
```

在上述闭环、前端、评测、安全、Linux/Docker 和公开部署门禁完成前，发布门禁保持 `CLOSED`，不得启动 ForenTrail。

## 回滚点

- Task 1 输入契约：`642fc2f`
- Task 2 恢复决策：`8bcf7c3`
- Task 3 原子审批：`b37a659`
- Task 4 幂等工单：`88c014c`
- Task 5 快照到重启恢复：`8fb054e`、`5bdacf7`、`e9b2834`、`2e6cbb4`、`e93b551`
- Task 5 证据：`88760be`
