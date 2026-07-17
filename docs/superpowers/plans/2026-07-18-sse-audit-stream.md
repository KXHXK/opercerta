# SSE 审计事件流实施计划

## 目标

为已认证的库存补货 operation 增加只读 SSE 审计流，使前端可按 audit sequence 接收状态演进，并以 `Last-Event-ID` 断线续传；不直接暴露数据库、MCP 或内部异常。

## 边界

- 端点：`GET /api/v1/operations/{operation_id}/events`。
- 权限与 operation 读取一致：`operator`、`approver`、`auditor`、`demo-admin` 可读；匿名或无效令牌在读取事件前被拒绝。
- 事件只包含 `id=sequence`、稳定 `event` 类型和安全 JSON payload；不包含 token、密码、数据库 URL、traceback 或隐藏推理。
- `Last-Event-ID` 为有效正整数时只返回更大的 sequence；格式错误固定返回 `422`。
- 本轮只实现有限快照流（查询时已有事件后结束），不虚构实时 pub/sub；前端实时推送和 Redis 订阅另行实现。

## TDD 顺序

1. 写 API RED：授权读取返回有序 SSE，`Last-Event-ID` 续传，匿名/非法游标拒绝，未知 operation 返回 404。
2. 在仓储增加只读、按 sequence 查询审计事件的最小接口与数据库集成断言。
3. 在 FastAPI 增加 `EventSourceResponse` 路由与严格响应序列化。
4. 运行 focused、完整 pytest、Ruff、格式、mypy、Compose smoke；记录实际结果和未实现的实时订阅边界。

## 发布边界

此功能只证明本地单节点审计事件回放，不证明 SSE 长连接容量、跨实例广播、消息队列或公开部署。发布门禁继续 `CLOSED`。
