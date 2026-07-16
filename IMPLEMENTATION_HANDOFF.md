# OperCerta｜智能运营处置 Agent：实施交接

## 当前检查点

- 书面设计已经总审通过并冻结为实施基线；当前文档目录见根目录 `DOCUMENT_INDEX.md`。
- 可靠性内核的非法输入、确定性恢复、数据库迁移和原子审批竞态已实现；最近完整测试为 `34 passed`，审批竞态目标用例重复 `20/20` 通过。
- Windows 原生 PostgreSQL 18.4 已验证为本地集成测试数据库：服务仅监听 `127.0.0.1:55432`，普通 IPv4 回环使用 SCRAM；证据见 `docs/release-evidence/native-postgres-environment.md`。
- 审批原子性证据见 `docs/release-evidence/approval-atomicity.md`。曾被失败 traceback 展开的本地测试角色密码已轮换并复验；新值不得粘贴到对话或写入 Git。
- Task 4 已确认采用通用 JSON object payload，并固定新工单初始状态为 `created`；用户已确认 `docs/superpowers/specs/2026-07-16-work-order-idempotency-contract-design.md`，当前正在回填实施计划，尚未写生产代码。
- 当前 Git 尚未配置远程仓库；本地 commit 不是远程备份。
- 发布门禁保持 `CLOSED`，不启动 ForenTrail 或其他项目。

## 新对话必须先做

1. 先阅读 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md` 和最近每日日志，再阅读相关设计、计划、交接和 Git 状态。
2. 只实施 OperCerta；从已确认的 Task 4 幂等工单规格和回填后的精确计划开始幂等写入 TDD。
3. 运行集成测试前，以不回显方式从已忽略 `.env.local` 加载 `OPERCERTA_DATABASE_URL`；不得提交该文件或任何凭据。
4. 每个效果数字都保留基线、测试数据、测量脚本和结果证据；指标未测出前使用目标值或空值，不写成已实现结果。
5. 使用公开或合成数据，从零编写全部代码和文档，不导入任何原单位源码、数据、截图、模型、品牌或内部规则。

## 第一阶段完成条件

- 非法输入、状态恢复、审批竞态和幂等写入测试先于对应实现并可重复运行。
- 最小纵向闭环能够在本地 PostgreSQL 环境运行，失败路径和人工接管路径可演示；Linux/Docker 一致性验证在发布门禁阶段完成。
- README、架构图、接口说明、评测报告、部署与回滚说明随实现同步更新。
- 通过详细设计中的发布门禁后，再部署公开演示、填写在线地址并开始 ForenTrail。

## 可复制到新对话的启动语

> 工作目录为本 OperCerta 仓库根目录。请先读取 `DOCUMENT_INDEX.md`、`docs/development-log/current-state.md`、最近每日日志、`README.md`、`IMPLEMENTATION_HANDOFF.md` 和 `docs/specs/` 下的四份设计文件，顺序为命名设计、总体设计、组合设计、OperCerta 详细设计；然后从可靠性内核 Task 4 的幂等写入 RED 测试继续。严格只实施 OperCerta，不复用旧公司材料，不虚构指标，未通过发布门禁前不启动其他项目。
