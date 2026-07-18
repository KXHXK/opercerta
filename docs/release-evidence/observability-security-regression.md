# 可观测性与安全回归：本地验证证据

验证日期：2026-07-18（Asia/Shanghai）

## 范围

- 服务端生成 UUIDv4 `request_id`，忽略客户端传入的 `X-Request-ID`，并在响应头返回服务端值。
- 使用 `ContextVar` 隔离并发请求上下文，在正常返回与异常返回后恢复原上下文。
- Python 标准日志只输出固定 JSON 白名单字段，不输出 Authorization、JWT、密码、请求正文、审批 reason、连接 URL、异常消息或 traceback 正文。
- 每个应用实例使用独立 Prometheus registry；HTTP route、method、status 和 SSE event label 均归一化到固定集合。
- `/metrics` 默认关闭，只能通过 `OPERCERTA_METRICS_ENABLED=true` 显式开启。
- SSE 只对 `Last-Event-ID` 之后实际回放的持久化审计事件计数。

## RED/GREEN 证据

1. FastAPI 补丁升级：版本断言先以 `AssertionError: 0.139.0` 失败；锁定 `0.139.2` 后版本断言通过，同步完整回归为 `325 passed in 75.52s`。
2. 请求上下文：测试先因 `No module named 'opercerta.observability'` 收集失败；最小 `ContextVar` 实现后 `2 passed`。
3. 安全 JSON 日志：测试先因 `No module named 'opercerta.observability.logging'` 收集失败；白名单 formatter 与入口配置实现后 `4 passed`。
4. 低基数指标：测试先因 `No module named 'opercerta.observability.metrics'` 收集失败；独立 registry 与固定标签实现后 `1 passed`。
5. HTTP 中间件：测试先因无法导入 `ObservabilityConfig` 而收集失败；服务端 request_id、稳定 503、默认关闭的 `/metrics` 与安全日志实现后，相关 API 回归 `15 passed`。
6. SSE 计数：测试先观察到事件 2 已回放但指标没有样本；在实际 `yield` 前计数后，SSE/API 回归 `14 passed`。

以上数字均来自本轮实际命令输出，只代表合成测试和本机回归，不解释为生产成功率、性能或 SLA。

## 完整门禁

仓库根目录：

```text
uv run pytest -q
332 passed in 74.58s (0:01:14)

uv run ruff check .
All checks passed!

uv run ruff format --check .
100 files already formatted

uv run mypy src
Success: no issues found in 50 source files
```

Ruff 对 3 个本轮文件执行纯格式化并单独提交后，再次执行完整后端测试：`332 passed in 74.70s (0:01:14)`。两次结果均保留，不把耗时差异解释为性能变化。

`web/` 目录：

```text
npm run test:run
Test Files  9 passed (9)
Tests  15 passed (15)

npm run build
TypeScript 与 Vite 生产构建退出码 0；24 modules transformed。
```

## 安全断言

- 恶意客户端 `X-Request-ID` 不被信任或回显；响应只携带服务端生成值。
- 合成 Authorization、JWT、密码、异常消息和任意用户输入不进入安全 JSON 日志。
- operation_id、原始未知路径和未知事件名不进入指标 label，分别归一化为固定 route 或 `unmatched`、固定 event 或 `other`。
- 并发请求各自读取自己的 request_id；未处理异常返回稳定 503 后，`current_request_id()` 已恢复为 `None`。
- `/metrics` 默认返回 404；显式启用只用于内部或测试环境。

敏感文本扫描首次命中 `src/opercerta/evaluation/executor.py` 的两处 Authorization：一处动态篡改刚签发的演示 token，一处固定字符串 `malformed-wrong-issuer-token`。`git blame` 确认它们来自既有固定契约评测提交 `df5422cc`，用途是构造 tampered/wrong-issuer 攻击输入，不是保存的凭据。保留该文件作为明确例外后，对 README、交接、索引、本证据、当前状态和其余 `src` 的同一扫描退出码为 1、零匹配；没有通过改写合成样本来规避扫描。

## 已知限制

- 未实现 OpenTelemetry、Grafana、Redis 业务依赖、生产 IAM、CI/CD、Caddy、HTTPS 或公开部署。
- 当前指标只存在于单个应用进程内；没有持久化、集中采集、告警或多实例聚合证明。
- 当前 request_id 是请求关联，不是分布式 trace_id。
- 没有性能提升、生产可用性或 SLA 结论。
- `OperCerta release gate: CLOSED`。
