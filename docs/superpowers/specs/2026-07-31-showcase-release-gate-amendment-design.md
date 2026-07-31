# OperCerta Showcase Release 门禁修订规格

**状态：** 2026-07-31 经用户批准，作为 `v0.1.x` 展示版本的有效修订

**适用范围：** 仅限 OperCerta；不启动 ForenTrail，不把 FieldPilot 纳入本仓库

**修订原则：** 降低公开托管成本，但不降低业务闭环、可靠性、证据和真实性要求

## 1. 修订原因

原始详细设计把“公网 URL 可完成真实核心业务”同时作为作品展示和产品上线条件。当前
OperCerta 已具备公开静态展示、本地可复现完整 Agent MVP、固定评测、真实模型代表验证
和 Docker Compose 重启恢复，但把可写 FastAPI、PostgreSQL、Redis、MCP 与模型服务长期
暴露到公网，还需要生产身份、限流、防滥用、备份、告警和持续费用。

本修订把展示交付和生产上线拆成两个独立门禁，避免为了赶进度把静态页面误报为在线产品，
也避免把生产治理全部塞进求职展示版本。

## 2. 两类门禁

### 2.1 Showcase Release

Showcase Release 定义为：

> 公开静态展示 + 本地可复现完整 Agent MVP + 自动化工程证据 + 本人掌握验收 + 3–5 分钟录屏。

必须同时满足：

1. GitHub 仓库公开，包含 README、许可证、锁文件、架构、限制和可复现命令。
2. Netlify 静态页面可访问，展示真实业务流程、架构、技术栈和已验证证据。
3. 本地 Docker Compose 能启动 PostgreSQL、Redis、MCP 和 FastAPI，并通过 readiness。
4. 库存补货、设备维修、任务恢复共用一个生产 LangGraph 根生命周期。
5. 固定评测、前后端测试、静态检查和 main Compose 重启恢复门禁全绿。
6. 真实模型只做少量代表性兼容验证，不把样本包装成准确率、SLA 或成本结论。
7. 项目所有者亲自完成 `docs/learning/opercerta-ownership-acceptance.md` 的必做验收。
8. 完成 3–5 分钟录屏，展示业务动机、Agent Trace、审批、工单和当前边界。
9. Tag 精确指向通过门禁的 main 提交，并保存回滚点和发布说明。

Showcase Release 允许表述：

> OperCerta 是一个公开源码、通过 CI、可在本地单节点 Docker Compose 中复现三业务完整闭环
> 的受控运营 Agent MVP；公网地址提供只读静态项目展示。

不得表述为“公网可操作 Agent”“生产系统”“高可用平台”或“真实企业 WMS/CMMS”。

### 2.2 Product Release

Product Release 继续使用更严格的生产门禁，至少包括：

- 真实 HTTPS FastAPI 公网入口和精确 Origin CORS；
- 生产身份生命周期、最小权限、会话吊销和审计；
- 限流、配额、模型费用熔断、防滥用和安全数据重置；
- 托管密钥、数据库备份、恢复演练、迁移编排和回滚；
- 日志、Trace、指标采集、Dashboard、告警和运行手册；
- 公网浏览器 E2E、并发、超时、失败恢复和安全验收；
- 明确容量边界，不声称未经验证的 SLA 或高可用。

在这些条件完成前，`Product Release gate: CLOSED`。

## 3. 对原始规格的覆盖关系

本修订只覆盖以下条款在 `v0.1.x Showcase` 中的解释：

- 总体设计“在线地址可以完成核心演示”；
- OperCerta 详细设计“公网 URL 可以完成核心演示”；
- “未通过产品生产门禁前不得开始其他项目”不再阻止已批准的独立后续规划，但本轮用户明确
  暂不启动 ForenTrail，先完成 OperCerta 和后续 FieldPilot。

原始规格中的 Agent 闭环、三业务、审批、幂等、恢复、评测、安全、真实性和不复用旧公司
材料等要求全部继续有效。Product Release 的生产条件没有删除或降级。

## 4. 当前门禁状态

截至本修订创建时：

- 自动化工程与本地 Compose 证据：通过；
- 公开静态展示：通过；
- 开源许可证、状态文档和最新 Release 收口：正在完成；
- 本人掌握验收与 3–5 分钟录屏：尚未验收；
- `Showcase Release gate: AWAITING_OWNER_VALIDATION`；
- `Product Release gate: CLOSED`。

只有本人验收和录屏完成后，才能创建最终 Showcase Tag。

## 5. 失败与回滚

- 任一自动化门禁失败：不合并 main，不创建 Tag。
- 本人无法脱稿解释关键链路：回到对应学习模块和代码重新操作，不代签通过。
- 录屏出现错误或夸大表述：删除候选视频并重录。
- 公网静态部署异常：回滚到上一已验证 Netlify production deploy。
- Product Release 条件未满足：始终保留静态公网与本地完整运行的边界说明。
