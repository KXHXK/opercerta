# OperCerta 异常信号收件箱 TDD 实施计划

**依据：** `docs/superpowers/specs/2026-07-25-operational-signal-inbox-design.md`
**执行方式：** Inline TDD；每项先观察目标 RED，再做最小 GREEN
**回滚基线：** `d49577b`

## Task 1：冻结领域与业务动机契约

1. 为 signal 模型、稳定枚举、幂等键和三场景草案编写单元 RED。
2. 实现严格 `OperationalSignal`、`SignalDraft`、watch target 与事实摘要。
3. 复用既有 assessment，不复制库存/设备/作业规则。
4. 运行领域聚焦测试、Ruff、format、mypy。

## Task 2：`0007` 与并发安全 Repository

1. 编写迁移、重复扫描、十路并发 upsert、对象失配和十路调查绑定 RED。
2. 新增 `0007_operational_signals` 和 SQLAlchemy schema。
3. 实现 `SignalRepository.upsert_detected/list_active/load/reconcile`。
4. 扩展 operation 创建事务，在 signal 行锁内原子绑定。
5. 验证 `0006 → 0007 → 0006 → 0007`、数据库 focused 和静态门禁。

## Task 3：确定性扫描服务

1. 使用 fake typed gateway 编写正常零 signal、三异常 signal、部分依赖失败和重复扫描 RED。
2. 实现 `SignalDetectionService`，并发读取各目标但逐对象安全收口。
3. 扫描阶段断言零模型、零 RAG、零 operation、零工单。
4. 运行应用层 focused 和静态门禁。

## Task 4：Signal API、RBAC 与 Agent 启动

1. 扩展测试 runtime，编写 scan/list/investigate、401/403/404/409/422/503 RED。
2. 把只读 MCP gateway 和 signal services 注入 `AppRuntime`。
3. 新增三个 signal API；investigate 由服务端构造绑定请求。
4. 外部 `/operations` 的写动作必须带 signal；query 继续可用。
5. Agent 创建/审批/恢复后 reconcile signal 状态。
6. 运行 API focused、OpenAPI、安全 envelope 和静态门禁。

## Task 5：React 异常信号收件箱

1. 先写客户端契约、空态、扫描、部分失败、卡片选择和启动 Agent RED。
2. 新增 `SignalInbox`；移除固定对象作为主要入口。
3. 将“创建处置”改为“交给 Agent 分析”，把“查询状态”降为诊断入口。
4. signal 卡片明确展示“确定性检测”，不把它包装成 LLM 结论。
5. 运行前端 focused、全量、TypeScript/Vite build 和响应式检查。

## Task 6：三业务 Compose 与恢复证据

1. 更新 Compose 验证脚本：scan → 三 signal → 三 Agent → 审批 → Verifier → 三工单。
2. 断言重复扫描不新增 signal、同 signal 不产生第二个 operation。
3. 重启 API/MCP 后核验 signal-operation 绑定与 Trace 不重复。
4. 运行 Mock release Compose；Real Kimi 仍使用独立代表性门禁，不以 Mock 冒充。

## Task 7：总门禁和文档收口

1. 完整后端、前端、Ruff、format、mypy、lock、安全扫描。
2. 更新 README、核心技术手册、手动实验、面试讲解、架构证据、当前状态、交接和当日日志。
3. 在根 `DOCUMENT_INDEX.md` 的 agent-core-implementation 独立表及 worktree 自身索引登记全部新增 Markdown。
4. 停在人工提交审批；未经批准不 commit/push/Ready/merge。

## 完成口径

只有以下事实同时成立，才算本修订完成：

- 用户先看到来源明确的异常 signal，再启动 Agent；
- 确定性规则负责发现，LLM 不判断简单阈值；
- operation 与 signal 原子绑定且并发只有一个胜者；
- 三业务仍完整通过审批、Verifier、幂等与恢复门禁；
- UI、代码、文档和面试表述使用同一业务动机；
- 所有数字都有测试或脚本证据，不虚构生产指标。

## 2026-07-25 实施结果

Task 1--7 的本地实现与验证已完成，并停在人工提交审批点。新鲜证据为完整后端 `600 passed in 178.48s`、前端 18 文件/`56 passed` 与 production build、Ruff、Mypy 79 个源文件，以及隔离空卷 Mock release Compose 退出码 0（175.1 秒）。远程 CI、修订后的 Real Kimi、commit/push/PR 合并和生产治理不属于这条本地完成证据，发布门禁保持 `CLOSED`。

用户首屏复核后补充修正：扫描权限改为首次点击按需签发 operator JWT；角色切换不得加载历史 signal；scan 返回服务端 `scanned_at`，页面必须解释固定三对象 watchlist、6 次 MCP 读取、三类规则事实与事实哈希去重。修正后的完整门禁仍为后端 `600 passed in 189.97s`、前端 `56 passed` 与 production build、Ruff、Mypy 全绿。
