# OperCerta 当前状态

> 更新时间：2026-07-31。本文件只保存当前权威状态；历史过程见 `docs/development-log/daily/` 与 `docs/release-evidence/`。

## 当前结论

OperCerta 的三业务共享 Agent 主线、可靠性内核、前后端、本地 Compose 和自动化证据已经完成。当前版本正式定义为：

> **公开静态展示 + 本地可复现完整 Agent MVP + 3–5 分钟录屏。**

公开站点 <https://opercerta-kxh.netlify.app/> 只承载静态项目展示，不连接可写 API 或数据库。真实 FastAPI、LangGraph、FastMCP、PostgreSQL、Redis 与 React 控制台在本地 Docker Compose 环境运行。当前版本不是公网交互产品，也不是企业生产系统。

## 三类门禁

| 门禁 | 状态 | 判定依据 |
| --- | --- | --- |
| 工程与本地自动化门禁 | `PASSED` | 当前 main `7bb9ecd`；PR #23 合并；main run `30629194460` 五项成功；后端 671、前端 60、三业务 42/42、Agent 9/9、Compose 重启恢复通过 |
| Showcase Release gate | `AWAITING_OWNER_VALIDATION` | 静态站点和本地 MVP 已具备；仍需项目所有者独立完成业务实演、源码讲解、恢复实验和录屏 |
| Product Release gate | `CLOSED` | 未部署公网可写后端、生产身份、限流、防滥用、托管数据库备份、高可用与线上告警 |

`Showcase Release gate: AWAITING_OWNER_VALIDATION`

`Product Release gate: CLOSED`

本分支新增 3 条发布/安全契约后，本地一次性 pgvector 测试库得到 `671 passed in 112.07s`；main backend job 随后复核通过。

## 已实现范围

- 库存不足、设备异常、作业阻塞三类确定性信号发现与 Case 隔离。
- 有限表单输入和类型化 Goal，不提供无边界自由聊天。
- 单一 `ControlledAgentRootGraph`：LLM 规划、工具策略、MCP Observation、有界回环、人工审批中断、恢复与 Verifier。
- FastMCP 七类类型化工具；业务权威事实由 PostgreSQL 提供，SOP 由 pgvector 检索并带 citation。
- 审批绑定、批准后最新事实复核、行级并发控制、幂等键、唯一约束和写后读验证。
- PostgreSQL LangGraph checkpoint、业务表主导恢复、API/MCP 重启恢复。
- Redis 只缓存只读证据，审批后复核绕过缓存。
- FastAPI/JWT/RBAC/Pydantic/SSE、React Case 工作台、Agent Trace 和审计时间线。
- Mock 模型确定性门禁；Moonshot/Kimi K2.6 仅做少量兼容性代表验证，不宣称准确率、成本或 SLA。

## 当前运行与发布证据

- GitHub main：`7bb9ecda8170ed8752049331f5597ea2368d77b1`；PR #23；Actions run `30629194460` 五项全绿。
- 自动化基线：后端 `671 passed`；前端 19 文件/60 条；三业务固定契约 42/42；冻结 Agent 安全恢复 9/9；main Compose smoke 通过。
- main Compose 在干净 GitHub Linux 环境构建 uv `0.11.28` 镜像，验证三业务数据库副作用、API/MCP 重启、恢复和隔离卷清理，关闭了本机 GHCR 拉取超时留下的容器证据缺口。
- 本机 WSL2 Ubuntu 26.04 的 `opercerta-demo` PostgreSQL、Redis、MCP、API 四服务 healthy；readiness 中 database、checkpoint、MCP 均 ready。
- Netlify 为静态站点；`/console` 与 `/api/*` 在公网均是 SPA 静态回退，不是可写后端。
- 旧预发布 `v0.1.0-showcase.1` 指向较早提交，只保留历史；最终 Showcase tag 必须在本轮合并、本人验收和录屏后创建。

## 当前唯一主线

1. 合并本轮双门禁、许可证、工具链和文档防漂移修订，并取得新鲜 main CI/Compose 证据。
2. 项目所有者按 `docs/learning/opercerta-ownership-acceptance.md` 亲自完成环境、完整库存闭环、代码链路、重启/幂等和分层讲解验收。
3. 录制 3–5 分钟演示，保存操作编号、工单编号、Trace/审计和数据库后置事实。
4. 验收通过后创建最终 Showcase tag，并以“公开静态展示 + 本地可复现完整 Agent MVP”对外表述。

ForenTrail 暂不启动。FieldPilot 是 OperCerta 完成后的独立项目，不在本仓库扩展或预先实施。

## 不得误报的边界

- 不把静态 Netlify 页面描述为公网可操作 Agent。
- 不把 demo JWT 描述为生产身份系统。
- 不把固定合成评测描述为生产准确率或真实流量 SLA。
- 不把少量真实模型调用描述为供应商基准测试。
- 不在本人尚未实演和讲清代码前，把个人掌握门禁写成通过。

正式门禁定义见 `docs/superpowers/specs/2026-07-31-showcase-release-gate-amendment-design.md`。
