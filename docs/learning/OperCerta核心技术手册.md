# OperCerta 核心技术手册

## 1. 项目解决什么问题

OperCerta 把“发现运营异常”到“生成可审计工单”做成受控 Agent 后端。三条合成业务是：

- 库存补货：库存低于规则阈值 → 人工批准 → 补货工单；
- 设备维修：设备离线或严重告警 → 人工批准 → 维修工单；
- 作业异常恢复：作业阻塞或超时 → 人工批准 → 恢复工单。

Agent 可以收集证据、执行确定性规则、生成解释和编排步骤，但不能自行绕过审批、修改规则或直接写数据库。所有展示数据均为仓库内公开合成数据。

## 2. 一次请求如何穿过系统

```text
React 页面
  → FastAPI：认证、严格输入、统一错误
  → OperationRunner：创建业务 operation
  → LangGraph：按场景执行取证、评估、报告、审批中断、复核、写入、验证
  → MCP Gateway：只调用六个白名单工具
  → FastMCP Server：校验工具参数并访问合成目录/工单仓储
  → PostgreSQL：operation、证据、审批、工单、审计和 checkpoint
  → Redis：只缓存初次/查询阶段的只读证据
  → SSE：把已持久化审计事件回放给页面
```

OpenTelemetry 用同一 trace 关联 API、LangGraph node、MCP、Redis 和 PostgreSQL；span 只记录 allowlist 属性，不保存 JWT、Prompt、证据正文、SQL 参数或异常堆栈。

## 3. 各技术栈为什么存在

### React 与 ReAct 不是一回事

React 是本项目的浏览器 UI library，负责组件、状态和调用 API。ReAct（Reason + Act）是让模型交替推理和调用工具的 Agent 模式。OperCerta 前端使用 React，但写操作不采用开放式 ReAct 自由决策；可靠性关键路径由类型化 LangGraph 和确定性规则控制。

### FastAPI

FastAPI 是 HTTP 边界：Pydantic 严格校验请求，JWT/RBAC 决定 operator、approver、auditor 能做什么，lifespan 打开和释放数据库/checkpointer，health endpoint 区分进程存活与依赖就绪。API 从 JWT `sub` 取得审批人，拒绝客户端伪造 actor。

### LangGraph

LangGraph 表达可暂停、可恢复的状态机。首次执行在 `awaiting_approval` 中断；批准后从 checkpoint 恢复，但先重新读取真实 MCP 事实并比较审批绑定。节点可以重放，所以副作用必须由数据库幂等约束保护。

### MCP 与 FastMCP

MCP（Model Context Protocol）是工具发现和调用协议；FastMCP 是 Python 侧快速定义 MCP server/tool 的框架。类比：HTTP 是协议，FastAPI 是实现 HTTP 服务的框架。OperCerta 只允许六个固定工具：三种状态读取、规则读取、工单创建、工单读取。

### PostgreSQL

PostgreSQL 是业务真相。选择它是因为事务、行级锁、唯一约束、JSONB、成熟的并发语义和 LangGraph PostgreSQL checkpointer 都适合审批竞态与幂等写入。审批用 `SELECT ... FOR UPDATE` 形成一个原子胜者；工单用 operation/idempotency 唯一约束保证重放不会多写。

### Redis

Redis 只是可删除的读优化，不是事实源。缓存失败会旁路到 MCP；批准后的复核刻意绕过缓存，以免等待期间的旧证据触发错误工单。本机矩阵证明缓存命中改变 MCP 调用次数，但小样本延迟不是生产 SLA。

### Docker 与 Docker Compose

Docker 构建和运行单个隔离镜像；Docker Compose 声明 PostgreSQL、Redis、bootstrap、MCP、API、Caddy 之间的网络、依赖、健康检查和 volume。开发 Compose 只把 API 绑定到本机；release Compose 只有 Caddy 暴露 80/443，内部服务无宿主端口。

### GitHub Actions

GitHub Actions 不是业务运行时架构，而是交付/质量架构。它在 PR/main 上复跑锁文件、静态检查、后端、前端和 Compose smoke，防止“只在开发者电脑能运行”。可以省去平台本身，但不能省去等价的自动化门禁。

## 4. 两类状态为什么都要有

LangGraph checkpoint 回答“图执行到哪个节点、恢复时带什么状态”；PostgreSQL 业务表回答“用户看到的 operation、审批、工单和审计事实是什么”。checkpoint 不能替代业务数据库：它不是稳定查询模型，也不能独立承担审批唯一性、工单唯一性和审计序列约束。

启动恢复时，RecoveryCoordinator 先扫描非终态业务 operation，再用相同 UUID 作为 LangGraph `thread_id` 恢复。业务表与 checkpoint 不一致时安全失败，不猜测成功。

## 5. 审批绑定与复核

审批不是一个孤立布尔值。绑定快照包含场景、主体证据 ID、规则证据 ID、规则版本、事实哈希、计划哈希和类型化参数。批准提交必须带回这份 expected binding。事务内只能有一个审批胜者；图恢复后直连 MCP 重读事实，任何关键变化都返回 `approval_snapshot_mismatch` 且不写工单。

## 6. 幂等和 exactly-once 的正确说法

分布式系统通常无法轻易承诺端到端 exactly-once。OperCerta 提供的是“节点至少可能重放，但业务副作用 effectively-once”：确定性 idempotency key、数据库唯一约束、原子事务、写后读验证共同保证一个 operation 最终只有一张有效工单。面试时不要把它夸大成所有网络和外部系统都 exactly-once。

## 7. 三业务共用与隔离

共享的是 API、Runner、审批仓储、恢复协调、审计、幂等工单和受控图入口；隔离的是每个场景的证据模型、规则、评估、计划、审批参数和工单 payload。这样避免复制可靠性内核，又不把所有业务塞进无类型字典。

## 8. 失败时系统如何安全

- 非法输入：FastAPI/Pydantic 返回固定 422，不创建 operation。
- MCP 不可用：dependency 失败，错误响应不泄露连接串或 traceback。
- Redis 不可用：只读缓存退化为 MCP 直读，不改变审批安全。
- 模型失败：真实模式不回退 Mock 后继续写；模型也无权决定动作参数。
- 重复审批：数据库返回 409，只有一个审批记录。
- 重启：从业务表和 checkpoint 恢复；终态不重复写。
- 事实变化：批准后复核失败，零工单。

## 9. 当前诚实边界

三业务、固定评测、WSL2 Compose、React 控制台、Redis、OpenTelemetry 适配器、CI 和 Moonshot AI `kimi-k2.6` 三业务代表性运行已有本地证据。模型只生成严格解释字段，动作、参数、审批和写入仍由确定性代码与数据库控制。公开交互 HTTPS 后端、生产 IAM/SSO、限流/防滥用、高可用和 Release Tag 尚未完成。静态 Netlify 页面不是公开业务后端。

真实模型兼容要逐层验证：OpenAI-compatible 不保证 temperature、thinking 扩展和响应字段完全相同。本项目不强制 temperature；代表性 K2.6 验证显式关闭 thinking 以取得严格 JSON content。验证只记录安全元数据和端到端耗时，不保存原始输出；当前 adapter 不暴露 usage，所以不能声称 token 或费用数字。

建议按“读代码入口 → 预测测试 → 手动运行 → 制造单变量故障 → 用自己的话讲解”的顺序掌握，而不是只复制命令。
