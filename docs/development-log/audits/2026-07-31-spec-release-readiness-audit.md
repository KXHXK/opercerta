# OperCerta 规格一致性与发布就绪审计（2026-07-31）

## 结论

OperCerta 当前实现与“受控单 Agent + 三业务共享可靠性内核”的有效设计主线一致，
没有退化为普通 CRUD 工单系统，也没有偏离为自由聊天或多 Agent 角色讨论。库存补货、
设备维修和作业异常恢复共享同一条生产 LangGraph 生命周期，并真实接入 LLM 决策、
FastMCP 工具、pgvector SOP 检索、人工审批、批准后复核、幂等写入、PostgreSQL 事实、
Redis 只读缓存、Agent Trace 和重启恢复。

当前已经达到“公开源码 + 静态项目页 + 可重复本地单节点完整 Agent MVP”的发布状态，
尚未达到“公网可交互产品”或“企业生产系统”状态。静态 Netlify 页面可以公开访问，但
`/api/*` 返回静态 SPA HTML；真实 FastAPI、MCP、PostgreSQL 和 Redis 只在本地/CI 与
release Compose 中运行。

## 核验依据与优先级

1. 命名基线：`docs/specs/2026-07-14-agent-project-naming-design.md`。
2. 总体基线：`docs/specs/ai-agent-portfolio-overall-design.md`。
3. 组合基线：`docs/specs/2026-07-14-agent-portfolio-design.md`。
4. OperCerta 原始详细设计：`docs/specs/2026-07-14-opercerta-design.md`。
5. 有效修订：三业务发布、Agent 核心架构、异常信号收件箱、信号对账与后继调查、
   单根 LangGraph Agent Loop 与 case 工作台规格。
6. 当前事实：源码、锁文件、迁移、Compose、CI、固定评测、真实模型代表报告和本审计
   当日运行结果。后来的明确修订优先于早期设计中被修订的范围，运行事实不由文档状态
   代替。

## 设计—实现映射

| 设计要求 | 当前实现证据 | 结论 |
| --- | --- | --- |
| 库存、设备、作业三业务 | scenario registry、三类 signal detector、三类策略和工单 payload | 一致 |
| 有限输入而非自由聊天 | React 三业务表单、严格 Pydantic Goal/Intent、对象和动作 allowlist | 一致；这是后续 Agent 规格对早期“自然语言请求”的安全收敛 |
| 单 Agent Plan-and-Execute | `ControlledAgentRootGraph`、Model → Tool Policy → MCP Observation → Model 有界回环 | 一致 |
| LangGraph 唯一生命周期所有者 | production factory 只构造受控根图；同一 thread/checkpoint 覆盖审批、复核、写入和终态 | 一致；历史场景图只保留回归与等价测试 |
| MCP 工具调用 | FastMCP 注册库存、设备、任务、策略、SOP、工单创建和工单查询共 7 个类型化工具 | 一致；原始 5 工具先由三业务修订扩展，再由 Agent/RAG 修订增加知识工具 |
| RAG 与 Memory | FastEmbed、pgvector 512 维向量、HNSW、版本化合成 SOP、citation；checkpoint/业务事实/知识分层 | 一致；RAG 不提供权威数量和权限 |
| 人工审批和批准后复核 | JWT/RBAC、绑定哈希、PostgreSQL 行锁、fresh-fact cache bypass、模型 Verifier、重新审批 | 一致 |
| 幂等与重启恢复 | 唯一幂等键、写后读、PostgreSQL checkpointer、业务表主导 recovery、API/MCP restart smoke | 一致 |
| API 与前端 | FastAPI 安全 envelope、health、operation/signal/case/trace/SSE API；React case 工作台和局部状态 | 本地一致；公网 API 未部署 |
| 数据与基础设施 | PostgreSQL 18/pgvector、8 个 Alembic 迁移、Redis 8.8、Docker Compose、Caddy | 本地和 CI 一致 |
| 可观测性 | request/operation/thread/tool/trace 关联、JSON 日志、OpenTelemetry、Prometheus、Agent Trace/audit 分层 | 代码与测试一致；公开环境没有 collector、dashboard 或告警 |
| 测试与评测 | 667 条后端、19 文件/60 条前端、42/42 三业务契约、9/9 Agent 安全恢复、main Compose | 已有可重复证据；均不是生产 SLA 或独立准确率 |

## 原始设计与当前实现的合理变化

- 原始详细设计只具体化库存和设备，2026-07-20 三业务修订正式补齐作业异常。因此当前
  三业务不是范围膨胀或偏差，而是对总体设计缺口的已批准修复。
- 原始 MCP 清单为 5 个工具；任务工具和 `knowledge.search_sop` 分别由三业务与 Agent
  核心/RAG 规格增加，当前 7 工具与有效设计一致。
- 原始描述允许自然语言请求，后续规格把产品入口收敛为有限表单和受控 Goal。LLM 仍在
  根图内完成语义/规划、工具选择、Observation 后续决策和批准后 Verifier，不需要通过
  无边界聊天框证明 Agent 属性。
