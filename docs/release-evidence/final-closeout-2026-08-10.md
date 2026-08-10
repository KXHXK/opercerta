# OperCerta 最终收口验证证据（2026-08-10）

## 验证对象

- 基线：`origin/main` `c4257ac10dec470bbb9ca1076c4cfacfb21a80de`。
- 分支：`release/final-closeout-20260810`。
- 环境：Windows 10 + WSL2 Ubuntu 26.04 + Docker 29.1.3；源代码测试使用 uv 0.11.28 / Python 3.12，前端使用 Node.js 24。
- 数据：隔离的临时 PostgreSQL/pgvector 与合成业务数据；未使用客户或原单位数据。

## 上游 CI 事实

main Actions run [`30744845403`](https://github.com/KXHXK/opercerta/actions/runs/30744845403) 的 `repository-safety`、`python-quality`、`backend-tests` 和 `frontend` 成功；`compose-smoke` 在镜像构建时失败。失败日志为第二次 `uv sync --frozen --no-dev --offline` 无法在 clean runner cache 中解析 `hatchling>=1.27,<2`。

本分支先增加容器资产断言并得到 RED，再移除第二次项目安装的错误 `--offline` 假设。运行依赖继续由 `uv.lock` 与 `--frozen` 约束。

## 本地验证结果

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| uv 锁文件 | `uv lock --check` | 通过 |
| Ruff | `uv run ruff check .` | 通过 |
| 格式 | `uv run ruff format --check .` | 220 个文件通过 |
| mypy | `uv run mypy src` | 86 个源文件通过 |
| 后端单元测试 | `uv run pytest -q tests/unit` | 421 条通过 |
| 后端集成测试 | `uv run pytest -q tests/integration` | 261 条通过，239.50 秒 |
| 后端合计 | 单元 + 集成 | 682 条通过 |
| 三业务固定契约 | `uv run python scripts/run_opercerta_evaluation.py` | 42/42 通过（运行器的 pytest 包装为 1 条通过） |
| Agent 安全恢复评测 | `uv run python scripts/run_agent_evaluation.py` | 9/9 通过 |
| 前端依赖审计 | `npm audit --audit-level=high` | 0 个漏洞 |
| 前端测试 | `npm run test:run` | 19 文件/63 条通过 |
| 前端构建 | `npm run build` | 通过；JS `index-XIL8-04O.js`，CSS `index-BKDs2e3h.css` |
| 文档索引 | `uv run python scripts/verify_document_index.py` | 128 份当前 Markdown 完整登记 |
| 仓库安全 | `uv run python scripts/verify_repository_safety.py` | 通过 |
| Docker clean build | `docker build --progress=plain` | 通过；原失败的项目安装层成功取得构建后端并完成 wheel 构建 |
| Compose 完整验证 | `COMPOSE_PROJECT_NAME=opercerta-final-closeout python3 scripts/verify_agent_compose.py` | 三业务轨迹、citation、审批和 PostgreSQL 副作用通过 |
| Compose 重启恢复 | restart API/MCP 后执行 `--recovery-only` | 通过；四个长期服务均 healthy |
| 隔离资源清理 | `docker compose down -v --remove-orphans` | 测试容器、网络与 volume 删除完成 |

## 供应链修复

- `web/package-lock.json` 将 nanoid、postcss、undici 升级到修复版本，未改变顶层依赖范围。
- GitHub Actions frontend job 在 `npm ci` 后执行 `npm audit --audit-level=high`，高风险告警将失败关闭。
- 新增 `SECURITY.md`，CONTRIBUTING 改为引用真实安全报告流程。

## 判定

- 工程与本地自动化门禁：`PASSED`。
- 远程 main CI 门禁：`PENDING_PR`。
- Showcase Release gate：`AWAITING_OWNER_VALIDATION`。
- Product Release gate：`CLOSED`。

本轮没有重新调用真实 Kimi；9/9 真实模型指标来自已合入 main 的 2026-08-02 脱敏报告。本轮复验的是 Mock 冻结契约、数据库/MCP/Compose 和构建/供应链门禁，不能把两次证据混成一次运行。

## 尚不能写成通过的事项

- 收口分支尚未 push/PR，尚无新的远程 clean runner Compose 证据。
- 项目所有者掌握验收与 3–5 分钟录屏尚未完成。
- 最终 Showcase tag 尚未创建。
- Product Release gate 保持 `CLOSED`；本证据不覆盖公网 IAM、Ingress、限流、备份、高可用或 SLA。

所有本地命令均已取得终态；上游 main 的失败历史继续保留，不能用本地结果冒充远程 clean runner 已修复。
