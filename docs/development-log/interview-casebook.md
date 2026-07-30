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

- **已完成：** 库存补货、设备维修、作业恢复三业务后端、可靠性内核、Docker Compose/Caddy 单节点发布候选、本地 JWT/RBAC、SSE 审计回放、React 控制台、42 条三业务固定合成评测、Redis 只读缓存、OpenTelemetry 适配、安全回归与 GitHub Actions 分层 CI。
- **未完成：** 真实模型代表性验证、公开交互 HTTPS 后端、生产 IAM/SSO、限流/防滥用、备份恢复、高可用、当前远程发布门禁与 Release Tag。
- **面试表达：** “我优先证明了高风险写操作的可靠性内核，完整产品能力仍按发布门禁分阶段推进；不会把本地后端证据说成生产上线。”

## 10. 源码正确但旧镜像仍会让接口 404

- **问题：** 浏览器能读取 operation 详情，但审计 SSE 回放失败；API 日志显示 `/events` 返回 404。
- **根因：** 工作区源码已有审计路由，正在运行的容器镜像却创建于实现之前；`docker compose up -d` 只复用了旧镜像。
- **修复：** 比对容器创建时间、源码路由和访问日志，确认边界后重新构建 `api`、`mcp`、`bootstrap` 镜像，而不是修改已经正确的路由代码。
- **验证：** 同一 operation 的事件地址返回 `200 OK` 与 `text/event-stream`，浏览器回放序列 1–10。
- **限制：** 本地 Compose 默认不等同于镜像仓库供应链；正式部署仍需不可变 tag/digest 和部署 commit 关联。
- **面试表达：** “我先证明失败发生在镜像版本边界，而不是看到 404 就改路由；源码、镜像和运行实例必须形成同一版本链。”

## 11. WSL 结束会让无 Live Restore 的 Docker 一起退出

- **问题：** Compose 服务健康后不久全部在同一秒退出，且退出码为 0。
- **根因：** PostgreSQL 日志记录管理员快速关机；无持久 WSL 会话时实例结束，Docker daemon 随之停止，`Live Restore` 又为 false。
- **修复：** 为本次验证启动隐藏、可追踪的临时 WSL 保活进程，保持 Linux 实例和 Docker daemon 存活；不写系统启动项，验证后清理。
- **验证：** Windows 前台命令结束后 `/health/ready` 仍返回 database、checkpoint、mcp 全部 ready，浏览器随后完成审批、唯一工单和审计闭环。
- **限制：** 临时保活只适合本地演示；长期开发应通过常驻终端、Docker Desktop/系统服务策略或明确的 WSL 生命周期管理解决。
- **面试表达：** “四个服务同秒正常退出更像编排器或运行时生命周期问题，而不是四个应用同时崩溃；我用数据库 shutdown 日志确认了这一点。”

## 12. 部署成功不等于部署了正确产物

- **问题：** Netlify CLI 首次生产部署退出码为 0，但线上仍显示旧控制台，证据图 URL 也返回 HTML。
- **根因：** 功能分支位于嵌套 Git worktree；Netlify 将 repository root 回退到主 checkout，使相对发布目录解析为主工作区的旧 `web/dist`。
- **修复：** 先用 `netlify build --dry --debug` 证明目录解析链，再显式部署功能工作树内已经测试的 `web/dist`，没有为了部署问题修改业务代码。
- **验证：** 比较本地与线上 JS/CSS 指纹；验证两张图片均为 `image/png`；验证 `/api/*` 仍是 HTML 静态回退；记录最终 deploy id 与日志 URL。
- **限制：** 当前是人工 CLI 静态部署，不是 Git 自动部署；公开后端、身份和数据写入仍然关闭。
- **面试表达：** “我没有把 CLI 的 success 当成上线证据，而是用资源指纹和 Content-Type 验证实际产物；最终定位为 worktree 基目录解析错误。”

## 13. 平台显示已部署不等于公网可访问

- **问题：** 作品集在 Sites 平台已有部署地址，但外部访问持续返回 Cloudflare HTTP 403，无法作为简历入口。
- **根因：** 已观察到的事实只能证明平台生成过部署，不能证明当前公网边缘链路允许匿名访问；在没有平台侧可操作证据前，不猜测更具体的账户或策略根因。
- **修复：** 保留原 Sites 源作品集作为唯一人工维护源，新增独立、纯静态的 Netlify 导出镜像；先用失败闭环验证 HTML、资源、输出目录和 SSR 响应，再执行 preview → production 两阶段发布。
- **验证：** 原 Sites URL 同轮仍返回 403；新 Netlify URL 返回 `200 text/html; charset=UTF-8`，标题、7 个本地资源、OperCerta 精确 URL 和外链安全属性均通过，浏览器确认第 04 张 OperCerta 卡片正常渲染。
- **限制：** 镜像目前采用人工 CLI 发布，不是 Git 自动部署；它只解决作品集公开访问，不开放 OperCerta 后端、身份或写入。
- **面试表达：** “我把部署状态、公开可达性和内容正确性拆成三个门禁。平台部署成功但公网 403 时，我没有伪造上线结论，而是建立可测试的静态导出链路，用 preview、production、HTTP 与浏览器证据逐层验证。”

