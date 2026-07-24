# 2026-07-23 OperCerta 规格一致性审计

## 结论

项目主线没有偏离。当前实现是单 Agent、受控表单、Plan-and-Execute、LangGraph 持久编排、MCP 工具、pgvector RAG、人工审批、批准后复核、确定性授权与幂等工单的组合；不是自由聊天、多 Agent，也不是只有模型文案的传统工单页面。

## 已对齐的核心能力

| 规格目标 | 当前实现证据 | 结论 |
| --- | --- | --- |
| 三业务闭环 | 库存补货、设备维修、作业异常恢复均有 query 与受控写路径 | 对齐 |
| Agent 编排 | LangGraph 状态、条件路由、有界 replan、interrupt/checkpoint/recovery | 对齐 |
| 模型与 Prompt | Goal、Planner、Analyst、Verifier、Reporter 版本化 Prompt；Mock/Real 严格分离 | 对齐 |
| 工具与 RAG | 七个 FastMCP 工具；知识检索使用 FastEmbed + PostgreSQL/pgvector | 对齐 |
| Harness | Goal/预算、ToolPolicy、ToolExecutor、模型适配、Pydantic validator、场景 guardrail、Trace 脱敏按模块组合 | 对齐，避免夸大为单类万能 Harness |
| 可靠写路径 | PostgreSQL 原子审批、审批周期、binding、批准后直读复核、唯一约束与写后读 | 对齐 |
| 前端展示 | 有限表单、业务事实、Agent Trace、RAG 引用、建议/规则对照、审批、审计和角色接力 | 对齐 |
| 技术边界 | 合成数据、门禁 CLOSED、无生产 SLA/成功率/成本虚构 | 对齐 |

## 本轮发现并修复

1. **安全错误被前端吞掉。** `ApiClient` 原先只抛 `api_status_409` 等字符串，审批区再统一显示“审批未提交”。现保留 status/code/message，并映射非法输入、登录失效、权限不足、重复/过期审批、binding 变化和依赖故障的可操作中文提示；audit snapshot 同样不再丢失 envelope。
2. **Verifier 在产品 Trace 中不可见。** 三个场景图已经真实执行批准后重新取证和模型复核，但 Trace 只显示 `execute_controlled_action`。现增加 `verify_current_facts` 模型事件与 `verify_approval_binding` 确定性护栏事件，并保证它们先于写入事件。
3. **安全终态的 Trace run 未必结束。** rejected、aborted、expired 原先会落到 `running`。现将它们视为完成的安全业务终态；只有 failed 使用失败 run 状态。
4. **主业务角色混入未完成管理能力。** 控制台移除 `demo-admin` 选项，只保留 operator、approver、auditor。后端身份契约暂留，独立管理入口等用户批准后再做。
5. **离线冷启动说明不完整。** 空 FastEmbed volume 不能直接 `HF_HUB_OFFLINE=true`。手册现明确先在线预热、确认 MCP healthy，再离线重建验证。
6. **设计状态过时。** Agent 核心规格页仍写“尚未实施”，现改为核心实现和 Draft PR 已完成，同时继续引用新鲜证据且保持发布门禁关闭。

## 审查后不做无收益重构

- 规格中的 Goal、Planner、RAG、Validator、Verifier 等是逻辑节点，不要求为了图形一致性全部拆成独立 LangGraph node；现有组合已保留可测试职责与 Trace 证据。
- `docs/development-log/decisions/` 已承担 ADR 的决策、替代方案和结果记录，不再复制一套空的 `docs/adr/` 目录。
- React 静态展示由 Netlify 承载，本地业务服务由 Compose 承载；不为了“Compose 服务数量”再塞一个重复前端容器。release Compose 已有 Caddy/静态资源边界。

## 延期与人工审批项

- demo-admin 独立本地入口、种子重置、固定评测管理 API。
- Real Kimi 新 Agent 完整 Compose 稳定通过。
- Draft PR 合并、main Compose、Release Tag。
- 公网交互后端、生产身份、限流、防滥用、备份和高可用。

这些缺口不影响本地三业务 Agent 技术闭环的真实性，但影响生产上线声明。发布门禁保持 `CLOSED`，且不启动 ForenTrail。

## 新鲜验证

- 后端 unit：`356 passed in 38.86s`。
- 前端：17 个测试文件、`51 passed`；TypeScript/Vite production build 成功。
- Python 质量：Ruff 通过，`182 files already formatted`；Mypy 76 个源文件通过；`git diff --check` 通过。
- Mock Compose：三业务 Agent 验证退出码 0；批准路径强制断言 Verifier、binding guardrail、controlled execution 的事件和顺序。
- 重启恢复：API/MCP restart 后 recovery-only 退出码 0；API、MCP、PostgreSQL、Redis 均 healthy。

独立本地测试数据库端口未监听，因此新增数据库集成测试未取得本机绿色结果；其同语义无数据库单元测试与真实 Compose/PostgreSQL 断言已通过。完整数据库集成和仓库安全仍需本批修改 push 后由 Draft PR Actions 复验，不能用旧 run 代替。
