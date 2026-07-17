# OperCerta 实施问题与面试复盘案例集

**用途：** 将真实实施过程中的问题、诊断、修复和验证证据沉淀为可复盘材料。它不替代发布证据，也不把本地验证描述为生产效果。

## 使用方式

每个案例按以下顺序讲解：**问题 → 约束 → 诊断证据 → 最小修复 → 验证 → 仍有限制**。面试时优先说自己实际看到的错误、运行过的命令和代码/测试边界，避免把“曾经研究过”说成“已经上线”。

## 1. 并发审批与幂等写入不是同一个问题

- **问题：** 多个审批人可能同时批准同一 operation；崩溃重试也可能重复创建工单。
- **根因：** 审批决定和工单写入若只依赖 API 层判断，就会被并发请求或节点重放绕过。
- **修复：** PostgreSQL 事务与唯一约束保证每个 operation 最多一条审批；工单使用稳定幂等键和 canonical JSON/hash，同键同参安全重放、同键异参冲突。
- **验证：** 十路审批竞态和十路工单并发分别多轮独立进程复验；每轮断言一个决定、一行工单和对应审计，而非只断言 HTTP 成功。
- **限制：** 这保证业务效果有效一次，不承诺 LangGraph 节点 exactly-once。
- **面试表达：** “我把并发控制放进数据库真相层，而不是依赖前端按钮禁用；节点可以重放，但唯一键让工单业务效果最多一次。”

## 2. Checkpoint 不能替代业务数据库

- **问题：** 进程可能在审批落库与工作流恢复之间崩溃，单靠内存状态或 checkpoint 无法稳定回答“是否已批准、是否已创建工单”。
- **根因：** LangGraph checkpoint 是编排快照，不是审批、审计和工单的业务真相；两类持久化也不是一个分布式原子事务。
- **修复：** 将 operation、approval、work_order、audit_event 保存在 PostgreSQL 业务表，checkpoint 放入独立 `langgraph` schema；RecoveryCoordinator 以业务状态和图快照共同决定恢复动作。
- **验证：** 覆盖首次 checkpoint 前、等待审批、审批落库后、工单落库后四个 A/B 重启点；关闭第一组资源、创建第二组资源后继续断言数据库事实。
- **限制：** 只验证单节点、单 Worker 的恢复，不证明多 Worker 抢占或跨区域容灾。
- **面试表达：** “我不把框架内部快照当作业务数据库；恢复时允许节点至少执行一次，但让数据库保证业务写入有效一次。”

## 3. Windows 独立服务与测试事件循环不一致

- **问题：** Pytest 的 PostgreSQL 异步用例通过，但 FastAPI 作为独立 Uvicorn 进程启动时，Psycopg async 在 lifespan 阶段失败。
- **根因：** Windows 上 Uvicorn 的 loop factory 会选择 ProactorEventLoop，而 Psycopg async 不兼容该循环；测试 fixture 的循环创建路径不同。
- **修复：** 先以最小启动探针验证，再显式使用 Uvicorn 支持的 Selector loop factory；不修改领域逻辑或替换数据库驱动。
- **验证：** 独立 FastMCP 服务、FastAPI 服务与客户端三进程真实传输闭环通过；后续 WSL2 Linux Compose 也完成运行验证。
- **限制：** Windows 修复不等于生产部署策略；Linux 容器有独立的运行时证据。
- **面试表达：** “我先沿 traceback 定位到事件循环创建边界，对照 Uvicorn 与 Psycopg 的运行约束，再做单变量启动验证，而不是盲目修改业务代码。”

## 4. 密码一旦进入 traceback，代码修复还不够

- **问题：** 一次数据库连接失败的 traceback 曾包含测试角色密码。
- **根因：** 带密码的完整 DSN 被异常格式化输出；即使仓库未提交该值，也不能再把旧凭据视为安全。
- **修复：** 轮换数据库角色密码；代码改为无密码 DSN 加临时 `PGPASSWORD`，并使用 SecretStr/安全错误映射，避免在响应、日志和 Git 中保存凭据。
- **验证：** 轮换后以不回显方式连接，相关 checkpointer 与完整回归重新通过；Git 跟踪文件未包含新值。
- **限制：** 这降低应用层泄露风险，不能替代终端、日志平台和主机权限治理。
- **面试表达：** “我把事故分成‘旧密码已经可能泄露’和‘未来错误仍可能泄露’两部分处理：前者靠轮换，后者靠连接与错误边界重构。”

## 5. Docker 构建暴露了打包元数据与容器上下文差异