## 14. 测试全绿也不能替代规格逐条核对

- **问题：** 三业务创建、审批和工单测试均已通过，但批准规格要求的三对象只读 `query` 仍被 API 返回 422。
- **根因：** 实现和早期测试沿用了库存切片“只允许 create_work_order”的安全边界；新增场景时更新了对象分派，却没有逐条复核动作矩阵。
- **修复：** 先加入三对象 API 失败测试，再逐层补齐 API 白名单、场景注册表、查询专用评估落库、`query_completed` 封闭结果和三张图的无审批分支；React 同页增加真实查询按钮。
- **验证：** 三对象 query 均 completed，持久化两份证据与 assessment，approval binding、approval 和 work order 全为 null；完整后端 392 条与前端 25 条测试通过。
- **面试表达：** “测试只能证明测试写到的东西。我在提交前按规格动作矩阵复核，发现 query 缺口，并用失败测试把它从文档要求变成可执行契约。”

## 15. 失败测试也会污染共享集成环境

- **问题：** 查询诊断完成后，全量恢复测试意外捞到 6 条旧 operation，断言从空列表变为多条恢复记录。
- **根因：** 测试 harness 只有收到 202 后才登记 operation ID 供 finally 清理；故障阶段 API 返回 503，数据库行已经创建但未进入清理列表。
- **修复：** 先确认目标是专用 `opercerta_test`，查看 operation 请求和状态后精确清理测试数据。随后把 harness 改为通过 `TrackingOperationRepository` 在数据库创建成功时立即登记 ID，不再依赖 HTTP 202 响应。
- **验证：** API/恢复聚焦 17 条通过，最终完整后端 414 passed；没有清理开发或演示数据库。
- **面试表达：** “集成测试本身有状态生命周期。业务逻辑修好后，我没有把恢复测试失败误判为新回归，而是从数据库证据定位到失败用例的清理盲区。”

## 16. 缓存优化不能进入审批后的安全判定

- **问题：** Redis 能降低重复只读取证延迟，但缓存证据可能在人工审批等待期间过期；若批准后仍读缓存，就可能依据旧事实写工单。
- **设计：** 缓存 wrapper 只传给初次/查询取证节点；三张图的 `revalidate`、写入和写后读始终使用直接 MCP gateway。Redis 异常只变成 miss，PostgreSQL/MCP 仍是业务真相。
- **验证：** 单元测试证明同一初始读取命中缓存后只调用一次 delegate；集成测试让初始 gateway 固定返回旧快照、随后修改真实 MCP 事实，批准恢复仍得到 `approval_snapshot_mismatch` 且零工单。
- **限制：** Redis 8.8 Compose 与 2×2 本机矩阵已经验证，但每格仅 5 次；只能证明命中和 MCP 调用变化，不能写成生产性能或 SLA。
- **面试表达：** “我把 Redis 定义为可删除的读优化，不是事实源。缓存只服务初次观察，审批后的安全复核有独立直连路径，并用两个不同 gateway 的测试证明这个边界不是口头约定。”

## 17. Trace 的价值在关联，不在记录更多敏感内容

- **问题：** 只给 API 加 span 不能解释 LangGraph、MCP 和数据库的耗时；但把请求正文、SQL、Prompt 或 token 放进 span 又会制造泄密面。
- **提交前发现：** OpenTelemetry 默认 `record_exception=True`；即使业务属性有 allowlist，未处理异常的 message 和 stacktrace 仍会以 event 自动进入 span。这是第一版测试未覆盖的旁路泄露面。
- **设计：** 使用属性 allowlist，仅记录组件、操作、场景、节点和真实关联 ID；关闭自动异常正文/堆栈记录，只保存异常类型与 ERROR 状态。API→MCP 传播 W3C context，MCP 服务提取后建立子 trace。SQL span 不记录 SQL 与参数，模型 adapter 不记录 key 或原始响应。
- **验证：** in-memory exporter 断言 JWT、API key、消息、证据正文和带秘密的异常 message/stack 均不进入 span；SQL 测试传入秘密参数后，span 只保留 `component=postgresql` 与 `operation=execute`。
- **限制：** OTLP exporter 默认关闭，当前 Compose 没有 Collector/Grafana；因此只能声称埋点与导出适配器可用，不能声称已建成线上观测平台。
- **面试表达：** “可观测性不是把所有内容都写日志。我先定义安全字段集合，再关联 API、图节点、MCP、Redis 和 SQL；这样能定位阶段耗时，同时不把业务证据和凭据复制到观测系统。”

## 18. 测量脚本也必须运行当前代码镜像

