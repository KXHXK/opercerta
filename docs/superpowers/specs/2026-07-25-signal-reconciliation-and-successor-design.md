# OperCerta Signal 历史对账与后继调查设计

**日期：** 2026-07-25
**状态：** 用户已批准继续实施
**基线：** `feat/agent-core-implementation` at `d49577b`，保留当前异常信号功能的未提交改动
**发布门禁：** `OperCerta production release gate: CLOSED`

## 1. 问题

当前本地持久卷存在两类已确认问题：

1. 终态反馈代码上线前形成的历史行仍显示 `investigating`，但关联 operation 已为 `expired`；
2. 新路径即使正确得到 `attention_required`，页面也只能查看旧处置。同一事实哈希再次扫描会命中原去重行，operator 无法为仍未解决的异常启动后继调查。

不能通过清空 `operation_id` 或覆盖旧 signal 修复，否则会破坏历史绑定、审批失效证据和审计链。

## 2. 目标闭环

```text
terminal operation
  -> startup reconciliation repairs signal projection
  -> attention_required
  -> operator explicitly retries
  -> one successor signal
  -> one successor operation
  -> fresh MCP/RAG investigation
  -> new approval binding
```

## 3. 数据契约

新增迁移 `0008_signal_successor_lineage`：

- `operational_signals.predecessor_signal_id UUID NULL`
- 外键指向 `operational_signals.id`，删除前驱时使用 `RESTRICT`
- `predecessor_signal_id` 唯一，保证同一前驱最多产生一个直接后继

现有扫描 signal 的 `predecessor_signal_id` 为 `NULL`。后继 signal：

- 复制前驱的对象、类型、来源、严重度、原因、事实和事实哈希；
- 使用独立稳定键 `signal:retry:v1:{predecessor_signal_id}`；
- 初始状态为 `open`，operation 尚未绑定；
- 通过现有 signal 行锁事务绑定新的 operation；
- 前驱保持 `attention_required` 和原 operation 绑定，不覆盖历史。

后继再次失败后可以继续形成链，每一层只有一个直接后继。

## 4. 历史对账

`SignalRepository.reconcile_terminal_links()` 以 `operations.status` 为事实来源：

- `completed/rejected -> resolved`
- `aborted/expired/failed -> attention_required`
- 修复 signal 的 `updated_at`，`resolved` 同时设置 `resolved_at`
- 只修复与终态 operation 不一致的 signal
- 重复执行返回零变化，必须幂等

生产 lifespan 在 `runner.recover_all()` 后执行一次对账。operation 的既有终态审计仍是事实依据；对账只修复可派生 signal 投影，不伪造新的业务决定。

## 5. API 与权限

新增：

```text
POST /api/v1/signals/{signal_id}/retry
```

- 仅 `operator`
- 仅允许 `attention_required`
- 原子创建或返回唯一 open 后继 signal，再使用既有原子绑定启动 operation
- 成功返回新的 `OperationAccepted`
- 不存在返回 404；状态不允许或并发已认领返回 409
- 客户端不能修改对象、action、事实或 predecessor

旧 operation 已是终态，旧审批继续由现有状态机拒绝；新 operation 必须生成新的审批绑定。

## 6. 前端

- `attention_required` 且尚无后继时显示“重新调查”
- 点击调用 retry API，不复用旧 operation
- `investigating` 继续显示“查看关联处置”
- 页面说明新处置会重新读取 MCP 事实并生成新的审批绑定
- 不提供清空历史、强制改状态或绕过审批按钮

## 7. TDD 门禁

- 领域：后继去重键稳定、模型严格包含 predecessor；
- 迁移：`0007 -> 0008 -> 0007 -> 0008`；
- Repository：历史三类终态映射、幂等对账、十路后继创建只有一行；
- API：RBAC、404/409、十路 retry 一个 operation、旧 operation/审批不变；
- 前端：attention retry、investigating view、错误与忙碌状态；
- Compose：旧卷启动对账、retry 后新 operation、API/MCP 重启不重复；
- 完整 Pytest、Ruff、format、mypy、前端测试/build 全绿。

## 8. 非目标

- 不接入消息队列、生产调度或真实 WMS/EAM；
- 不自动无限重试；
- 不删除旧 signal、operation、审批或审计；
- 不把本地测试结果解释为生产指标；
- 未通过门禁前不提交、不推送、不合并、不启动 ForenTrail。
