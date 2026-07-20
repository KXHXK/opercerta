# Redis、OpenTelemetry 与 Real model adapter 阶段证据

核验日期：2026-07-20（Asia/Shanghai）

## 已验证

- Redis 失败安全旁路、JSON/TTL、有界低基数指标和重复初次读取命中。
- 缓存只进入初次/查询证据路径；批准恢复后直接 MCP 复核，事实变化以 `approval_snapshot_mismatch` 终止且零工单。
- API、LangGraph 节点、MCP 读写、Redis 和 SQLAlchemy span 使用明确属性 allowlist；API→MCP 注入/提取 W3C trace context。
- SQL 参数、JWT、模型 key、完整消息、Prompt、证据正文、异常 message/stacktrace 和原始模型响应不进入 span 或日志；异常只记录类型与 ERROR 状态。
- OpenAI-compatible adapter 只接受 `summary` 与 `rationale`，拒绝权威字段，固定超时并最多尝试两次；真实模式失败不回退 Mock 执行写动作。
- OpenTelemetry 三项依赖锁定为 `1.44.0`；Redis 官方镜像固定为 `redis:8.8.0-trixie`，Compose 未公开 Redis 端口。

## 本轮命令事实

- 聚焦缓存、模型、追踪、API 配置与容器契约：`27 passed`。
- 提交前安全审查修复后的最终完整后端：`409 passed in 101.15s`。
- `uv lock --check`：锁文件一致。
- Ruff lint：通过；Ruff format：131 个文件格式正确；mypy：62 个源文件无问题。

上述完整测试是在异常 span 与指标旁路修复后重新执行的新鲜结果。

## 尚未验证

- 尚未使用真实模型 API key，不存在真实 provider/model、Token、费用、延迟或成功率结果。
- 尚未拉取并运行本次新增的 Redis 8.8 镜像，三业务 Compose 与重启恢复属于 Task 7。
- 尚未部署 OTLP Collector/Grafana，也没有公开 HTTPS 动态后端。

因此本证据不打开生产发布门禁，也不支持任何性能提升、生产 SLA 或真实模型效果声明。