- **问题：** 2×2 矩阵请求全部成功、Redis hit 正常，但 MCP 调用指标始终为 0。
- **根因：** Compose 复用了 Task 6 镜像；缓存指标已在旧镜像中，Task 7 新增的 MCP 指标却没有。源码、测试和运行镜像不是同一版本。
- **修复：** 编排脚本强制 `docker compose up --build -d`，以资产测试固定，并重跑全部 12 格。
- **验证：** 禁用缓存时每场景 10 次 MCP；启用时 2 次 MCP + 8 次 hit；60/60 个业务终态 completed。
- **面试表达：** “性能脚本本身也是交付代码。我不因 HTTP 成功就接受矛盾指标，而是沿源码—镜像—实例版本链定位到旧镜像，并强制可重建复现。”

## 19. 评测用例由开发者设计时如何避免自证循环

- **风险：** 同一人写实现和用例，可能只测容易通过的 happy path，形成“自己出题自己答”。
- **控制：** 新 12 条不能修改原 30 条，只能版本化继承；期望来自已批准规格的动作矩阵和安全不变量；报告记录实际工具、数据库可观察事实和失败摘要；Compose 再从进程与数据库边界独立复核。
- **验证：** 套件覆盖批准、拒绝、未知对象、正常无动作、查询零写入、策略失败和重启恢复，而非只统计通过数。
- **限制：** 这仍不是第三方验收或生产流量；后续可让面试官现场修改合成事实或新增黑盒用例。
- **面试表达：** “我承认自建评测存在偏差，所以把旧套件设为不可漂移基线，并用工具调用、数据库断言和独立 Compose smoke 交叉取证；通过率不是唯一证据。”

## 20. 时间派生展示字段不能直接进入审批哈希

- **问题：** 设备状态、规则和分类都没有变化，但从创建到批准跨过一秒后仍返回 `approval_snapshot_mismatch`。
- **根因：** `decision_facts_hash` 包含 `heartbeat_age_seconds`；它是由当前时钟派生的展示值，不是源事实，因此每秒变化。
- **修复：** 先写同一证据在 60 秒和 61 秒评估时“展示年龄变化但哈希稳定”的失败测试；哈希改为设备 source version、last heartbeat、severity、state、告警允许性、是否 stale 和最终分类等稳定决策输入。
- **验证：** 聚焦维护/设备工作流/重启/API 回归通过，随后完整后端 422 条通过；release Compose 三业务重新通过。
- **限制：** 跨过 stale 阈值会改变分类和哈希，这是应有行为；测试只排除分类不变时的时钟噪声。
- **面试表达：** “审批哈希应绑定可审计的决策事实，而不是每次读取都变化的派生展示值。我保留年龄用于 UI，但把稳定事实和分类结果作为绑定内容。”

## 21. 反向代理配置正确不等于路由优先级正确

- **问题：** API 容器内部 `/health/ready` 返回 200，但经 Caddy 访问得到 React HTML。
- **根因：** Caddy 会按指令顺序适配配置；裸 `reverse_proxy` 与 SPA catch-all 组合后，实际执行顺序不符合文本视觉顺序。
- **修复：** 使用互斥 `handle @api` 与静态 `handle` 明确路由，资产测试要求 API matcher、反向代理和 SPA fallback 同时存在，且没有 metrics/MCP/数据库路由。
- **验证：** `caddy fmt`、`caddy validate` 和一键 release smoke 通过；三业务只经 Caddy 完成，`/metrics` 返回静态 HTML 而非内部指标。
- **限制：** 本地使用 HTTP 地址；自动 HTTPS 仍需要真实域名、DNS 和入站端口验证。
- **面试表达：** “我没有因为 API 内部健康就归因给业务服务，而是比较代理前后响应类型，定位到路由层，并用配置结构测试防止 catch-all 再吞掉 API。”

## 22. 故障窗口的代理响应不一定是 JSON

- **问题：** API/MCP 重启期间 Caddy 返回空正文 502，smoke 脚本先因 `json.loads` 失败退出，掩盖了真正的依赖启动状态。
- **根因：** 诊断客户端假设所有成功和错误响应都符合应用 JSON envelope；代理在上游尚未恢复时不受这个应用契约约束。
- **修复：** 先为 JSON、空正文和代理文本写解码测试；通用 request 返回可空 body，readiness 轮询容忍暂态非 JSON，业务结果仍严格要求 JSON 与目标终态。
- **验证：** 解码聚焦测试和一键重启恢复 smoke 通过；空代理错误不再让诊断器自身崩溃。
- **限制：** 这不是吞掉业务错误；达到 deadline 或业务断言不符仍失败，并输出 Caddy/API 诊断。
- **面试表达：** “健康轮询面对的是代理和应用两个协议边界。我只放宽启动窗口的解析，不放宽业务完成条件，让诊断工具在故障时继续提供证据。”

## 23. OpenAI-compatible 不等于所有参数完全兼容

