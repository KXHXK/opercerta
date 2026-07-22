# OperCerta Agent 核心架构交付证据

## 结论

2026-07-22，Agent 核心 Task 1--9 的本地实现与可重复门禁已完成并提交。三业务通过真实 LangGraph Agent 调查节点、受控 Tool Calling 契约、FastMCP、真实 FastEmbed/pgvector RAG、人工审批、批准后复核、幂等写入、Agent Trace 和 Compose 重启恢复。Task 9 实现提交为 `642d3ba test: gate OperCerta agent trajectories`。2026-07-23 已创建 [Draft PR #8](https://github.com/KXHXK/opercerta/pull/8)，修复提交 `ba53e70` 后，最新基线远程快速门禁 run `29937375023` 全绿。

真实 Kimi Tool Calling 的新端到端代表验证仍为 **failed**，没有回退 Mock，也没有改写成成功。重复工具规划与 provider 异常 operation 原子收口已修复，但最终 Compose 代表调用仍受到外部依赖有界超时影响。因此本证据不打开生产发布门禁：`OperCerta production release gate: CLOSED`。

## 本地新鲜命令与原始结果

### 静态与类型门禁

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

结果：Ruff 通过；`187 files already formatted`；Mypy `Success: no issues found in 76 source files`。

### 完整后端与前端

```bash
OPERCERTA_DATABASE_URL=<ignored-test-dsn> uv run python -m pytest -q
cd web && npm test -- --run && npm run build
```

结果：后端 `566 passed in 179.66s`；前端 17 个测试文件、46 条测试通过，TypeScript/Vite production build 成功。证据只来自合成数据和本地测试数据库。

Task 10 新增文档防漂移测试后，最终本地复验为 `567 passed in 189.36s`；前端仍为 17 文件/46 条并再次构建成功。

2026-07-23 本轮修复的新鲜、无数据库本地回归为 unit `352 passed in 28.05s`、关键 Agent 图集成 `7 passed in 3.54s`、Ruff 通过、`188 files already formatted`、Mypy 76 个源文件通过。完整数据库套件在本地 WSL 自动化中因数据库服务被外部停止而未形成绿色证据；本次提交推送后的 GitHub Actions backend-tests 才是完整数据库回归依据。

### 冻结 Agent 轨迹评测

```bash
OPERCERTA_DATABASE_URL=<ignored-test-dsn> \
  uv run python scripts/run_agent_evaluation.py \
  --suite data/evals/opercerta-agent-v1.json \
  --output-dir tmp/evals
```

原始报告：`tmp/evals/opercerta-agent-v1-mock-report.json`（ignored，不提交）。结果 `9/9`：非法 schema、提示注入、未知工具、对象漂移、RAG 跨场景隔离、批准后事实漂移、并发审批、重复写入、关键重启均通过各自公开 pytest node ID。该数字是冻结合成契约通过数，不是模型准确率、线上成功率或 SLA。

### Compose、真实 RAG 与重启恢复

```bash
OPERCERTA_HF_HUB_OFFLINE=true docker compose --env-file .env.compose up --build -d
uv run python scripts/verify_agent_compose.py
OPERCERTA_HF_HUB_OFFLINE=true docker compose --env-file .env.compose restart api mcp
uv run python scripts/verify_agent_compose.py --recovery-only
docker compose ps
```

整条命令退出码 0。验证包括三业务 query/批准路径、唯一审批/工单数据库断言、真实 FastEmbed 入库、pgvector 场景隔离 citation、Agent Trace 事件类别、API/MCP 重启后等待审批 operation 恢复。最终 API、MCP、PostgreSQL、Redis 均 healthy。

这里的模型模式是 Mock，embedding/RAG、MCP、PostgreSQL 和容器进程是真实实现。Mock 报告不得用于声称真实 Kimi 已通过。

## Real Kimi 代表验证

历史安全报告路径为 `tmp/real-model-agent-v1-report.json`；本轮增加阶段诊断后的安全报告为 `tmp/real-model-agent-v1-diagnostic.json`（两者均 ignored，不提交）。最终代表调用元数据：provider `Moonshot AI`，model `kimi-k2.6`，mode `real`，inventory query，`status=failed`，`failure_stage=query`，`error_type=RepresentativeValidationError`，`operations_attempted=1`，安全失败详情为 `stage=create_operation`、`http_status=503`、`error_code=dependency_unavailable`。报告没有原始模型文本、凭据、token 或费用字段。

低层 probe 得到 `inventory.get_snapshot` 的 native tool call；无 RAG 的完整 LangGraph probe 完成 Goal → inventory/policy → Analysis；开启 RAG 后首次复现 replan 重复已完成工具，修复为“只暴露 missing tools”后，真实图 probe 按 inventory → knowledge → policy 完成。该修复保留 Harness 的重复调用硬拒绝，不以 Prompt 代替代码边界。

完整 Compose 代表验证仍不稳定：一次 query 已得到 HTTP 202、`completed` operation 和 Trace 200，但旧报告在后置证据断言处只保留通用 `AssertionError`；增强安全阶段诊断后的下一次调用在约 30 秒由 API 返回 503。该结果证明失败被安全、有界地收口，但不能证明端到端通过。真实模型失败没有回退 Mock，也没有产生工单。

provider/图异常留下 `received` operation 的缺口已经修复：operation runner 会写入固定 `dependency_unavailable` 终态；若终态写入本身失败，则不记录 provider 正文并保留原始异常。对应测试覆盖失败收口、敏感文本不持久化和二次失败语义。

## Draft PR 与远程 CI

- 分支：`feat/agent-core-implementation`；PR：[Draft PR #8](https://github.com/KXHXK/opercerta/pull/8)。
- 首次 run `29936292055`：repository-safety、python-quality、frontend 通过；backend-tests 因普通 `postgres:18` 不提供迁移要求的 vector extension 而失败。
- 修复：先写 CI 资产 RED，再把 backend service 固定为 `pgvector/pgvector:0.8.2-pg18-trixie`；提交 `ba53e70 fix: use pgvector in backend CI`。
- 最新基线 run [`29937375023`](https://github.com/KXHXK/opercerta/actions/runs/29937375023)：repository-safety、python-quality、backend-tests、frontend 全部通过。
- `compose-smoke` 在 PR 事件按设计跳过；本地 Agent Compose 已有本页前述证据，但新 Agent 核心合并后的 main Compose 证据仍未产生。

## 数据、安全与指标边界

- 业务和 SOP 均来自仓库合成数据，不含旧公司材料。
- `.env.local`、JWT、数据库凭据、API key、prompt 原文、隐藏思维链和 SOP 正文未进入报告或 Git。
- 本轮本地完整数据库测试的失败 traceback 曾展开测试角色凭据；值未进入仓库或本文，但必须轮换 Windows PostgreSQL 角色密码并同步 ignored `.env.local`，轮换前不得打开生产门禁。
- Agent Trace 只保存受限摘要与 citation reference；audit 与 OpenTelemetry 不冒充 Agent Trace。
- 未获得 provider usage，因此不填写 token 和成本；未做生产负载，因此不填写吞吐、延迟 SLA 或可用性。
- 本地单节点 Compose 通过不代表公网、高可用、备份恢复或生产安全通过。

## 仍关闭的门禁

1. 新 Agent 核心的真实 Kimi Tool Calling 完整 Compose 端到端仍未稳定通过；
2. 本次原子收口/replan 修复尚待新一轮 Draft PR Actions 完整数据库回归；
3. 本地测试角色密码需人工轮换并同步 ignored `.env.local`；
4. Draft PR 尚未 review/合并，合并后的 main `compose-smoke` 尚无新鲜证据；
5. 公网可写 HTTPS API、生产 IAM/租户隔离、限流防滥用、秘密托管、备份、高可用、自动部署和 Release Tag 未完成；
6. 用户尚需不依赖 Codex 完成一次人工闭环和口述复盘。

因此只完成 OperCerta 本地 Agent 核心交付，不启动 ForenTrail。
