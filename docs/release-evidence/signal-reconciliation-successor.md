# Signal 历史对账与后继调查证据

日期：2026-07-25
分支：`feat/agent-core-implementation`
基线提交：`d49577b`
结论：本地 Mock/Compose 纵向切片通过；生产发布门禁仍为 `CLOSED`。

## 1. 修复的问题

旧持久卷中存在 operation 已经 `expired`，关联 signal 却仍为 `investigating` 的历史遗留状态。原界面还缺少失败后的恢复入口：再次扫描会因相同事实哈希复用原 signal，operator 无法在保留旧审批与旧 operation 的前提下启动后继调查。

本次采用两项非破坏性修复：

1. production 启动先恢复 operation，再按 operation 终态对账关联 signal：
   - `completed/rejected → resolved`
   - `aborted/expired/failed → attention_required`
2. `attention_required` signal 通过 operator-only retry 创建一个带 `predecessor_signal_id` 的后继 signal，再创建并绑定新的 operation。旧 signal、旧 operation、旧审批和旧审计均不修改。

数据库唯一约束保证一个 predecessor 最多只有一个 successor；并发请求不能创建分叉调查链。

## 2. RED / GREEN 过程

### RED

- Python 领域测试首先因 `derive_signal_retry_dedup_key` 与 retry 错误契约缺失而 ImportError。
- React 测试首先因 API Client 没有 `retrySignal` 且页面没有“重新调查”入口而失败。
- 首次执行 `0008` 迁移时，PostgreSQL 拒绝超过 63 字节的自动约束名；约束名显式缩短为 `fk_signal_predecessor` 后迁移成功。
- 浏览器验证发现扫描响应只返回三条根 signal，导致已经存在的 successor 无法显示。先增加 App RED 测试，再在扫描成功后读取活动 signal 列表，失败时才回退扫描响应。

这些失败分别证明契约、UI、数据库可移植性和运行态谱系展示确实存在缺口，不是先写实现再补“必过测试”。

### GREEN

- `operational_signals.predecessor_signal_id` 为 nullable 自引用外键，采用 `RESTRICT`，并有唯一约束。
- `SignalRepository.reconcile_terminal_links()` 加行锁、幂等更新，只处理仍为 `investigating` 且 operation 已终态的行。
- `SignalRepository.create_successor()` 加锁 predecessor，只接受 `attention_required`，复制原受控事实并返回唯一 successor。
- `POST /api/v1/signals/{signal_id}/retry` 仅允许 operator；服务端生成 retry key，不信任客户端提供谱系或去重键。
- React 对可重试 signal 显示“重新调查”；发现 successor 后隐藏重复入口并显示谱系提示。

## 3. 自动化门禁

- 领域 focused：`13 passed`
- 前端 focused：`13 passed`
- 数据库/API focused（含迁移往返、对账幂等、十路并发）：`12 passed`
- 完整后端：`607 passed in 329.96s`
- 完整前端：18 个测试文件，`58 passed`
- 前端 production build：成功
- Ruff lint：`All checks passed!`
- Ruff format：199 个文件格式正确
- mypy：80 个源文件无问题

测试使用一次性数据库容器，结束后已清理。

## 4. 真实本地持久卷与重启验证

启动对账前：

- 库存 signal：`investigating`，关联 operation：`expired`
- 任务 signal：`investigating`，关联 operation：`expired`
- 设备 signal：`attention_required`

启动对账后，三个根 signal 均为 `attention_required`，三条旧 operation 仍为 `expired`，证明修复没有重写历史操作。

对库存 predecessor `57cb635c-07bb-41b3-bd7e-b579b810bb01` 发起真实本地 retry：

- successor signal：`2cef23d3-1b30-436b-82b0-7a29125c6372`
- new operation：`157347ee-ba5b-4911-bfe9-3f64a47ad162`
- new operation 状态：`awaiting_approval`
- old signal 状态：仍为 `attention_required`
- old operation 状态：仍为 `expired`
- 重复 retry：HTTP 409

重启 API/MCP 后再次查询：

- 库存 signal 行数：2
- successor 行数：1
- successor 仍为 `investigating`
- new operation 仍为 `awaiting_approval`
- API readiness：HTTP 200

这证明谱系、待审批中断点和唯一后继都保存在 PostgreSQL 中，不依赖浏览器内存。

## 5. 浏览器验收

在 `http://localhost:18080/console` 执行真实扫描后观察到：

- 可重试按钮：2 个（设备、任务）
- 已有后继谱系提示：1 个（库存）
- 调查中 signal：1 个（库存 successor）
- “查看关联处置”：1 个
- “查看原处置”：3 个

页面因此能同时表达旧失败历史、可重试异常和新的待审批调查，不再把过期 operation 伪装成仍在运行。

## 6. 诚实边界与下一人工节点

- 本轮 Compose 使用 Mock 模型保证确定性回归；没有调用 Real Kimi，不能把本证据表述为真实模型兼容通过。
- 没有公网可写后端、生产 IAM、限流、备份或高可用证据。
- 未 commit、未 push、未 merge。
- 当前新 operation 停在 `awaiting_approval`。下一步必须由用户以 approver 身份人工检查绑定事实后决定批准或拒绝。
- `OperCerta production release gate: CLOSED`，不启动其他项目。
