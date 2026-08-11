# OperCerta 当前状态

> 更新时间：2026-08-10。本文件只保存当前权威状态；历史过程见 `docs/development-log/daily/` 与 `docs/release-evidence/`。

## 当前结论

OperCerta 的三业务共享 Agent 主线、可靠性内核、前后端、本地 Compose 和自动化证据已经完成。当前版本正式定义为：

> **公开静态展示 + 本地可复现完整 Agent MVP + 3–5 分钟录屏。**

公开站点 <https://opercerta-kxh.netlify.app/> 只承载静态项目展示，不连接可写 API 或数据库。真实 FastAPI、LangGraph、FastMCP、PostgreSQL、Redis 与 React 控制台在本地 Docker Compose 环境运行。当前版本不是公网交互产品，也不是企业生产系统。

## 当前门禁

| 门禁 | 状态 | 判定依据 |
| --- | --- | --- |
| 工程与本地自动化门禁 | `PASSED` | 收口分支锁文件、Ruff/format/mypy、682 条后端、42/42、9/9、63 条前端、0 high audit、clean Docker build 与 Compose 三业务/重启恢复均通过 |
| 远程 CI 门禁 | `PR_CHECKS_PASSED_MAIN_PENDING` | Draft PR #26 初始 run `31479724666` 四项通过；Compose 按 PR 规则跳过，等待批准合并和新 main run |
| Showcase Release gate | `AWAITING_OWNER_VALIDATION` | 静态站点和本地 MVP 已具备；仍需项目所有者独立完成业务实演、源码讲解、恢复实验和录屏 |
| Product Release gate | `CLOSED` | 未部署公网可写后端、生产身份、限流、防滥用、托管数据库备份、高可用与线上告警 |

`Showcase Release gate: AWAITING_OWNER_VALIDATION`

`Product Release gate: CLOSED`

PR #25 已把真实模型质量评测合入 main。main run `30744845403` 的后端、前端、Python 与仓库安全 job 通过，但 Compose 构建失败，因此不能继续写成“五项全绿”。失败点是 Dockerfile 第二次 `uv sync --offline` 无法在全新缓存中取得 `hatchling`，不是业务、Agent 或数据库断言失败。

## 已实现范围

- 库存不足、设备异常、作业阻塞三类确定性信号发现与 Case 隔离。
- 有限表单输入和类型化 Goal，不提供无边界自由聊天。
- 单一 `ControlledAgentRootGraph`：LLM 规划、工具策略、MCP Observation、有界回环、人工审批中断、恢复与 Verifier。
- FastMCP 七类类型化工具；业务权威事实由 PostgreSQL 提供，SOP 由 pgvector 检索并带 citation。
- 审批绑定、批准后最新事实复核、行级并发控制、幂等键、唯一约束和写后读验证。
- PostgreSQL LangGraph checkpoint、业务表主导恢复、API/MCP 重启恢复。
- Redis 只缓存只读证据，审批后复核绕过缓存。
- FastAPI/JWT/RBAC/Pydantic/SSE、React Case 工作台、Agent Trace 和审计时间线。
- Mock 模型承担确定性回归门禁；Moonshot/Kimi K2.6 冻结真实模型质量评测 9/9：三业务各覆盖正常查询、提示注入和审批写入；提示注入 3/3，未授权调用、审批绕过和重复工单均为 0。该固定本地小样本不代表生产准确率、成本或 SLA。

## 当前运行与发布证据

- GitHub main：`c4257ac10dec470bbb9ca1076c4cfacfb21a80de`；PR #25；Actions run `30744845403` 四项成功、`compose-smoke` 失败。
- 收口 Draft PR：[PR #26](https://github.com/KXHXK/opercerta/pull/26)；初始 head `63692be`；PR run `31479724666` 的 repository-safety、python-quality、backend-tests、frontend 全部成功，compose-smoke 按事件规则跳过。
- 已合并自动化基线：后端 `682 passed`；前端 19 文件/62 条；三业务固定契约 42/42；冻结 Agent 安全恢复 9/9。最近一次成功 main Compose 证据属于 `4c696d2`，不能替代 `c4257ac` 的失败结果。
- 收口分支本地新鲜证据：后端 421 单元 + 261 集成 = 682；前端 19 文件/63 条；依赖审计 0；clean Docker build 成功；隔离 Compose 完成三业务数据库副作用、API/MCP 重启、recovery-only 和资源清理。
- 真实模型质量小样本：9/9；Goal、工具 precision/recall、证据完整率、citation 可解析率与数据库副作用匹配率均为 100%；端到端 P50/P95 为 19.722/31.333 秒。该结果不是生产准确率或 SLA。
- 最近一次成功的历史 main Compose 在 `4c696d2` 验证了三业务数据库副作用与恢复；当前 main `c4257ac` 的 clean build 失败事实已单列，不能混写。
- 本轮 WSL2 Ubuntu 26.04 隔离 Compose 的 PostgreSQL、Redis、MCP、API 四服务均达到 healthy，验证完成后已删除容器、网络和测试卷，不保留污染状态。
- Netlify 为静态站点；`/console` 与 `/api/*` 在公网均是 SPA 静态回退，不是可写后端。
- 旧预发布 `v0.1.0-showcase.1` 指向较早提交，只保留历史；最终 Showcase tag 必须在本轮合并、本人验收和录屏后创建。

## 当前唯一主线

1. 项目所有者复核 Draft PR #26 后批准转为 Ready 并合并，取得新的 main 五项全绿证据，把远程 CI 门禁改为 `PASSED`。
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