- **问题：** `/models`、认证和模型名均有效，但首条 Kimi K2.6 chat 请求仍返回 HTTP 400。
- **根因：** adapter 强制发送 `temperature=0`，而该模型只接受自己的固定温度语义；随后不传温度虽返回 200，默认 thinking 模式又只产生 reasoning，严格 JSON content 为空。
- **修复：** adapter 不再强制 temperature；新增默认关闭影响的 thinking 配置，真实代表性验证显式发送 `thinking={"type":"disabled"}`，仍只接受 `summary`/`rationale` 两字段 JSON。
- **验证：** 库存、设备、作业各一条真实模型写路径通过，三种唯一工单落库；Mock 默认路径重新执行 release Compose 通过。
- **限制：** 这证明与当前供应商/模型的代表性兼容，不代表所有 OpenAI-compatible 服务都支持同一扩展字段；供应商适配仍需契约测试。
- **面试表达：** “OpenAI-compatible 主要复用 endpoint 和消息形状，不代表采样参数、thinking 扩展和返回位置完全一致。我用最小安全探针逐层确认网络、认证、参数和响应形状，再把差异变成显式配置。”

## 24. 分层超时必须从外向内递增

- **问题：** 模型服务端允许等待 30 秒，但验证客户端 10 秒先断开，表现为外层超时而不是可解释的模型结果。
- **根因：** 只调整了 adapter timeout，没有检查浏览器/验证器、反向代理和服务端的完整 deadline 链。
- **修复：** 把验证客户端 timeout 做成 1–120 秒有界配置，本次使用 75 秒包住模型 30 秒预算；重试仍最多两次，避免无界等待。
- **验证：** 三业务 6 个代表 operation 在 83.1 秒总运行内完成；单条写请求端到端约 3.7–5.9 秒。
- **限制：** 单样本端到端数字不等于供应商纯模型延迟，也不是生产 SLA。
- **面试表达：** “外层 deadline 必须覆盖内层最坏预算，否则内层的错误处理永远没有机会返回。我同时限制上下界，避免配置错误把验证变成无限等待。”

## 25. 配置误回显后的正确动作是轮换，不是删除日志

- **问题：** 一次本地检查命令误回显 `.env.compose` 的一次性数据库连接行。
- **处置：** 立即把该凭据视为已暴露，同步轮换 PostgreSQL 密码和匹配 URL；只用布尔一致性结果复验。Moonshot API key 未回显，代码、Git 和证据文档均不保存任何旧值或新值。
- **改进：** 配置诊断只输出 `SET/UNSET`、长度或白名单安全字段；不打印“脱敏后的整行”，因为脱敏规则自身也可能失效。
- **面试表达：** “秘密一旦进入可持久化输出，就不能靠撤回或删除证明安全。我的动作是缩小影响面、立即轮换、验证一致性，再把诊断方式改成只输出状态。”

## 26. 开发机配置不能整体继承到测试进程

- **问题：** 新功能分支首次后端基线出现一条失败，表现为“真实模型配置缺项应失败关闭”的测试没有按预期抛错。
- **根因：** 测试启动命令把本地 `.env.local` 的所有变量注入当前进程，使本应验证缺项的用例意外获得完整真实模型配置；失败来自测试 harness 的环境污染，不是生产实现回归。
- **修复：** 停止整体导入，只以不回显方式加载 PostgreSQL 集成测试必需的 `OPERCERTA_DATABASE_URL`；模型相关环境保持未设置。真实模型验证继续使用独立白名单脚本。
- **验证：** 最小环境基线全绿；新增静态展示契约后正式后端门禁为 430/430，真实模型失败关闭测试仍有效。
- **限制：** 本机测试数据库 URL 仍属于秘密配置，必须位于 ignored 文件且不得出现在日志；CI 应继续显式声明每个变量，而非继承开发 shell。
- **面试表达：** “环境变量也是测试输入。我遇到的失败不是业务回归，而是 harness 过度授权；我把测试环境改成最小能力，只注入数据库连接，让真实模型缺项测试重新验证正确边界。”

## 相关证据

- `docs/release-evidence/approval-atomicity.md`
- `docs/release-evidence/work-order-idempotency.md`
- `docs/release-evidence/langgraph-restart-recovery.md`
- `docs/release-evidence/inventory-replenishment-vertical-slice.md`
- `docs/release-evidence/docker-linux-runtime.md`
- `docs/release-evidence/public-portfolio-showcase.md`
- `docs/release-evidence/portfolio-netlify-static-mirror.md`
- `docs/release-evidence/three-business-evaluation-compose.md`
- `docs/release-evidence/three-business-release.md`
- `docs/release-evidence/performance-cache-matrix.md`
- `docs/release-evidence/real-model-representative-validation.md`
- `docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md`
- `docs/release-evidence/agent-pgvector-rag.md`

## 案例：固定 embedding 模型直连失败与可审计降级

