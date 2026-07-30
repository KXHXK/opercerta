# OperCerta 面试讲解

## 30 秒版本

“OperCerta 是我用 FastAPI、LangGraph、最小 LangChain、FastMCP、PostgreSQL/pgvector、Redis 和 React 实现的可恢复运营处置 Agent。它跑通库存补货、设备维修、作业异常恢复三条闭环：确定性检测先发现异常，Plan-and-Execute Agent 受控取证，人工审批绑定快照，批准后重新复核，再幂等写工单。最新 main 有 667 条后端测试、19 个前端测试文件/60 条用例、9/9 Agent 冻结评测和真实 Compose 重启证据；Real Kimi 的三业务只读、库存批准写入和无效 provider fail-closed 做过少量代表验证，并发布了 `v0.1.0-showcase.1` 只读静态 Showcase 预发布。公网可写后端仍未上线。”

## 3 分钟版本

1. **业务问题：** 运营异常不能让模型直接执行高风险写操作，需要证据、规则、审批和审计。
2. **六层 Agent 架构：** React/FastAPI 感知有限表单；LLM 编码 Goal；LangGraph 做有界规划；四类 Memory 分别承载状态、checkpoint、业务事实与 pgvector SOP；MCP 执行白名单工具；审批、复核、工单和 Trace 形成反馈循环。
3. **可靠性：** 非法输入在边界失败；审批用行锁保证一个胜者；审批绑定包含证据/规则/事实/计划哈希；批准后绕过缓存重读 MCP；工单用确定性幂等键和唯一约束保证重放不多写。
4. **恢复：** 业务 operation UUID 同时作为 LangGraph thread ID。启动扫描非终态业务表，再从 checkpoint 继续；业务表是真相，checkpoint 是执行进度。
5. **证据：** 原三业务 42 条固定合成评测之外，新增 9 类 Agent 轨迹评测，覆盖非法 schema、提示注入、未知工具、对象漂移、RAG 隔离、审批后漂移、竞态、幂等和重启；Compose 使用真实 FastEmbed/pgvector RAG。
6. **边界：** 本地 Mock 闭环、真实 RAG/数据库/MCP 和少量 Kimi 兼容路径已验证；真实调用样本不足以形成准确率、SLA 或成本结论。`v0.1.0-showcase.1` 是只读静态 Showcase 预发布，不代表生产 IAM、公开 HTTPS 后端、高可用或产品级正式 Release 已完成。

## 10 分钟深挖提纲

### 1. 为什么不是让 LLM 直接调用写工具

模型输出不稳定，也不应成为权限和业务数量的事实源。OperCerta 把确定性评估、审批、复核和幂等写入放在代码/数据库；模型只生成严格 `summary`、`rationale` 解释，失败时真实模式不回退 Mock 后继续写。

### 2. 为什么选 LangGraph

核心需求不是聊天，而是可中断、持久化、重启恢复的长流程。LangGraph 把 `gather → assess → report → interrupt → revalidate → execute → verify` 显式化。三业务共享受控入口和恢复内核，但保留类型化证据/计划。

### 3. checkpoint 为什么不能代替 PostgreSQL 业务表

checkpoint 是图运行状态，适合恢复节点；业务表要支持 API 查询、事务锁、唯一约束、审计序列和长期兼容。恢复协调器以业务表找候选，再以 checkpoint 继续。任何一侧缺失都安全失败，而不是推断已经成功。

### 4. 审批竞态怎么处理

审批 Repository 在事务内锁 operation 行，检查状态、过期和 expected binding，只允许第一次决策写入，并同步追加审计。十个并发请求不是靠 Python 锁，而是 PostgreSQL 原子控制；失败者得到稳定冲突。

### 5. 幂等与 exactly-once

我不会承诺整个分布式链路 exactly-once。LangGraph 节点可能至少一次执行；通过 operation 派生 idempotency key、数据库唯一约束、原子事务与写后读，达到业务副作用 effectively-once。外部系统若不支持幂等，还需要 outbox、去重表或对账补偿。

### 6. Redis 为什么不会破坏审批安全

