# OperCerta 可观测性与安全回归基础设计

日期：2026-07-18（Asia/Shanghai）
状态：已确认设计，实施计划已创建
发布门禁：`CLOSED`

## 1. 目标与范围

本阶段只为 OperCerta 已验证的库存补货闭环增加本地、可测试、低基数的可观测基础，并建立防止敏感信息泄漏与请求上下文串线的安全回归。它为后续 CI/CD、Caddy/HTTPS 和公开演示提供排障证据，不把本地指标包装成生产 SLA。

本阶段实现：

- 服务端生成并回传 `request_id`；
- 同一 HTTP 请求内的安全结构化日志关联；
- 可显式启用的 Prometheus `/metrics`；
- API 请求次数、状态码、耗时与 SSE 回放事件计数；
- 恶意请求头、Authorization 泄漏、未知路径、异常响应、低基数标签和并发上下文隔离回归；
- 现有 liveness/readiness 语义的回归保护。

本阶段不实现：

- OpenTelemetry Collector、分布式 Trace、Grafana 或告警系统；
- Redis 缓存、限流或 readiness 依赖；
- 生产 IAM/SSO、多租户、真实模型、设备场景；
- Caddy、HTTPS、CI/CD、云平台账号或公开部署；
- 性能、可用性、成本、SLA 或生产业务效果声明。

## 2. 方案选择

采用“最小可观测基线”：Python 标准库 `logging`、FastAPI middleware 与官方 `prometheus-client`。未采用完整 OpenTelemetry，因为当前只有单 Worker API 与独立 MCP 服务，先增加 Collector、Exporter 和跨服务 trace 会扩大 Compose 与部署故障面。未采用部署优先，因为没有稳定埋点时，Prometheus/Caddy 只能证明容器启动，不能支持业务排障。

## 3. 依赖核验与升级边界

2026-07-18 通过官方 PyPI JSON 元数据核验：

- `prometheus-client==0.25.0`：仓库锁定版本与当前官方版本一致，不升级；
- `fastapi==0.139.0`：当前官方版本为 `0.139.2`。

实施计划必须先用独立 TDD/门禁任务把 FastAPI 更新到 `0.139.2`，重新锁定依赖并运行完整后端回归。若补丁升级破坏既有契约，立即恢复 `0.139.0` 并记录证据；不得在可观测性实现中顺手修复无关行为。

## 4. 请求关联契约

API middleware 为每次请求生成 UUIDv4 格式的 `request_id`。客户端传入的 `X-Request-ID` 一律不作为可信关联标识，也不回显；响应始终包含服务端生成的 `X-Request-ID`。

请求开始时把 `request_id` 写入 `ContextVar`，请求结束或异常后必须在 `finally` 中恢复 token。并发请求不得读取到彼此的关联值。业务层只在已经拥有可信 `operation_id` 时记录该对象引用；不从任意路径或请求正文直接构造日志字段。

本阶段不生成或传播 W3C `traceparent`，也不虚构 `trace_id`、`thread_id` 或 `tool_call_id`。这些字段只有在后续真实 Trace/MCP 关联实现后才能进入证据。

## 5. 安全结构化日志

日志事件使用 Python `logging`，由项目 formatter 输出单行 JSON。允许字段固定为：

- `timestamp`、`level`、`service`、`event`；
- `request_id`；
- 可选的 `operation_id`、`route`、`method`、`status_code`、`duration_ms`、稳定 `error_code`。

禁止记录：

- `Authorization`、JWT、Cookie、密码、数据库/MCP URL；
- 请求或响应完整正文、审批 reason、模型输入输出、证据正文；
- traceback 正文、隐藏思维链或任意环境变量集合；
- 未经白名单约束的自定义 `extra` 字段。

异常日志只记录稳定事件名、状态码与安全错误码。开发者仍可通过测试失败栈定位代码，但运行时结构化日志不得展开凭据或请求载荷。

## 6. Prometheus 指标契约

每个应用实例使用独立 `CollectorRegistry`，由应用 factory 注入，避免测试重复创建应用时污染默认全局 registry。

第一阶段指标固定为：

- `opercerta_http_requests_total{method,route,status_code}`；
- `opercerta_http_request_duration_seconds{method,route}`；
- `opercerta_audit_events_replayed_total{event_type}`。

`route` 必须使用 FastAPI 路由模板；未匹配路径统一为 `unmatched`。`event_type` 只允许既有审计事件白名单，未知值归入 `other`。禁止把 `request_id`、`operation_id`、用户主体、SKU、异常消息或原始路径作为 label。

`/metrics` 由显式配置控制，默认关闭。测试或容器内网环境明确启用后返回 Prometheus 文本格式；关闭时不得暴露指标内容。后续公开部署必须由 Caddy 阻止公网访问，本阶段不提前配置 Caddy。

## 7. 健康与错误边界

保留现有 liveness/readiness 行为，不把尚未被业务使用的 Redis加入 readiness。可观测 middleware 不得改变现有安全错误 envelope、状态码、SSE 内容类型或 RBAC 判定。

无论路由正常返回、抛出已知领域错误、发生未处理异常或客户端请求未知路径，都必须：

- 返回服务端生成的 `X-Request-ID`；
- 记录一次请求完成事件；
- 增加一次对应 HTTP 计数；
- 在异常后清理请求上下文。

## 8. 测试与证据

严格按 TDD 从以下失败用例开始：

1. 恶意 `X-Request-ID` 不被信任或回显；
2. 日志不包含 Authorization/token/审批正文；
3. 并发请求的 `request_id` 不串线，完成后 ContextVar 恢复；
4. 404、已知 API 错误和未处理异常仍产生响应关联与低基数指标；
5. `/metrics` 默认关闭，显式启用后格式正确；
6. 原始 operation ID、SKU 和未知路径不出现在 label 名称或值中；
7. SSE 回放只按白名单事件类型计数；
8. 既有 325 条后端测试、Ruff、format、mypy 与前端 15 条测试继续通过。

证据必须记录命令、实际通过数、运行环境、失败诊断与已知限制。不得从合成测试推导生产性能或成功率。

## 9. 文件与组件边界

- `src/opercerta/observability/context.py`：请求上下文与生成/清理契约；
- `src/opercerta/observability/logging.py`：安全字段白名单与 JSON formatter；
- `src/opercerta/observability/metrics.py`：应用级 registry、指标对象和 label 归一化；
- `src/opercerta/api/app.py`：middleware、可选 `/metrics` 与既有路由埋点；
- `tests/unit/observability/`：上下文、日志和低基数单元测试；
- `tests/integration/api/test_observability_api.py`：HTTP、异常、并发、SSE 与指标集成测试。

各模块只负责一个边界；业务领域模型、数据库 Schema、LangGraph checkpoint 和审批/幂等事务语义保持不变。

## 10. 完成条件

只有在依赖补丁门禁、全部新增 RED/GREEN、完整前后端回归、静态检查和中文证据均通过后，才可声明“可观测性与安全回归基础完成本地验证”。即便通过，本项目仍未完成生产身份、CI/CD、Caddy/HTTPS 和公开部署，发布门禁继续为 `CLOSED`，不得启动其他项目。