- **问题：** `docker compose build --pull` 首次失败，Hatchling 报告 `Readme file does not exist`。
- **根因：** Dockerfile 在 `uv sync --frozen --no-dev` 前仅复制了 `pyproject.toml` 与锁文件；editable 包构建还需要 `README.md` 和 `src/`。
- **修复：** 先写容器资产 RED 测试，再把 README 与源码移动到锁定同步之前复制。
- **验证：** 容器资产测试通过，最终应用镜像在 WSL2 中构建成功。
- **限制：** 当前为可复现本地镜像构建，不是已推送和签名的生产镜像供应链。
- **面试表达：** “锁文件只能固定依赖版本，不能自动保证构建上下文包含 Python 打包后端需要的项目元数据。”

## 6. PostgreSQL 18 镜像的数据目录升级保护

- **问题：** `postgres:18` 容器刚启动即退出，提示旧挂载点可能造成跨主版本数据目录误用。
- **根因：** Compose 把 named volume 挂载在旧的 `/var/lib/postgresql/data`，而 PostgreSQL 18 镜像改为在 `/var/lib/postgresql` 下使用版本化目录。
- **修复：** 先新增失败测试固定 PostgreSQL 18 的目标挂载点，再将 Compose volume 改为 `/var/lib/postgresql`；不删除已有 named volume。
- **验证：** PostgreSQL healthcheck 通过，bootstrap、MCP、API 随后均启动并通过业务 smoke。
- **限制：** 这是当前官方镜像行为的适配；未来跨大版本升级仍须按实际升级手册和备份演练执行。
- **面试表达：** “容器启动失败不是先删 volume 重来；我先读镜像错误信息，确认是升级保护，再用最小配置修复并保留数据。”

## 7. MCP 健康正常不代表内部业务调用可用

- **问题：** MCP `/health/ready` 为 200，但 API 创建 operation 后得到 `dependency_unavailable`。
- **根因：** FastMCP 的 DNS rebinding 防护拒绝 Compose 服务名 `Host: mcp:8001`，业务 `/mcp` 请求返回 421；healthcheck 的 loopback Host 未覆盖这个路径。
- **修复：** 增加真实 Streamable HTTP 会话 RED 测试，以 `mcp:8001` 列出工具；为当前监听地址、loopback 与 `mcp[:8001]` 增加受限 allowed-hosts 白名单，而非关闭防护或允许任意 Host。
- **验证：** MCP 集成回归通过；最终 Compose smoke 证明创建、审批、工单与审计终态均成功。
- **限制：** 白名单应随部署域名和服务拓扑变更复核。
- **面试表达：** “readiness 证明依赖在线，不等于业务协议路径正确；我把服务发现 Host 作为集成契约的一部分测试。”

## 8. Docker 可用性与镜像供应链是两个独立边界

- **问题：** Docker Engine 已安装并 active，但 Docker Hub 和 Docker 厂商 APT 源在当前网络超时或被重置。
- **根因：** Windows 与 WSL2 对 Docker 站点的网络路径受限；这不是 Docker CLI、证书或 Compose 文件错误。
- **修复：** 比较 DNS、Ubuntu 官方 HTTPS 与 Docker HTTPS 探针；用户确认后改用 Ubuntu 官方签名 Docker 包，并只配置三个实测可达的第三方 registry mirror。
- **验证：** `hello-world` 拉取运行，之后 Python、uv、PostgreSQL 与 OperCerta 镜像成功拉取、构建和运行；镜像来源例外与 digest 已归档。
- **限制：** 公共 mirror 是供应链风险；正式发布需使用可审查、稳定、可替换的镜像策略。
- **面试表达：** “我区分了运行时安装成功和镜像供应链可用两个门禁，用对照网络探针定位问题，不把网络问题错误归因给 Docker 配置。”

## 9. 当前未完成范围也应能诚实说明

- **已完成：** 库存补货后端、可靠性内核、Docker Compose 单节点验证。
- **未完成：** 设备场景、JWT/RBAC、SSE、React、真实模型、Redis、固定评测、安全回归、可观测性、CI/CD 和公开部署。
- **面试表达：** “我优先证明了高风险写操作的可靠性内核，完整产品能力仍按发布门禁分阶段推进；不会把本地后端证据说成生产上线。”

## 相关证据

- `docs/release-evidence/approval-atomicity.md`
- `docs/release-evidence/work-order-idempotency.md`
- `docs/release-evidence/langgraph-restart-recovery.md`
- `docs/release-evidence/inventory-replenishment-vertical-slice.md`
- `docs/release-evidence/docker-linux-runtime.md`
