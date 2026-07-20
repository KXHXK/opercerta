# OperCerta 真实模型代表性验证证据

## 结论与边界

2026-07-20 经用户明确授权，在本地 WSL2 Ubuntu + Docker Compose 发布候选上使用 Moonshot AI `kimi-k2.6` 完成三业务代表性验证。库存、设备、作业各执行一条只读 `query` 和一条批准写入路径，共 6 个 operation；3 条写路径实际经过真实模型解释，随后分别形成唯一的 `replenishment`、`repair`、`task_recovery` 工单。

本证据证明 OpenAI-compatible adapter、三业务确定性规则、人工审批、批准后复核和幂等写入能与该真实模型组合运行。它不证明公网可用性、生产 SLA、模型准确率、容量、高可用或成本水平；生产发布门禁仍为 `CLOSED`。

## 固定验证方法

实现提交：`b517ab8 feat: validate representative real model paths`。

密钥只存在于被 Git 忽略的 `.env.local`。脚本只解析五个白名单变量，不执行该文件、不启用 shell trace、不打印密钥，也不保存原始模型输出：

```bash
./scripts/run_real_model_validation.sh tmp/real-model-validation-report.json all
```

固定契约：

- `query` 只做 MCP 取证和确定性评估，预期模型调用为 0、审批为 0、工单为 0；
- `create_work_order` 由确定性代码决定动作与参数，模型只返回严格的 `summary` 和 `rationale`；
- 每条写路径都必须进入 `awaiting_approval`，批准后直连 MCP 重取事实，再形成 1 条审批和 1 条唯一工单；
- 验证经 Caddy 公共入口访问 API，并对 PostgreSQL 审批/工单数量做断言；
- 成功或失败后均执行 `docker compose down -v --remove-orphans`。

## 实际结果

正式运行退出码为 0，总耗时 83.1 秒；报告摘要为 `6 operations / 3 model paths`。

| 场景 | Query 端到端 ms | 写请求端到端 ms | Summary 字符 | Rationale 字符 | 审批/工单 | 工单类型 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 库存 | 462.833 | 3758.707 | 189 | 294 | 1 / 1 | `replenishment` |
| 设备 | 232.836 | 3707.601 | 141 | 263 | 1 / 1 | `repair` |
| 作业 | 272.862 | 5917.239 | 149 | 372 | 1 / 1 | `task_recovery` |

这里的“写请求端到端”包含 API、MCP、确定性评估、真实模型请求与持久化，不是供应商模型纯推理延迟。样本每场景仅 1 次，不能计算 P50/P95 或推导生产性能。

当前 adapter 不暴露供应商 usage，因此报告明确写入 `token_usage_available=false`、`cost_available=false`；没有根据文本长度虚构或估算 token/费用。模型原文、Prompt、API key 和内部 reasoning 均未进入报告。

## 调试链与设计决策

1. 首次真实请求在模型阶段失败；安全探针确认网络、认证和模型名有效。
2. 请求显式传入 `temperature=0` 时供应商返回 HTTP 400，指出该模型只接受 1。修复为不强制 temperature，交由供应商默认值处理。
3. 不传 temperature 后请求成功，但默认 thinking 模式只返回 reasoning、严格 JSON content 为空。新增可配置的 `OPERCERTA_MODEL_THINKING_MODE=disabled`，代表性验证显式关闭 thinking，从而取得受约束的最终 JSON。
4. 模型服务端超时已放宽到 30 秒，但外层验证客户端仍为 10 秒，形成分层超时倒挂。验证客户端改为 1–120 秒有界配置，本次使用 75 秒。
5. 为 release Compose 增加可选模型变量后，Mock 冒烟因空 URL 在 Pydantic 启动校验前失败。先写 RED 回归，再把三个可选模型空字符串规范化为未设置；Real 模式缺项仍安全失败。修复后完整 429 条测试和 Mock Release Compose 均重新通过。

## 凭据安全事件与处置

调试期间一次本地配置检查命令误把被忽略的 `.env.compose` 数据库连接行回显到工具输出。该值是一次性本地 Compose 数据库凭据，不是 Moonshot API key；模型密钥从未回显。发现后立即同时轮换 `.env.compose` 中的 PostgreSQL 密码和匹配的 `DATABASE_URL`，并仅用布尔一致性结果复核。代码、提交和本文均不保存旧值或新值。

改进措施：以后只输出 `SET/UNSET`、一致性布尔值或白名单安全字段；不再用“替换后再打印整行”的方式检查配置。任何凭据一旦进入对话、日志或终端记录，都按已暴露处理并轮换。

## 验证后的门禁

已完成：三业务本地闭环、真实模型代表性运行、固定评测、缓存矩阵、Mock/Real Compose 验证和中文学习材料。

仍未完成：生产 IAM/SSO、公开交互 HTTPS 后端、限流/防滥用、托管数据库备份恢复、固定提交远程 CI、Release Tag，以及用户亲手完成掌握检查。因此只能说“本地真实模型代表性验证通过”，不能说 OperCerta 已生产上线。
