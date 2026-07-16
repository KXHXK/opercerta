# OperCerta 库存补货后端纵向闭环证据

## 验证范围与结论

2026-07-16，在 Windows 原生 PostgreSQL 18.4 环境完成“库存不足 → 补货工单”后端纵向闭环 Task 1–9 的本地验证。本证据只记录实际命令、Git 提交和数据库查询结果，不把本地重复次数解释为生产成功率、容量、性能或 SLA。

```text
OperCerta release gate: CLOSED
Verified scope: inventory replenishment backend vertical slice only
Unverified scope: equipment scenario, React, SSE, JWT/RBAC, real model, Redis, observability, Docker/Linux, public deployment
Next project permitted: no
```

## 环境、锁定版本与 Git 基线

- 操作系统：Windows 本机开发环境。
- 数据库：PostgreSQL 18.4，仅使用已验证的本机回环测试实例；本文件不保存连接串或密码。
- Task 9 起始 Git 基线：`0f782b8 docs: record replenishment api task`，分支为 `main`，工作树为空。
- `uv sync --frozen --all-groups`：退出码 0，输出 `Checked 84 packages in 7ms`。
- 本地安装与锁定的主要版本：
  - OperCerta `0.1.0`
  - Alembic `1.18.5`
  - FastAPI `0.139.0`
  - HTTPX `0.28.1`
  - LangGraph `1.2.9`
  - `langgraph-checkpoint-postgres` `3.1.0`
  - MCP Python SDK `1.28.1`
  - Psycopg `3.3.4`
  - Pydantic `2.13.4`
  - Pydantic Settings `2.14.2`
  - SQLAlchemy `2.0.51`
  - Uvicorn `0.51.0`
  - Pytest `9.1.1`
  - Ruff `0.15.21`
  - mypy `2.3.0`

## TDD RED/GREEN 记录

- Task 1：领域契约先因新错误/模块缺失 RED；严格整数回归又先得到 `42 failed`。使用 `StrictInt` 后 focused `59 passed`、unit `136 passed`；实现提交 `4a04113`、`b87b609`。
- Task 2：Alembic 先明确找不到 `0002_inventory_replenishment`，Repository 测试先因模块缺失 RED；迁移、证据和 operation 持久化实现提交 `c035a46`、`c6d9f92`、`ef2ec15`。
- Task 3：绑定审批和过期服务先因领域命令、应用模块缺失产生 2 个收集错误；修正时区断言后 focused `13 passed`，实现提交 `d97c5bb`。
- Task 4：真实 MCP 服务测试先因 `opercerta.tools` 缺失 RED；实现四工具后完整测试 `246 passed`，提交 `9b74f9d`。
- Task 5：类型化 MCP gateway 测试先因模块缺失 RED；实现 allowlist、有限重试和结构化复验后 focused `12 passed`，提交 `d2faf57`。
- Task 6：审批前工作流测试先因 `replenishment_graph` 缺失 RED；实现后完整测试 `264 passed`，提交 `415b776`。
- Task 7：审批后四条新分支先为 `4 failed, 6 passed`；A/B 恢复测试先因 Runner 模块缺失 RED。实现后图 focused `10 passed`、重启 focused `7 passed`，提交 `9b830d2`。
- Task 8：API 测试先因 `opercerta.api` 缺失 RED；设备查询曾错误返回 `202`、OpenAPI 时间曾缺少 `date-time`、Engine 构造错误曾遗留临时环境值，均先用回归暴露再修正。最终 API focused `8 passed`，提交 `c4ac3ab`。

## `0002` 迁移与数据库不变量

- 使用 `SecretStr`、无密码 URL 和临时 `PGPASSWORD` 边界执行迁移；命令输出未显示连接 URL。
- `alembic downgrade 0001_reliability_kernel`：退出码 0。
- `alembic upgrade head`：退出码 0。
- `alembic current`：`0002_inventory_replenishment (head)`。
- 迁移恢复后的 `uv run pytest tests/integration -q`：`131 passed in 55.39s`。
- Task 9 真实传输查询确认：目标 operation 恰好一条审批、一条工单；终态审计按 sequence 排序。

## 四个真实 MCP 工具与传输证据

独立 FastMCP 服务进程通过 Streamable HTTP 暴露并由独立客户端列出以下四个精确名称：

1. `inventory.get_snapshot`
2. `policy.list_constraints`
3. `work_order.create`
4. `work_order.get`

服务只绑定运行时选择的临时回环端口，端口没有写入永久架构。HTTP/MCP 客户端使用 `trust_env=False`，业务写入仍由审批事实和稳定幂等键约束。

## 正常库存与安全失败路径

- 正常库存不调用模型生成补货计划，不请求审批，不创建工单，以 `replenishment_not_required` 完成。
- SKU 不存在、库存/规则证据不可用、非法结构化输出、超规则数量和过期证据均安全失败，不进入工单写入。
- 未知 MCP 工具在创建网络会话前被本地 allowlist 拒绝。
- MCP 未知错误文本、数据库连接细节和 traceback 不进入稳定领域错误或 API 响应。

