# Agent 审批后 Verifier、复审与幂等执行证据

日期：2026-07-22（Asia/Shanghai）  
范围：Agent 核心架构 Task 5  
发布门禁：`CLOSED`

## 本阶段实现

- 库存补货、设备维修、任务恢复共用批准后复核语义：直连 MCP 重新取证，绕过只读 Redis 缓存。
- Verifier 只产生 `proceed`、`abort`、`escalate`、安全理由和可选非权威计划提议；写参数仍由确定性 Policy Guard 重新计算。
- `proceed` 仅在批准 binding 与新事实一致、模型未提出变更时执行；`abort` 安全终止且零工单；`escalate` 或任意动作/对象/参数漂移进入 `needs_reapproval`。
- PostgreSQL 新增审批周期：操作保存当前 `approval_cycle`，审批唯一键改为 `(operation_id, approval_cycle)`；旧批准不能授权新周期写入。
- 复审状态迁移支持“数据库已提交、检查点未保存”后的幂等重放；审计事件记录原审批 ID、周期和新 binding。
- 工单仍使用 operation 派生的幂等键，只有当前周期的有效批准才能授权首次写入，写后通过 MCP 回读核验。

## TDD 与故障复盘

1. 初始 RED 证明旧图没有调用 Verifier，`abort/escalate` 会错误继续完成。
2. 新增模型计划漂移 RED 后，严格契约最初拒绝 `proposed_plan`；补充非权威提议字段并由确定性路由强制复审。
3. 第二审批周期首次 RED 触发 `MultipleResultsFound`，定位到工单授权查询没有限定当前周期；改为按 operation 当前周期查询。
4. 全量回归发现旧可靠性内核仍把 operation 留在周期 0；修复进入待审批时原子写入周期 1，并让恢复查询只关联当前周期审批。
5. 审查阶段新增崩溃窗口 RED：复审迁移提交后重放会把旧审批误判为过期；改为先核验目标状态与审计载荷，再执行新迁移的审批校验。

## 新鲜验证

- Task 5 定向数据库与工作流门禁：`48 passed in 41.69s`。
- 完整工作流：`62 passed in 73.82s`。
- 后端产品测试（应用容器，排除需要 Git 可执行文件的 4 条安全脚本）：`502 passed in 174.52s`。
- 仓库安全脚本（WSL 原生 Git + 同一 Python 依赖）：`4 passed in 0.27s`。
- Ruff：通过。
- mypy：`Success: no issues found in 70 source files`。
- Alembic `0004_approval_cycles` upgrade/downgrade 与历史数据回填：`2 passed`（与基础迁移测试合并）。

## 证据边界

- 本阶段不包含 Task 6 的 pgvector/RAG，也不包含 Task 7 的产品级 Agent Trace 表、API/SSE 和前端 Trace 展示。
- “Trace 持久化前重启”必须等真实 Trace 表存在后验证，不能用 audit event 冒充。
- 当前只证明本机 WSL2、Docker、PostgreSQL 和合成业务数据上的工程行为，不声称生产吞吐、成功率、模型质量或公网可用性。
- 旧演示工作树的 bootstrap 镜像只认识到迁移 0003；本分支测试只复用其 PostgreSQL/Redis 容器，由当前源码执行迁移和测试。合并后必须重建应用镜像再做 Compose 门禁。