- **现象：** `BAAI/bge-small-zh-v1.5` 首次初始化访问官方 Hugging Face，约 150 秒后报 `Network is unreachable`；没有生成向量，也没有写知识表。
- **根因：** WSL 主机直连官方域名同样超时，问题在外部网络路径，不在 Docker DNS、FastEmbed 合同或 pgvector。
- **处理：** 先探测可达端点，只在 ignored 本地 `.env.compose` 临时配置 `HF_ENDPOINT`；产品 Compose 不硬编码第三方镜像。缓存完成后以 `local_files_only=True` 验证 512 维有限向量，并运行三场景真实检索。
- **证据边界：** 记录固定模型、维度、文档版本、chunk 和实际 cosine 分数；不把小规模合成语料包装成准确率。
- **面试表达：** “我把下载、向量生成、数据库写入分层验证。网络失败时系统没有写半成品；缓存成功后我用离线模式证明模型和检索链路独立可用。”

## 案例：Codex 自动化 WSL 会话停止 Docker service

- **现象：** 新镜像构建和服务健康成功，但完整 smoke 到数据库计数断言时，Compose 返回 `service "postgres" is not running`。
- **诊断：** Docker journal 显示 service 被正常 `terminated`，容器均退出 0；轮询 Docker、持续 `docker events` 和前台 Compose 三种 keepalive 都在约 43--49 秒复现。
- **决策：** 连续三次同根因后停止 workaround，不改产品代码掩盖环境问题；保留 535+4 测试、新镜像健康和失败日志，把完整 restart smoke 作为 Task 9 稳定交互式 WSL 门禁。
- **面试表达：** “我区分产品失败与执行宿主失败。三次最小假设都未改变结果后停止试错，避免为了绿色结果篡改业务验证脚本。”

## 27. 迁移测试不能依赖数据库碰巧已经升级

- **问题：** Task 6 在已有开发卷上通过，但新建空 pgvector 卷时迁移往返测试第一步失败，结果为 1 failed/74 passed。
- **根因：** 测试只声明原始 `database_url` fixture，却直接执行从 head 降到 `0004_approval_cycles`；旧开发卷碰巧已迁移到 head，掩盖了隐式前置条件。
- **修复：** 不改生产迁移，让测试显式依赖负责升级到 head 的 `migrated_database_url`；随后验证 downgrade→upgrade→downgrade→upgrade。
- **验证：** 单条迁移测试 `1 passed`；新建空卷的完整聚焦门禁 `75 passed in 36.33s`。
- **面试表达：** “迁移测试必须自己建立起点，不能借用开发机历史状态。空数据库是更强的隔离门禁，它把偶然通过变成可重复证明。”

## 28. 工具失败后盲目 replan 会掩盖原始业务错误

- **问题：** 查询不存在的库存对象时，主体工具已经返回 `inventory_not_found`，流程却继续 replan；Mock planner 没有剩余步骤，最终触发空计划校验并由 API 返回 503。
- **根因：** 图路由只看“工具调用结束”，没有区分可重试观察与主体/策略事实不存在；二次规划覆盖了更有价值的原始错误。
- **修复：** 主体事实或策略工具失败时立即安全终止，向外传播第一个结构化 observation error code；只有允许替代路径的失败才进入 replan。
- **验证：** 缺失对象 API 回归恢复为稳定 422，Agent Trace 定向与全量产品测试通过。
- **面试表达：** “Agent 不是失败后都让模型再想一次。业务主体不存在属于确定性终止条件，我让图保留原始错误，避免模型层把可解释的 422 变成基础设施 503。”

## 29. 新架构测试开关不能污染冻结评测基线

- **问题：** 为 Trace API 测试全局启用 Agent runner 后，历史冻结用例 `RPL-024` 的预期 failed 变成 aborted。
- **根因：** 不是产品行为回归，而是测试 harness 把新执行语义扩散到所有旧评测；同一输入在不同 runner 下允许有不同安全终态。
- **修复：** harness 默认保持旧确定性基线，只有 Agent Trace 新用例显式 `agent_trace_enabled=True`；两套语义分别测试、分别声明。
- **验证：** 冻结用例与 Trace 用例同时通过，随后产品测试 545 条全绿。
- **面试表达：** “兼容性不只是 API 字段，也包括评测语义。我没有为了全绿修改旧期望，而是收窄测试开关作用域，让旧基线和新 Agent 路径各自可复现。”

## 30. Windows 与 WSL 不能共用同一个虚拟环境

- **问题：** Windows `uv` 指向 worktree 的 Linux `.venv`，识别到跨平台结构后报拒绝访问，但已部分移除 Linux 可执行目录。
- **根因：** 虚拟环境含平台专属解释器、路径、动态库和入口脚本；同名目录不具备跨操作系统可移植性。
- **修复：** 由 WSL `uv sync --frozen` 严格按锁文件重建 Linux `.venv`；需要 Windows 解释器时使用独立 `.venv-windows`，不得让两个平台写同一目录。
- **验证：** WSL 环境重新安装锁定依赖，Task 7 定向 8 条通过。
- **面试表达：** “锁文件可以跨环境复现依赖选择，虚拟环境目录本身不能跨平台复用。我把依赖声明与环境产物分开管理，损坏后从 lock 重建而不是手工修补。”

