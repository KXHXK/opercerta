# OperCerta 实施交接

> 更新时间：2026-08-12。先读 `DOCUMENT_INDEX.md` 的核心阅读表，再读本文件和 `docs/development-log/current-state.md`。

## 当前交接结论

OperCerta 的三业务、Agent 主线、真实模型固定评测和本地运行能力已经通过 PR #26 合入 main `cde3dcd8597645597b0da1cb73e1c2056644cd80`。对应 [main run 31519846029](https://github.com/KXHXK/opercerta/actions/runs/31519846029) 的仓库安全、Python 质量、后端测试、前端测试/构建和 `compose-smoke` 五项全部通过；Compose 在干净 GitHub Linux runner 上完成镜像构建、三业务 Agent 轨迹与数据库副作用、API/MCP 重启、恢复验证和资源清理。工程、本地自动化与远程 CI 门禁均为 `PASSED`。

本版本发布定义已经正式修订为：

> **公开静态展示 + 本地可复现完整 Agent MVP + 录屏。**

`Showcase Release gate: AWAITING_OWNER_VALIDATION`

`Product Release gate: CLOSED`

公开站点是 Netlify 静态专题；本地 Docker Compose 才运行真实 React 控制台、FastAPI、LangGraph、LLM adapter、FastMCP、PostgreSQL/pgvector 与 Redis。不得把当前版本描述为公网交互产品或企业生产系统。

## 已完成的工程范围

- 库存不足、设备异常、作业阻塞三业务闭环。
- 单根 LangGraph Agent Loop、LLM 有界规划、MCP 工具调用、RAG SOP、审批中断与恢复。
- 最新事实复核、审批竞态控制、幂等工单、数据库后置断言与重启恢复。
- FastAPI/JWT/RBAC/SSE、React Case 工作台、Agent Trace、审计与指标埋点。
- 固定评测、仓库安全、Python 质量、前端和 Compose main-only 门禁。
- 公开静态页面、可回滚的历史 Showcase 预发布和完整开发/学习资料。

## 本轮收口修改

- 修复 clean-runner Docker build：保持运行依赖 `--frozen`，但不再假设构建后端已经存在于 uv cache。
- 升级前端锁文件中的受影响传递依赖，并在 CI/贡献指南加入 `npm audit --audit-level=high`。
- 新增 `SECURITY.md`，明确安全报告入口和非生产边界。
- 统一当前实现为“有界 ReAct 风格 Tool Loop”，不再误报为严格 Plan-and-Execute。
- 同步 682 条后端、当前收口分支 63 条前端、42/42、9/9 Agent、9/9 Kimi 真实模型固定路径等已验证数字及其样本边界。
- 补充完整 Agent Harness 技术说明和 2026-08-10 规格/发布审计。

## 下一执行顺序

1. 由项目所有者亲自执行 `docs/learning/opercerta-ownership-acceptance.md`；必须记录 `operation_id`、`work_order_id`、Trace、审计序列和数据库事实，**不得由 Codex 自动代签**。
2. 完成 3–5 分钟录屏与口述复盘。
3. 人工证据通过后，把 Showcase 门禁改为 `PASSED`，创建最终 tag 并记录回滚提交。

## 本地运行入口

```bash
cd /mnt/d/CODEX/agent-portfolio/opercerta
docker compose up --build -d --wait
curl http://127.0.0.1:8080/health/ready

cd web
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173/console>。公开站点为 <https://opercerta-kxh.netlify.app/>，仅作静态展示。

## 自动化门禁

```bash
uv sync --frozen --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run python scripts/run_opercerta_evaluation.py
uv run python scripts/run_agent_evaluation.py

cd web
npm ci
npm audit --audit-level=high
npm run test:run
npm run build
```

Compose 的三业务数据库副作用和重启恢复由 CI 的 main-only `compose-smoke` 与仓库验证脚本证明。不得用“配置可解析”代替真实启动/恢复证据。

## 未关闭范围

公网 FastAPI、生产 IAM、限流与防滥用、托管密钥、数据库备份/恢复演练、高可用、线上观测后端与告警均未实现，因此 Product Release gate 必须保持 `CLOSED`。这些不是本轮 Showcase 的阻塞项，但若未来改为公网交互产品，必须重新开规格和产品门禁。

ForenTrail 暂不启动；FieldPilot 等 OperCerta 完成并由本人掌握后再作为独立项目推进。

## 新任务恢复提示

> 工作目录是 `D:\CODEX\agent-portfolio\opercerta`。先完整读取 `README.md`、`IMPLEMENTATION_HANDOFF.md`、`docs/development-log/current-state.md`、`DOCUMENT_INDEX.md` 核心阅读表、四份 `docs/specs/` 设计文件，以及 2026-07-31 Showcase 门禁修订规格、实施计划和本人验收表。只实施 OperCerta 收口；公开站点是静态展示，完整 Agent MVP 在本地 Compose 复现，Product Release gate 保持关闭。完成自动化门禁后必须等待项目所有者本人实演、讲解和录屏，不得代签掌握验收，也不启动 ForenTrail。
