# OperCerta 面试讲解

## 30 秒版本

“OperCerta 是我用 FastAPI、LangGraph、FastMCP、PostgreSQL、Redis 和 React 实现的可恢复运营处置 Agent。它跑通库存补货、设备维修、作业异常恢复三条闭环：Agent 取证和评估，人工审批绑定证据快照，批准后重新复核，再幂等写工单。项目用数据库竞态测试、重启恢复、42 条固定评测和 Docker Compose smoke 证明关键可靠性；当前公开的是静态专题，真实模型和公网交互后端仍按发布门禁建设。”

## 3 分钟版本

1. **业务问题：** 运营异常不能让模型直接执行高风险写操作，需要证据、规则、审批和审计。
2. **架构：** React 调 FastAPI；Runner 创建 operation；LangGraph 执行三种类型化图；MCP 读取合成状态/规则并创建工单；PostgreSQL 保存业务事实和 checkpoint；Redis 只缓存初次只读证据；SSE 回放审计。
3. **可靠性：** 非法输入在边界失败；审批用行锁保证一个胜者；审批绑定包含证据/规则/事实/计划哈希；批准后绕过缓存重读 MCP；工单用确定性幂等键和唯一约束保证重放不多写。
4. **恢复：** 业务 operation UUID 同时作为 LangGraph thread ID。启动扫描非终态业务表，再从 checkpoint 继续；业务表是真相，checkpoint 是执行进度。
5. **证据：** 三业务 42 条固定合成评测、Compose 三场景和重启 smoke、缓存 2×2 调用矩阵、完整自动化门禁。自建评测继承原 30 条不可漂移库存基线，并检查实际工具与数据库事实。
6. **边界：** 本地单节点和静态公网展示已验证；真实模型代表性运行、生产 IAM、公开 HTTPS 后端、高可用和 Release Tag 尚未完成。

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
2. 在同一页面做一次只读 query，说明零审批零工单；
3. 做设备或作业创建处置，展示等待审批；
4. 批准并展示唯一工单、审计和绑定；
5. 展示一个自动化测试或 42 条报告，而不是滚动大量终端；
6. 主动说明真实模型/公网后端/生产 IAM 的未完成边界。

## 个人掌握检查

只有能不看稿画链路、解释审批绑定、亲手完成一个业务/规则修改/MCP 故障实验，并回答“为什么不会多写工单”，才把个人熟练度写进简历。文档完成不等于个人已掌握。
