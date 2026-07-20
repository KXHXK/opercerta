# 三业务固定评测、Compose 与性能矩阵证据

## 结论与边界

2026-07-20 在 WSL2 Ubuntu 26.04 LTS、Docker Engine 29.1.3、Compose 2.40.3 上完成本地单节点验证。库存补货、设备维修、作业异常恢复共 42 条固定合成契约全部通过；Compose smoke 覆盖三条批准写入、设备拒绝零写入、重复审批冲突、PostgreSQL 事实断言，以及 API/MCP 重启后的待审批恢复。

这些结果是本机合成数据证据，不是生产 SLA、容量结论或公网部署证明。性能矩阵每格只有 5 次请求，延迟仅供复现缓存行为，不据此宣称并行一定优于串行。

## 固定评测

```powershell
.venv\Scripts\python.exe scripts/run_opercerta_evaluation.py --output-dir tmp/evals/task7
```

- 套件：`opercerta-three-business-v1`
- 边界：真实 FastAPI + FastMCP + PostgreSQL 测试夹具
- 库存 30 条、设备 6 条、作业 6 条；总计 42 passed、0 failed
- 每个新增用例记录期望/实际 HTTP 状态、终态、审批数、工单数、审计事件和 MCP 工具名；新增 12 条以 `extends` 继承原 30 条并冻结顺序。

## Compose 三业务与重启恢复

同一 WSL 会话执行：

```bash
docker compose up -d
python3 scripts/verify_compose.py
docker compose exec -T redis redis-cli DBSIZE
docker compose restart api mcp
python3 scripts/verify_compose.py --recovery-only
docker compose ps
```

- 三个场景批准后分别只产生一张 `replenishment`、`repair`、`task_recovery` 工单。
- 重复审批返回 `approval_already_decided`；设备拒绝后零工单。
- PostgreSQL 断言审批、工单和终态一致；Redis `DBSIZE=8`。
- 重启 API/MCP 后，重启前创建的作业 operation 仍为 `awaiting_approval`，审批数与工单数均为 0。
- 容器健康后执行 `docker compose down -v --remove-orphans` 清理合成数据。

## 2×2 缓存/工具模式矩阵

```bash
bash scripts/run_performance_matrix.sh tmp/performance-task7-final
```

脚本强制重建当前工作树镜像，为每种模式重建 API，并在每格开始前清空 Redis。每格按库存、设备、作业各执行 5 次只读 query；60/60 个 operation 的业务终态均为 `completed`，error rate 全为 0，模型调用与 token 均为 0（query 路径按契约不调用模型）。

| 缓存 | 工具读取 | 场景 | P50 ms | P95 ms | MCP 调用 | Cache hit |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 关 | 并行 | 设备 | 201.974 | 260.608 | 10 | 0 |
| 关 | 并行 | 库存 | 214.834 | 268.039 | 10 | 0 |
| 关 | 并行 | 作业 | 233.771 | 266.360 | 10 | 0 |
| 关 | 串行 | 设备 | 237.287 | 305.813 | 10 | 0 |
| 关 | 串行 | 库存 | 230.264 | 299.501 | 10 | 0 |
| 关 | 串行 | 作业 | 243.612 | 253.988 | 10 | 0 |
| 开 | 并行 | 设备 | 85.091 | 200.197 | 2 | 8 |
| 开 | 并行 | 库存 | 86.883 | 264.333 | 2 | 8 |
| 开 | 并行 | 作业 | 91.277 | 214.768 | 2 | 8 |
| 开 | 串行 | 设备 | 112.557 | 240.586 | 2 | 8 |
| 开 | 串行 | 库存 | 94.774 | 249.284 | 2 | 8 |
| 开 | 串行 | 作业 | 118.343 | 324.801 | 2 | 8 |

可证明结论仅是：启用缓存时每场景第一次 query 的两份证据来自 MCP，随后四次各命中两份证据，因此 MCP 调用由 10 降为 2、命中为 8；禁用缓存时保持 10 次 MCP 调用。并行/串行延迟受本机容器调度影响且样本过小，不作性能优劣承诺。

## 诊断记录

第一次矩阵得到 MCP 调用数 0。原因为编排复用了 Task 6 旧镜像：其中已有 Redis 指标，但没有 Task 7 新增的 MCP 指标。修复不是改业务逻辑，而是让矩阵脚本执行 `docker compose up --build -d`，并以 RED/GREEN 资产测试固定该要求。新镜像重跑后所有调用/命中不变量均成立。

## 提交前总门禁

- `uv lock --check`：通过
- `ruff check .`：通过
- `ruff format --check .`：134 files already formatted
- `mypy src`：62 个源文件无问题
- 仓库安全扫描：通过
- 完整后端：414 passed in 103.80s

一次完整回归曾出现设备 MCP 临时 503，并让已创建但未返回 ID 的测试 operation 污染后续恢复扫描。单独与前置序列复现均通过；确认并精确清理专用测试库残留后，测试 harness 改为在 Repository 创建成功时立即跟踪 ID，而不是等 HTTP 202 才登记。修复后 API/恢复聚焦 17 条通过，随后总门禁取得上述 414 条全绿结果。