缓存仅包裹初次/查询取证；miss/error 直读 MCP。批准后的 `revalidate` 持有未缓存 gateway。测试先命中旧缓存，再修改真实 MCP 事实，批准仍得到 snapshot mismatch 且零工单。

### 7. MCP 与 FastMCP 的价值

MCP 固定工具协议和结构化输入输出；FastMCP 帮我实现 server。API 不直接接触合成目录和工单 SQL，而是通过六工具边界。网关有白名单、超时、有限重试和安全异常映射；Host 白名单故障也被真实集成测试覆盖。

### 8. 可观测性与安全

request ID 和 W3C trace context 关联 API/MCP；span 跨 LangGraph、Redis、SQL。默认关闭 OTLP 与 metrics 公网路由；属性 allowlist，关闭自动 exception message/stack，避免 token、Prompt、证据和 SQL 参数进入观测系统。

### 9. 测试策略

先测非法输入、状态恢复、审批竞态、幂等写入，再加业务 happy path。固定评测不只看 pass：每例保存 expected/actual 状态、审批/工单数、审计和 MCP 工具。Compose 从真实进程和数据库再次验证。CI 将后端、前端和 main smoke 分层。

### 10. 三个真实故障故事

- MCP readiness 为 200，但 Compose 服务名 Host 被 DNS rebinding 防护返回 421；用真实 Streamable HTTP 测试定位并添加最小 host 白名单。
- PostgreSQL 18 使用旧 volume 挂载点导致启动保护；保留数据、按官方镜像目录修复，而不是先删 volume。
- 性能矩阵 HTTP 全成功却 MCP 指标为 0；对比源码/镜像/实例发现复用旧镜像，强制 `--build` 后不变量恢复。

还可以讲 WSL 生命周期使 Docker 正常退出、Netlify worktree 部署错产物、失败测试污染共享数据库等案例。

### 11. 为什么是 Plan-and-Execute，而不是开放 ReAct

业务动作只有查询和创建三类受控工单，开放聊天会放大提示注入、对象漂移和越权工具风险。模型先把固定表单编码成 Goal，再提出只读工具计划；ToolPolicy/Harness 校验后执行，确定性规则和人工审批才允许进入写路径。需要重规划时最多一次，不允许无限自治循环。

### 12. 真实 Kimi Tool Calling 兼容问题怎么讲

“Mock 回归全绿后，真实 Kimi 首轮仍安全返回 503。我通过 checkpoint 阶段和安全错误分类定位到三类 provider 边界：LLM 错用了 MCP 的 2 秒 timeout；Kimi K2.6 的强制工具调用在当前 Moonshot 配置下要求关闭 thinking；最终分析和 Verifier 的 structured output 还有波动。我把模型 timeout 独立为 90 秒，在 adapter 配置边界关闭 thinking，并让最终分析/Verifier 使用两个内部原生提交工具。随后三业务只读、库存批准写入和无效 provider 零写入验证全部通过。整个过程没有回退 Mock，也没有把一次成功夸大为生产 SLA。”

这说明 Mock 用于确定性契约回归，Real 用于供应商协议兼容；两类证据都必要但不能互相替代。

## 偏业务岗位的 30 秒讲法

OperCerta 不是把聊天框贴到工单系统上，而是解决仓储异常调查跨系统、证据易过期、审批与执行容易脱节的问题。确定性监控先发现库存、设备和任务异常；单根 LangGraph 让 LLM 在受控 ToolPolicy 下通过 MCP 循环取证，结合 pgvector SOP 给建议，再由确定性规则和人工审批决定是否执行。批准后系统绕过 Redis 重新取证，由 Verifier 和审批 binding 双重校验，最后通过 PostgreSQL 唯一约束幂等写工单，并把 Trace、审计与恢复证据反馈到 React 工作台。

## 偏业务岗位的 3 分钟讲法

先讲业务痛点：传统工单的难点不是表单录入，而是异常事实分散、调查步骤依赖经验、审批等待期间事实变化，以及重试可能重复落单。OperCerta 因此把“可解释调查”交给 LLM，把“能否写入”留给确定性安全内核。