## 31. Agent Trace、审计日志与 OTel 必须分层

- **问题：** 如果直接把审计事件或 OpenTelemetry span 显示成 Agent Trace，页面无法解释模型建议、工具事实和 RAG 引用，也可能把异常正文或秘密带给业务用户。
- **设计：** Agent Trace 保存脱敏业务解释；审计日志保存状态变更事实；OTel 保存低基数调用链和耗时。Trace 不记录隐藏思维链，只记录模型输出合同、真实 observation 和 citation reference。
- **验证：** 禁止字段、边界截断、RAG 正文隔离、恢复去重、RBAC 与 SSE snapshot 均有自动化测试；证据见 `docs/release-evidence/agent-trace-rbac.md`。
- **面试表达：** “三套记录的受众和保留策略不同。我单独建模 Agent Trace，是为了让业务可解释性、合规审计和系统可观测性互不污染。”

## 32. 角色权限变化不能让前端丢失业务结果

- **问题：** approver 在等待审批时可读 Trace，但提交审批后 operation 进入 completed，按 RBAC 不再允许 approver 读取终态 Trace。如果页面把详情、Trace、audit 当成一个全成全败请求，审批成功后反而会显示“读取失败”。
- **设计：** 业务详情是主结果，Trace 作为独立权限资源加载；同一 operation 的 Trace 读取被拒绝时保留已加载安全快照，并提示切换 auditor 完成终态核验。读取另一个无权 operation 时不沿用旧 Trace。
- **验证：** API 权限测试证明 approver 只读待审批状态；前端角色引导和 App 编排测试通过。
- **面试表达：** “RBAC 不只是隐藏按钮，还会改变请求组合方式。我让核心业务结果与可解释轨迹独立失败，并用角色接力完成最小授权下的完整演示。”

## 33. CI 数据库镜像必须具备迁移声明的 extension

- **问题：** Agent 核心 Draft PR 首次 Actions 中，三个快速 job 通过，backend-tests 在 Alembic 的 `CREATE EXTENSION vector` 处失败。
- **根因：** 本地 Compose 已迁移到 pgvector 镜像，CI backend service 仍是普通 PostgreSQL 18，导致运行环境和数据库迁移合同漂移。
- **修复：** 先新增 CI 资产 RED，要求固定 `pgvector/pgvector:0.8.2-pg18-trixie` 且禁止 `postgres:18`；再修改工作流，未跳过迁移或 RAG 测试。
- **验证：** 定向 CI/容器资产测试 12 条通过；修复提交 `ba53e70` 后，最新基线 Actions run `29937375023` 的仓库安全、Python 质量、后端和前端全部通过。
- **面试表达：** “数据库 extension 是部署依赖，不只是 Python 包。我用可执行资产测试约束 CI 镜像与 Compose 一致，避免本地绿、远端红的基础设施漂移。”

## 34. Agent replan 应缩小行动空间，而不是重复展示全部工具

- **问题：** Kimi 在第一轮已完成 inventory 与 knowledge 工具后，第二轮仍重复选择已完成工具，Harness 正确拒绝重复调用，但 policy 证据因此缺失。
- **根因：** Graph 已计算缺失证据，却仍把完整工具集交给模型；Prompt 提醒不能消除概率性重复。
- **修复：** 从持久化 observation 计算已完成工具，replan 只暴露 missing tools；同时保留 Harness 的未知工具、重复调用和对象漂移硬拒绝。
- **验证：** RED 证明第二轮错误暴露 inventory + policy；GREEN 后 16 条定向测试通过，真实 Kimi + RAG 图 probe 依次完成 inventory、knowledge、policy。
- **面试表达：** “我把 LLM 当受约束决策器。Graph 用状态收窄可选集合，Harness 守住最终边界；这样既不依赖 Prompt 运气，也不会因为安全拦截直接失去任务进度。”

## 35. provider 异常必须让 operation 进入可解释终态

- **问题：** operation 已创建后，模型或图抛异常会留下 `received`，重启恢复只能把它改成 `recovery_state_conflict`，丢失原始失败语义。
- **根因：** API 创建记录与图执行之间存在异常窗口，旧 runner 没有业务终态补偿。
- **修复：** runner 捕获异常并调用 operation state repository 写入固定 `dependency_unavailable`；若收口写入自身失败，记录固定安全日志并重新抛出原始异常。
- **验证：** 测试覆盖终态写入、provider 文本不持久化、二次失败仍保留原始异常；本地 unit 352 条与关键图集成 7 条通过。
- **面试表达：** “可恢复系统不能只依赖重启扫描兜底。异常发生当下就应把业务记录收口为安全终态，恢复协调器处理的是进程中断，不应替代正常异常处理。”

## 36. 真实模型验证失败也要产生安全、可行动证据

