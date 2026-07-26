# OperCerta 单根 Agent Loop 与 Case 工作台实施证据

> 日期：2026-07-26
> 分支：`feat/agent-core-implementation`
> 保护基线：`d49577b`
> 生产发布门禁：`CLOSED`

## 结论

本地已完成三业务共享的单根 LangGraph Agent Loop、按业务对象聚合的 React case 工作台、默认生产入口切换、新旧语义等价、Mock Compose、重启恢复和少量真实 Kimi 代表验证。尚未获得 commit/push/merge 或公网可写后端部署授权，不能称为生产上线。

## 架构证据

- FastAPI production factory 只构造 `ControlledAgentRootGraph`，运行与恢复分别由 `ControlledAgentRootRunner`、`ControlledAgentRootRecoveryCoordinator` 进入同一根图。
- 根图包含 `Model → ToolPolicy → MCP Observation → Model` 有界循环，以及确定性 Policy、原生审批 interrupt、批准后强制刷新、模型 Verifier、确定性 binding、幂等写入和写后读。
- 库存、设备和任务只在场景策略、事实 schema、规则评估与工单 payload 上分化，不复制生命周期。
- 历史图模块仍用于回归和新旧等价测试；产品运行时没有隐藏旧路径 fallback。

## 自动化门禁

- 三业务新旧语义等价：`3 passed`，覆盖 assessment、计划哈希、审批绑定、工单 payload、终态与审计事件类型。
- 生产 lifespan：`2 passed`。
- 最终后端单元：`395 passed`；格式修复后的真实模型/entrypoint 聚焦回归 `39 passed`。
- 受影响的根图、等价、signal API 与审批竞态在全新临时 pgvector/PostgreSQL 上 `32 passed`，随机凭据、容器和数据随后销毁。
- 完整集成：`260 passed`；两条 warning 来自测试专用短 JWT key，不是生产配置。
- 前端：19 个文件、`60 passed`；Vite production build 成功。
- Ruff check、Ruff format check、Mypy（85 个源文件）均通过。
- 仓库安全扫描与 Git whitespace/diff 检查通过；同步 worktree 当日日志后，文档索引与排除依赖后的 544 份 Markdown 文件一致。
- 隔离 Compose `opercerta_task9` 完成三业务、RAG citations、数据库事实断言、API/MCP 重启与 recovery-only；临时容器和 volumes 已清理，原演示环境未被修改。

## 真实模型代表证据

在隔离 Compose `opercerta_real_gate`、Moonshot `kimi-k2.6` 下，执行范围严格限制为：

- 库存只读：`real-model-inventory-query-2026-07-26.json`；
- 设备只读：`real-model-equipment-query-2026-07-26.json`；
- 阻塞任务只读：`real-model-task-query-2026-07-26.json`；
- 库存批准写入：`real-model-inventory-approved-2026-07-26.json`；
- 无效 provider fail-closed：`real-model-provider-failure-2026-07-26.json`。

通过路径核对 Agent Trace、RAG 引用、审批、唯一工单和写后读；失败路径为 503/failed/零审批/零工单，未静默回退 Mock。`real-model-query-three-scenarios-2026-07-26.json` 保留首轮失败事实，用于复盘修复前状态，不作为通过证据。

## 已知限制

- API 镜像重建前，浏览器已观察三张 case 主卡及局部历史展开；重建后的浏览器 reload 被本地 URL 安全策略阻止，因此不虚构该次人工复验。
- 当前没有公网可写 HTTPS 后端、生产 IAM/SSO、租户隔离、限流、防滥用、备份恢复、高可用、自动部署或 Release Tag。
- 少量代表调用只证明当前 adapter/provider 组合的兼容路径，不是准确率、SLA、吞吐或成本指标。
- Git 修改仍在本地工作树；提交、推送、合并和公开部署均等待人工审批。
