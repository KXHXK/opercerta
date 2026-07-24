# OperCerta 规格一致性审计与最小修复计划

> 日期：2026-07-23
> 范围：只实施 OperCerta；不合并 PR、不发布生产、不调用额外真实模型
> 方法：原始四设计 → Agent 核心修订 → 实现 → 自动化证据逐项对照，明确偏差按 TDD 修复

## 目标

保证 OperCerta 仍是“传统仓库/运营工单可靠性内核 + 受控 AI Agent 增强”，既不退化成普通 CRUD 工单，也不扩成自由聊天、多 Agent 或无边界自治系统。修复优先服务于本地完整闭环、求职展示、技术讲解和后续人工排障。

## 审计顺序

1. 核验 Git 分支、工作树、依赖锁、Compose 与现有 CI 基线。
2. 对照命名设计、总体设计、组合设计、OperCerta 详细设计、三业务修订与 Agent 核心规格。
3. 检查三业务、LangGraph、Prompt、LLM、Harness、MCP、RAG/Memory、PostgreSQL、Redis、审批、Verifier、幂等写入、恢复、Trace、React 与安全错误契约是否真实接线。
4. 将偏差分为“本轮修复”“记录后延期”“人工审批门禁”。
5. 对本轮修复先写失败测试，再修改实现；最后运行前后端、静态检查与可用环境内的 Compose/数据库门禁。

## 本轮最小修复

- 保留 API 安全错误 envelope，在 React 中给出可执行中文提示。
- 把批准后 Verifier 与确定性绑定护栏投影为独立 Agent Trace 事件。
- 让 completed/rejected/aborted/expired/failed 都正确结束 Trace run。
- 主业务角色只展示 operator、approver、auditor；不把未完成管理能力伪装成可用角色。
- 补充 FastEmbed 空缓存首次在线预热、后续离线复验的手动说明。
- 更新已实施规格状态、文档索引、中文开发日志和面试案例。

## 不在本轮自动扩展

- 独立 demo-admin 种子重置与固定评测入口。
- 公网可写 API、生产 IAM/SSO、限流、备份、高可用与自动发布。
- Real Kimi 完整 Compose 的额外付费/外部调用。
- Draft PR 合并、main Compose、Release Tag 与生产门禁开启。

这些事项会改变安全、成本或发布状态，必须留给用户回来后审批。