- **问题：** 完整 Compose 代表调用失败时，报告只有 `AssertionError`，既不能定位边界，也存在把响应正文写入异常的泄露风险。
- **设计：** 验证器只允许 stage、HTTP 状态、固定错误码和 operation 状态进入报告；模型原文、Prompt、响应正文、凭据、token 和未返回的成本全部禁止记录。
- **验证：** 单元测试证明敏感异常文本不进入报告；最终 Kimi 代表调用被定位为 `create_operation / 503 / dependency_unavailable`，没有回退 Mock。
- **限制：** 该证据只说明失败被正确分类和收口，不等于真实模型端到端通过；一次约 21 秒完成和一次约 30 秒超时也不能被包装为 SLA。
- **面试表达：** “失败报告的价值是回答‘在哪一层、以什么安全类别失败’，而不是倾倒完整上下文。我用 allowlist 证据定位外部依赖超时，同时避免诊断系统成为新的泄露面。”

## 37. 后端安全错误不能在前端退化成同一句“请重试”

- **问题：** API 已返回 401/403/409/422/503 的稳定 `code + message`，React 客户端却只抛 `api_status_N`，审批组件再吞成通用提示。
- **影响：** 用户无法区分令牌过期、权限不足、审批过期、binding 变化和依赖故障；面试演示也看不到后端安全契约。
- **修复：** 引入类型化 `ApiError`，只解析安全 envelope，并把固定错误码映射为可执行中文动作；未知代理响应仍用固定兜底，不显示原始正文。
- **验证：** RED/GREEN 覆盖 409 过期审批、422 非法请求、403 审计读取及审批组件展示。
- **面试表达：** “错误处理也是端到端契约。后端分类再完整，如果前端统一吞掉，用户恢复路径和安全证据都会丢失。”

## 38. 后端执行了 Verifier，不等于产品能证明执行了 Verifier

- **问题：** 三业务图已在批准后绕过缓存重新取证并调用 Verifier，但 Agent Trace 只显示一个 `execute_controlled_action`。
- **风险：** UI 看起来仍像普通审批工单；模型复核、确定性授权和数据库写入三个责任边界无法解释。
- **修复：** 在产品 Trace 中按顺序投影 `verify_current_facts`、`verify_approval_binding`、`execute_controlled_action`，只保存 decision/route/固定摘要，不保存隐藏推理或原始证据正文。
- **验证：** 单元和数据库集成契约锁定事件语义键、顺序、binding 结果及终态；恢复重放继续依赖 semantic key 去重。
- **面试表达：** “Agent 能力既要真实执行，也要有不泄露思维链的产品证据。我把模型建议、确定性授权和副作用拆成三类可审计事件。”

## 39. 离线复验必须先区分冷缓存与热缓存

- **问题：** 新建空 FastEmbed volume 后直接设置 `HF_HUB_OFFLINE=true`，MCP 无法加载固定 embedding 模型。
- **根因：** 离线模式只禁止联网，不会凭空提供模型文件；之前成功的离线重启依赖已有命名 volume。
- **修复：** 手册明确首次在线预热并确认 MCP healthy，再以同一 volume 离线重建；删除 volume 后必须重新预热。
- **边界：** 这证明“已缓存后的离线可运行”，不声称“空机器完全离线安装”。第三方下载镜像只允许存在于 ignored 本地配置。
- **面试表达：** “我会明确冷启动、热缓存和离线运行三种状态，避免把开发机历史缓存当成可部署性证据。”

## 40. 写入成功与后置读取失败必须分开建模

- **问题：** 审批 API 已返回 204，但 approver 在 operation 完成后因 RBAC 无权读取终态；旧前端把整个回调判为失败，显示“审批未提交”并重新启用按钮。
- **风险：** 用户可能重复提交已经完成的原子决定；界面描述与数据库事实相反，破坏审批竞态和幂等设计的可信度。
- **修复：** 以审批响应作为写入提交边界，只让写入失败拒绝回调；后置刷新独立捕获，明确提示已提交但未读取最新状态，并保持决定按钮禁用。
- **验证：** 测试固定“审批 204 → 刷新 403”的顺序，断言提示、禁用状态和请求次数；完整前端 53 条通过。
- **面试表达：** “分布式 UI 不能把 command 和 query 当成一次原子操作。写入成功后查询失败属于状态未知的读取问题，不代表命令回滚；我让界面以服务端提交事实为准并阻止重复副作用。”

## 41. 安全 envelope 仍需在客户端按 allowlist 消费

- **问题：** 后端错误采用 `code + message` JSON envelope，但未知错误码时前端仍把原始 `message` 拼入提示，可能暴露 provider、代理或堆栈细节。
- **根因：** “结构化 JSON”不等于“内容可信”；客户端错误码映射之外的文本仍是非可信输入。
- **修复：** 已知 code 映射为固定可执行动作；未知 code 只显示固定安全文案与 HTTP 状态，不使用原始正文。
- **验证：** RED 用包含私有 provider 细节的未映射消息证明泄露；GREEN 后 `Error.message` 与 `userMessage` 均不含该文本。
- **面试表达：** “错误 envelope 是传输合同，不是展示白名单。我在前后端两侧都做最小披露，让诊断信息留在受控日志，而不是进入业务用户界面。”