## 批准、拒绝、过期与快照变化

- 审批绑定库存 evidence ID、规则 evidence ID、规则版本、决策事实 hash、计划 hash 和建议数量。
- 拒绝路径终止为 `rejected`，零工单。
- 审批过期路径终止为 `expired`，零审批写入、零工单。
- 批准后写入前重新读取库存与规则；绑定事实变化时以 `approval_snapshot_mismatch` 失败，旧批准不能授权新事实。
- Task 9 真实传输中，低库存 SKU 的绑定建议数量为 `18`，批准后完成，重复提交同一审批返回 HTTP `409`。

## 幂等写入、回读与 A/B 重启

- 工单幂等键由 operation ID 稳定派生；相同 payload 安全重放，不同 payload 冲突关闭。
- `work_order.create` 后必须调用 `work_order.get`，比较工单 ID、operation ID、payload 和 payload hash。
- 预写工单恢复保留原工单 ID，数据库保持一行工单和一条创建审计。
- Task 9 审批十路竞态目标测试以 10 个独立 Pytest 进程复验，完成 `10/10`；每轮 `1 passed, 10 deselected`。
- Task 9 A/B 重启恢复测试以 10 个独立 Pytest 进程复验，完成 `10/10`；每轮 `7 passed`。
- 上述重复次数只证明本机本轮可重复执行，不代表生产概率或吞吐。

## FastAPI 创建、查询与审批

- `POST /api/v1/operations`：严格接收库存补货创建请求；真实传输返回 `202` 和 `awaiting_approval`。
- `GET /api/v1/operations/{id}`：返回请求、证据、assessment、plan、`approval_binding`、审批、工单、结果、错误和最后审计序号。
- `POST /api/v1/operations/{id}/approval`：使用查询返回的六字段 binding 提交审批；真实传输批准后返回 `202 completed`。
- 重复审批真实返回 HTTP `409` 和稳定 code `approval_already_decided`。
- 数据库真实查询为 `approval_rows=1`、`work_order_rows=1`；最后四个审计事件依次为 `execution_started`、`work_order_created`、`verification_started`、`operation_completed`。

## 完整测试与静态检查

- `uv run pytest -q`：`283 passed in 57.94s`。
- 文档完成后的提交前复验：`283 passed in 56.41s`，`uv sync --frozen --all-groups` 输出 `Checked 84 packages in 6ms`。
- `uv run ruff check src tests migrations`：`All checks passed!`。
- `uv run ruff format --check src tests migrations`：`68 files already formatted`。
- `uv run mypy src`：`Success: no issues found in 35 source files`。
- `git diff --check`：退出码 0。

真实双服务首次启动在业务调用前失败：Uvicorn 0.51 的 Windows 单进程默认 loop factory 创建 `ProactorEventLoop`，Psycopg async 明确要求兼容的 Selector loop。读取本机 Uvicorn 实现后，用其 custom loop factory 接口显式指定 `asyncio:SelectorEventLoop`；最小启动探针先确认可监听，再运行完整三进程闭环。此项是 Windows 本地运行约束，不等于 Linux/Docker 已验证。

## 凭据与响应安全扫描

- 数据库配置只从进程环境或已忽略的 `.env.local` 读取。
- 迁移、真实服务和数据库查询均使用无密码连接 URL 与临时 `PGPASSWORD` 边界；未把连接串写入文档或 Git。
- API 固定错误 envelope 不包含异常字符串、数据库地址、密码、traceback 或 MCP 内部未知文本。
- 文档凭据模式扫描和占位文本扫描均退出 0 且零匹配；Markdown 根文档链接检查为 `markdown_link_missing=0`。

## 未验证范围与发布门禁

- 设备告警/维修工单等其他三个首版业务场景尚未形成同等级闭环证据。
- React、SSE、JWT/RBAC、可信身份、真实模型、Redis、可观测性、固定评测与安全回归尚未完成。
- Docker/Linux 一致性、云托管、HTTPS、公开域名、备份恢复、生产多 Worker 调度和分布式容灾尚未验证。
- 因此本证据只关闭库存补货后端纵向切片的本地 Task 1–9，不打开发布门禁，不允许开始 ForenTrail。

## Git 回滚点

- Task 1–8 后端纵向切片基线：`0f782b8 docs: record replenishment api task`。
- API 实现回滚点：`c4ac3ab feat: expose replenishment api`。
- 审批后执行与恢复回滚点：`9b830d2 feat: execute approved replenishment`。
- 审批前工作流回滚点：`415b776 feat: plan inventory replenishment`。
- MCP gateway 回滚点：`d2faf57 feat: validate mcp tool calls`。
- MCP 服务回滚点：`9b74f9d feat: serve replenishment mcp tools`。
- 本文件与同步日志由 `docs: record replenishment slice evidence` 原子提交保存；实际 commit 可通过 `git log -1 --oneline` 核验。
