# React Agent 工作台与角色接力证据

日期：2026-07-22
范围：Agent 核心架构计划 Task 8
结论：前端组件、生产构建和三档响应式检查通过；真实后端浏览器端到端属于 Task 9，生产发布门禁仍为 `CLOSED`。

## 页面解决的问题

旧控制台只能选择场景、提交工单并查看业务事实/审计，无法解释 Agent 的感知、规划、工具、RAG、模型建议和确定性边界。Task 8 保留有限业务表单，不增加开放聊天框，把真实后端 `AgentTraceSnapshot` 映射为一页可追踪工作台：

1. 固定场景/对象/动作表单；
2. 结构化 Goal；
3. 后端持久化 Agent Trace；
4. MCP observation 与 SOP citation reference；
5. 模型建议和确定性执行计划对照；
6. 审批绑定、批准后 Verifier 说明；
7. 工单/结果回读、下一角色引导和独立业务审计。

## 组件与边界

- `IntentCard`：显示后端 operation 请求与 Goal 编码，不提供自由聊天输入。
- `AgentTrace`：按 sequence 展示九类真实事件、节点、状态和安全引用；不展示隐藏思维链。
- `EvidenceAndCitations`：展示 MCP 安全摘要和 document/chunk/version/score，不展示 SOP 原文。
- `DecisionComparison`：明确模型只提供建议，动作参数、审批和写入由 Policy Guard 与数据库控制。
- `NextRoleGuide`：保留 operation，在 operator → approver → auditor 之间给出下一步；approver 在终态无权重新读取 Trace 时，页面保留同一 operation 已加载轨迹并引导 auditor 接管。
- `ApprovalPanel`：展示规则版本、事实哈希和计划哈希短摘要；批准后明确重新取证、事实漂移进入复审。
- audit timeline 保持独立，不冒充 Agent Trace。

## 测试驱动证据

- RED：五个 Agent 组件和 `ApiClient.getAgentTrace` 不存在，目标测试失败；原有 client 测试继续通过。
- GREEN：组件、API client、App 编排、审批和业务详情聚焦为 20 条通过。
- 完整前端：`17 passed` 测试文件、`46 passed` 测试。
- 生产构建：TypeScript project build 与 Vite 8.1.5 构建成功；产物 JS 244.21 kB（gzip 78.39 kB），CSS 22.35 kB（gzip 5.30 kB）。这些是构建产物大小，不是性能指标。

## 浏览器响应式检查

在本地 `/console` 请求 1440×1000、1024×900、390×844 三档视口检查：

- document scroll width 始终等于可视宽度，无应用元素越过左右边界；
- `main` 内 fixed/sticky 元素为 0；
- 390 档流程条为两列，避免七阶段单列占用整个首屏；
- 标题、角色/场景选择、门禁状态和下一步信息可读；
- `prefers-reduced-motion` 继续关闭过渡动画。

浏览器自身注入的批注根节点是 fixed，不属于项目 DOM；长页面 full-page screenshot 出现工具拼接重复，普通 viewport screenshot 与 DOM snapshot 均只有一份页面，因此未修改产品代码迎合工具截图。

## 尚未证明

- 本轮浏览器检查使用尚未认证的本地空状态，没有把它写成完整业务 E2E。
- Task 9 仍需在 Compose 中运行真实 API/MCP/PostgreSQL，完成 operator 创建、approver 审批、Verifier、工单回读、auditor Trace、重启恢复和少量真实 Kimi 代表验证。
- 公网静态专题仍不连接可写后端；生产 IAM、限流、备份、HTTPS 交互后端和发布门禁均未完成。