## 42. 本地集成测试也要使用短生命周期凭据

- **问题：** ignored `.env.local` 指向已停止数据库时，连接 traceback 展开了本地角色凭据；完整套件先表现为超时，拆分后才确认是端口拒绝。
- **处置：** 不把连接错误冒充产品 RED；旧值按已暴露处理。新鲜门禁使用仅绑定 loopback、运行时随机密码的一次性 pgvector 容器，测试结束自动销毁。
- **改进：** 恢复长期 Windows 测试库前轮换角色密码并同步 ignored 配置；测试 harness 应进一步缩短连接超时并确保异常永不呈现完整 DSN。
- **面试表达：** “开发测试环境同样是供应链的一部分。我把长期凭据改成一次性门禁凭据，并用 trap 保证失败也清理；同时区分基础设施不可用和业务断言失败。”

## 43. Mock 全绿不代表真实模型协议兼容

- **问题：** 单元、集成和 Mock Compose 全绿后，Kimi K2.6 的真实 Agent 请求仍统一 503。
- **根因：** production factory 复用了 MCP 的 2 秒 timeout；强制 tool calling 与默认 thinking mode 不兼容；最终分析和 Verifier 的通用 structured output 存在供应商波动。
- **修复：** 把模型 timeout 独立为 90 秒；仅在 Moonshot/Kimi adapter 配置关闭 thinking；最终分析与 Verifier 使用两个内部原生提交工具，再由本地 schema 校验。
- **验证：** 三业务真实只读、库存批准写入均通过；无效 provider 仍是 503、failed、零审批和零工单，没有回退 Mock。
- **面试表达：** “Mock 证明我的确定性契约，Real 证明供应商协议兼容。我把差异留在 adapter 边界，并同时保留修复前失败和修复后成功证据。”

## 44. 协议依赖不能共用一个超时语义

- **问题：** MCP 本地请求的 2 秒 timeout 被无意传给远程 LLM，造成正常生成被误判依赖故障。
- **风险：** 配置项名字与实际作用不一致，排障时会误以为网络或模型不可用；继续提高统一 timeout 又会拖慢 MCP 故障发现。
- **修复：** 分离 `OPERCERTA_MCP_TIMEOUT_SECONDS` 和 `OPERCERTA_MODEL_TIMEOUT_SECONDS`，并用 factory 单元测试锁定 2 秒与 90 秒分别进入对应 adapter。
- **面试表达：** “timeout 不是全系统通用数字，而是协议预算。远程生成、本地工具和数据库各有不同延迟与失败语义。”

## 45. `.gitattributes` 不会自动修复既有工作树的 CRLF

- **问题：** 仓库已经声明文本使用 LF，但 WSL 执行 `bootstrap_project_runtime.sh` 仍在 `pipefail\r` 处失败，知识库导入也报告 SOP checksum mismatch。
- **根因：** 行尾规则约束 Git 的规范化和后续检出，不会自动改写规则加入前已经位于 Windows NTFS 工作树中的字节；shell 解释器和内容寻址清单检查的是实际字节，不是 Git 意图。
- **修复：** 审计所有 tracked shell script 的 CRLF 计数并统一转成 LF；三份 SOP 只做行尾归一化，确认归一化后的 SHA-256 与既有 manifest 一致，没有反向修改期望哈希。
- **验证：** Bash 越过 `set -Eeuo pipefail`；全量单元测试 `404 passed`，后端总套件 `664 passed`；当前源码候选镜像的知识导入与三业务 Compose 恢复门禁通过。
- **面试表达：** “跨平台一致性不是只提交一个 `.gitattributes` 就结束。我同时验证 Git 规则、工作树真实字节、Linux 解释器和内容哈希，避免‘版本控制看起来干净、运行时仍然失败’。”

## 46. 冷构建失败与运行候选验证要分开举证

- **问题：** 新电脑执行 Compose 全量 rebuild 时，Dockerfile 的 `uv sync` 在冷缓存依赖下载阶段耗时过长；直接启动旧镜像虽然 healthy，却因包含旧 SOP 而在知识导入阶段失败。
- **风险：** 把 healthy 当作当前源码通过会产生假证据；持续重复冷下载又会拖慢故障收口。
- **处置：** 先比较现有镜像和仓库的 `pyproject.toml`、`uv.lock` SHA-256，确认冻结依赖完全相同；再以该镜像为基底覆盖当前源码、迁移、知识和脚本，生成本地候选镜像执行完整业务与重启恢复验证。
- **验证：** 三业务 Agent、RAG 知识导入、API/MCP 重启恢复和四服务健康均通过；同时明确记录本次没有完成空缓存冷构建，构建历史显示首次冷构建约 32 分钟。
- **面试表达：** “我把依赖层可复现性和应用层候选验证拆开：哈希证明依赖没漂移，候选镜像证明当前源码能运行；冷构建耗时仍单独治理，绝不把替代门禁包装成已解决。”
