# SSE 审计事件回放证据

**日期：** 2026-07-18  
**范围：** `GET /api/v1/operations/{operation_id}/events` 的本地持久化审计回放。

- 已认证的 operator、approver、auditor、demo-admin 可读取事件；匿名请求返回 401。
- 事件以审计 sequence 作为 SSE `id`；`Last-Event-ID` 仅回放更大的 sequence；非法游标返回 422。
- focused API：11 passed；全量 pytest：325 passed；Ruff、格式、mypy 均通过。

限制：当前实现是单次数据库快照回放，在已有事件输出后结束；不宣称实时 pub/sub、跨实例广播、SSE 连接容量或公开部署能力。发布门禁保持 `CLOSED`。