请求经 FastAPI 做身份和严格输入校验后进入唯一根 LangGraph。模型每轮只能在当前场景的只读工具白名单里选择 MCP 工具；Observation 会回到下一轮模型，证据齐全才结束循环。RAG 只提供带版本引用的 SOP，不代替 SQL/MCP 业务事实。Policy 用类型化规则形成 action plan，需要写入时 LangGraph 原生 interrupt 等待人工审批。

恢复后不是直接执行：系统绕过 Redis 重新读取权威事实，LLM Verifier 给 `proceed/abort/escalate` 建议，确定性 binding 再比较事实哈希、规则版本、计划哈希和参数。只有两层都允许，才调用受控写工具；PostgreSQL 行锁解决审批竞态，唯一键和事务保证业务副作用 effectively-once，写后读再确认结果。checkpoint 记图位置，业务表记长期事实，二者共同支持重启恢复。

验证分三层：Mock 冻结轨迹、真实 PostgreSQL/MCP/Compose 的数据库与重启断言、少量真实 Kimi 兼容调用。当前本地闭环完整，但公网可写后端、生产 IAM、限流、备份和高可用没有上线，因此发布门禁仍是 `CLOSED`。

## 高频追问

### PostgreSQL 为什么不用 MySQL

不是说 MySQL 做不到，而是 PostgreSQL 的事务/行锁、JSONB、约束与 LangGraph checkpointer 生态更贴合当前项目。选择依据是可靠性需求和技术组合，而非简单性能口号。

### Docker Compose 和 Kubernetes 的取舍

求职演示阶段是本地单节点，Compose 更短、更可复现。若进入生产多副本，需要外部托管数据库/Redis、迁移 Job、secret manager、负载均衡、滚动发布和 leader/worker 恢复协调，再评估 Kubernetes；当前不虚构高可用。

### GitHub Actions 能省吗

可以换成其他 CI，但不能省掉自动门禁。Actions 不在请求链路里，却是确保每次提交能复现测试和 Compose 的交付架构。

### 自己设计 42 条用例会不会作弊

有自证偏差风险，所以新增用例只能继承原 30 条冻结基线，期望来自批准规格；检查实际 MCP 工具和数据库事实；另用 Compose 重启 smoke 交叉验证。仍然诚实说明这不是第三方验收或真实生产流量。

## 面试现场演示顺序

1. 先讲 30 秒架构和边界；
2. 点击“扫描业务异常”，解释 6 次只读 MCP 与确定性信号规则；
3. 从设备或作业 case 点击“启动 Agent 调查”，展示 Goal、Tool/RAG、Trace 与等待审批；
4. 批准并展示 Verifier、唯一工单、审计和绑定；
5. 展示一个自动化测试或 42 条报告，而不是滚动大量终端；
6. 主动说明三业务只读、库存批准写入和无效 provider fail-closed 只做过本地代表性验证，公网后端/生产 IAM 仍未完成。

## 简历项目表述（通过个人掌握检查后使用）

- 基于 FastAPI、LangGraph、最小 LangChain Tool Calling、FastMCP、PostgreSQL/pgvector、Redis 与 React，实现库存、设备、作业三类异常的可恢复运营处置 Agent；以受控只读取证、人工审批绑定、批准后复核和幂等事务约束高风险写入。
- 建立 42 条固定三业务契约、9/9 冻结 Agent 安全/恢复评测与 GitHub Actions main Compose 门禁；验证 API/MCP 重启恢复和工单业务有效一次，并以 `v0.1.0-showcase.1` 发布只读静态展示。

展示入口：[OperCerta 专题](https://opercerta-kxh.netlify.app)、[GitHub 仓库](https://github.com/KXHXK/opercerta)、[Showcase 预发布](https://github.com/KXHXK/opercerta/releases/tag/v0.1.0-showcase.1)。在完成下方检查前，只陈述已经实现和验证的项目事实，不在简历中使用“精通”、生产级 SLA 或未经测量的准确率、性能和成本数字。

## 个人掌握检查

只有能不看稿画链路、解释审批绑定、亲手完成一个业务/规则修改/MCP 故障实验，并回答“为什么不会多写工单”，才把个人熟练度写进简历。文档完成不等于个人已掌握。
