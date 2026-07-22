# OperCerta Agent 核心架构交付证据

## 结论

2026-07-22，Agent 核心 Task 1--9 的本地实现与可重复门禁已完成并提交。三业务通过真实 LangGraph Agent 调查节点、受控 Tool Calling 契约、FastMCP、真实 FastEmbed/pgvector RAG、人工审批、批准后复核、幂等写入、Agent Trace 和 Compose 重启恢复。Task 9 实现提交为 `642d3ba test: gate OperCerta agent trajectories`。

真实 Kimi Tool Calling 的新端到端代表验证为 **failed**，没有回退 Mock，也没有改写成成功。因此本证据不打开生产发布门禁：`OperCerta production release gate: CLOSED`。

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

安全报告：`tmp/real-model-agent-v1-report.json`（ignored，不提交）。最终代表调用元数据：provider `Moonshot_AI`，model `kimi-k2.6`，mode `real`，inventory query，`status=failed`，`failure_stage=query`，`error_type=AssertionError`，`operations_attempted=1`。报告没有原始模型文本、凭据、token 或费用字段。

低层 probe 曾得到 `inventory.get_snapshot` 的 native tool call，单独结构化 Goal/分析/报告探针也曾成功；但完整 API → LangGraph 调查在工具规划阶段未稳定满足严格契约。检查点停在目标编码之后，API 返回安全 503/验证失败。真实模型失败没有回退 Mock，也没有产生工单。

还观察到 provider/图异常可能留下 `received` operation，随后启动恢复会把它收口为 `recovery_state_conflict`。这说明异常原子收口和 provider 兼容 repair 仍需实现，属于阻塞真实模型发布的 known limitation。

## 数据、安全与指标边界

- 业务和 SOP 均来自仓库合成数据，不含旧公司材料。
- `.env.local`、JWT、数据库凭据、API key、prompt 原文、隐藏思维链和 SOP 正文未进入报告或 Git。
- Agent Trace 只保存受限摘要与 citation reference；audit 与 OpenTelemetry 不冒充 Agent Trace。
- 未获得 provider usage，因此不填写 token 和成本；未做生产负载，因此不填写吞吐、延迟 SLA 或可用性。
- 本地单节点 Compose 通过不代表公网、高可用、备份恢复或生产安全通过。

## 仍关闭的门禁

1. 新 Agent 核心的真实 Kimi Tool Calling 端到端兼容未通过；
2. provider 异常下 operation 原子失败收口仍需补强；
3. 本 feature branch 尚未推送、创建 PR 或取得新鲜 GitHub Actions 全绿；
4. 公网可写 HTTPS API、生产 IAM/租户隔离、限流防滥用、秘密托管、备份、高可用、自动部署和 Release Tag 未完成；
5. 用户尚需不依赖 Codex 完成一次人工闭环和口述复盘。

因此只完成 OperCerta 本地 Agent 核心交付，不启动 ForenTrail。
