# OperCerta 幂等工单原子性证据

验证日期：2026-07-16（Asia/Shanghai）
实现基线：`88c014c`
验证范围：Task 4 的领域契约、PostgreSQL 首次授权写入、安全重放、payload 冲突和十路并发数据库事实。

## 环境

- 操作系统：Windows 本机开发环境；PostgreSQL 18.4 服务和 `127.0.0.1:55432` 连接已在 `docs/release-evidence/native-postgres-environment.md` 验证。
- 本轮版本采集：Python 3.12.13、Pydantic 2.13.4、SQLAlchemy 2.0.51、Psycopg 3.3.4、Pytest 9.1.1、Ruff 0.15.21、mypy 2.3.0。
- 本轮 shell 的 `psql` 不在 `PATH`；数据库版本不由该命令重复确认。真实集成测试通过共享 secret-safe Engine fixture 连接本地数据库。
- 数据库连接 URL 和密码未写入本文件，也未由版本或测试命令回显。

## RED 证据

### 领域契约 RED

命令：

```powershell
uv run pytest tests/unit/domain/test_work_orders.py -q
```

实际结果：退出码 1；测试收集因 `IdempotencyConflict` 和 `WriteNotAuthorized` 尚不存在而失败。此时未创建 `domain/work_orders.py`，失败原因与 Task 4 领域契约缺失一致。

### Repository RED

命令：

```powershell
uv run pytest tests/integration/db/test_work_order_idempotency.py -q
```

实际结果：退出码 1；测试收集因 `opercerta.infrastructure.db.work_order_repository` 不存在而失败。此时没有 Task 4 Repository 生产代码。

## GREEN 证据

实际执行结果：

| 验证 | 实际结果 |
| --- | --- |
| `uv run pytest tests/unit/domain/test_work_orders.py -q` | `27 passed in 0.10s` |
| `uv run pytest tests/unit -q` | `56 passed in 0.18s` |
| `uv run pytest tests/integration/db/test_approval_race.py -q` | `4 passed in 0.68s` |
| `uv run pytest tests/integration/db/test_work_order_idempotency.py -q` | `12 passed in 2.04s` |
| `uv run pytest tests/integration/db -q` | `17 passed in 3.26s` |
| `uv run pytest -q` | `73 passed in 3.67s` |
| `uv run ruff check src tests` | `All checks passed!` |
| `uv run ruff format --check src tests` | `20 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 12 source files` |

测试验证的数据库事实包括：

- operation 不存在时抛出 `OperationNotFound`，工单和审计均为零写入；
- 缺少审批、审批为 `rejected`、operation 状态不允许时抛出 `WriteNotAuthorized`，工单、成功审计和审计序号均不改变；
- `resuming`、`executing`、`verifying` 三种状态在已有 `approved` 决定时可首次创建；
- 首次创建的状态为 `created`，`created_at` 与 `updated_at` 相同且带时区；
- 相同 payload 重放返回同一工单 ID，不增加第二条创建审计；
- operation 推进到后续状态后，已有相同结果仍可安全重放；
- 同 operation 改变 payload 时抛出 `IdempotencyConflict`，原工单、payload、审计和序号不变；
- 返回对象中的嵌套 payload 被调用方修改后，数据库快照和后续重放结果不受影响；
- `work_order_created` 审计只保存 `work_order_id`、`idempotency_key`、`payload_hash`，不保存完整 payload。

## 并发复验

命令：

```powershell
1..20 | ForEach-Object {
    uv run pytest tests/integration/db/test_work_order_idempotency.py::test_ten_concurrent_identical_commands_create_effectively_once -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

实际结果：`RACE_REPETITIONS_PASSED=20/20`，总命令耗时 63.7 秒。每轮测试内部启动十个并发调用，并断言恰好一次 `replayed=False`、九次 `replayed=True`、十个结果共享一个工单 ID、数据库只有一行工单和一条 `work_order_created` 审计。

该结果是本地确定性测试重复记录，不是生产成功率、性能指标或服务级别承诺。

## 实施中发现并关闭的问题

- 首次全量 format check 暴露提交 `b37a659` 的三个既有文件与当前 Ruff formatter 不一致。预览确认只有换行变化，机械格式化后审批与迁移测试 `5 passed`，独立提交为 `ca8fbb7`。
- Repository 初版 mypy 注解把 SQLAlchemy 行声明为 `Mapping[str, Any]`；实际 `.mappings()` 返回 `RowMapping`。mypy 以退出码 1 阻止提交，改为具体 `RowMapping` 后完整静态检查通过，事务逻辑未改变。
- PowerShell 原生程序的非零退出码不会被 `$ErrorActionPreference='Stop'` 自动拦截；后续组合门禁均在每条命令后显式检查 `$LASTEXITCODE`。

## 一致性结论

在本地 PostgreSQL 数据库事务边界内，operation 行锁、已有记录优先判断、唯一约束兜底和同事务审计使相同命令达到 effectively-once 业务写入。工作流节点仍可至少执行一次；本证据不把网络、消息队列、真实第三方动作或数据库之外的边界描述为 exactly-once。

## 限制与发布门禁

- Task 5 的 LangGraph 四点重启恢复尚未实现。
- 未调用真实库存、维修、付款或其他第三方系统。
- Linux/Docker 发布环境尚未验证。
- `OperCerta release gate: CLOSED`；本地 Task 4 通过不等于项目发布通过，也不授权启动其他项目。

## 回滚点

- Task 4 实施前计划检查点：`071992b`。
- 领域契约：`6f99bf6`。
- 共享集成测试 Engine fixture：`8408f81`。
- 幂等 Repository 与并发测试：`88c014c`。