- 早期证据文档记录了当时查询路径不调用模型、旧图或尚未发布等历史事实；当前运行事实
  以单根 Agent Loop 证据、`current-state.md` 顶部和最新 main CI 为准。历史记录不能被
  反向解释为当前架构。

## 当日新鲜验证

- GitHub PR #20 已合并为 main `764f4b5`，main Actions run `30614799180` 五项成功：
  repository safety、Python quality、完整 backend、frontend、真实 Compose restart/recovery。
- 本分支 README/CONTRIBUTING/文档索引定向测试：`14 passed`。
- GitHub Markdown API 保留两个同名 `<details>` 分组和默认 `open` 属性，中英文可在同一
  README/CONTRIBUTING 页面互斥展开，不跳转独立语言文件。
- `https://opercerta-kxh.netlify.app/`、`/console` 和 `/api/v1/auth/demo-token` 均返回
  `200 text/html`；最后一项再次证明公网是静态 SPA，不是 API。
- 本机 `opercerta-demo` PostgreSQL、Redis、MCP、API 四容器 healthy；readiness 返回
  database/checkpoint/MCP 全部 ready。
- `docker compose -f compose.release.yaml config --quiet` 通过，说明发布拓扑配置可解析；
  它不等同于公网环境、备份、容量或安全验收。

## 尚存问题与优先级

### P0：公网交互或生产上线前必须完成

- 部署真实 HTTPS FastAPI 后端，并配置与前端完全匹配的 CORS 和公开入口。
- 用生产身份系统替换本地 demo JWT 签发；补齐身份生命周期、最小权限和会话吊销。
- 增加限流、配额、模型费用熔断、防滥用、托管密钥和安全数据重置。
- 使用托管/受维护的 PostgreSQL，完成备份、恢复演练、迁移编排和故障回滚。
- 部署日志/Trace/指标采集、dashboard 和告警；当前只有埋点与本地测试。
- 增加公网端到端、浏览器 CORS、超时、并发和失败恢复验收。

### P1：优质公开仓库建议补齐

- 当前 GitHub community profile 为 42%；缺少明确 `LICENSE`、`SECURITY.md`、
  Code of Conduct、Issue/PR 模板。
- main 分支尚未启用 branch protection；目前依靠人工坚持 PR 全绿后合并。
- 缺少独立 ADR 目录；架构取舍存在于规格和技术手册中，但不利于外部贡献者快速定位。
- 当前真实模型只做少量代表调用，adapter 又没有供应商 usage，不能给出准确率、Token、
  成本或 SLA 结论。

### P2：增强可信度而非阻塞本地 MVP

- 增加独立人工标注的业务质量集和多次真实模型运行，报告失败样本与方差。
- 增加 Playwright 类完整浏览器 E2E、无障碍和 Lighthouse 证据。
- 为容器基础镜像增加 digest/供应链更新策略，为公开部署增加 SBOM 或漏洞扫描。

## 发布与作品使用结论

| 使用方式 | 当前结论 | 允许表述 |
| --- | --- | --- |
| GitHub 开源源码 | 可用 | 可复现、经过 CI 的受控运营 Agent MVP |
| Netlify 静态项目页 | 已上线 | 公开只读项目说明和静态功能展示 |
| 本地/现场完整演示 | 可用 | Docker Compose 单节点三业务完整闭环 |
| 公网交互演示 | 未完成 | 不可称在线可操作 Agent；需要后端部署与安全治理 |
| 企业生产系统 | 未完成 | 不可声称生产高可用、SLA、真实 WMS/CMMS 接入 |

因此，OperCerta 已可作为个人 Agent 项目写入简历并用于本地面试演示，前提是明确写成
“可部署单节点 MVP + 公开静态项目页”，并能亲自解释和操作业务闭环。若希望审阅者无需
本地环境直接操作真实 Agent，则仍需完成 P0 中的公网交互演示子集；若希望称为生产系统，
则必须完成全部 P0 并补充运行期证据。

## 原始完成定义对照

| 完成定义 | 状态 |
| --- | --- |
| 核心业务成功/失败/拒绝终态闭环 | 通过 |
| 状态、工具、权限和异常路径测试 | 通过 |
| 固定评测与可重复性能/缓存报告 | 通过，样本边界已声明 |
| 干净 Docker Compose 启动与重启恢复 | 通过 |
| 在线地址可以完成真实核心业务 | 未通过；当前仅静态页 |
| README、架构、API/部署/限制文档 | 部分通过；内容充分但正式 ADR/安全治理文件缺失 |
| 日志、Trace、Token、成本与关键指标 | 部分通过；Trace/指标具备，供应商 usage/公开观测后端缺失 |
| 无密钥、无旧单位专有内容、无未授权材料 | 仓库安全门禁通过 |
| Release tag 与验收记录 | 通过，现有 Showcase pre-release |
| 可重复演示与学习材料 | 材料通过；个人脱稿掌握仍需本人验收 |

