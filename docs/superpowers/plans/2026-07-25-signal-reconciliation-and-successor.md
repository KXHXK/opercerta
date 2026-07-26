# OperCerta Signal 对账与后继调查 TDD 计划

**依据：** `docs/superpowers/specs/2026-07-25-signal-reconciliation-and-successor-design.md`

## Task 1：RED

1. 为 predecessor 契约和 retry 去重键写单元测试。
2. 为 `0008` 列、外键与唯一约束写迁移测试。
3. 为历史对账、重复对账和十路 successor 并发写数据库测试。
4. 为 retry API 和 React 入口写失败测试，保存 RED 证据。

## Task 2：GREEN 后端

1. 增加 `0008_signal_successor_lineage` 与 SQLAlchemy schema。
2. 扩展 `OperationalSignal`，实现稳定 retry key。
3. 实现幂等 `reconcile_terminal_links()` 与并发安全 `create_successor()`。
4. 在 production lifespan 中先恢复 operation，再对账 signal。
5. 增加 operator-only retry API，复用现有 operation 原子绑定。

## Task 3：GREEN 前端

1. 扩展 TypeScript 契约和 API Client。
2. 为 `attention_required` 提供“重新调查”。
3. 加载新 operation、Trace、审批与审计；不得覆盖旧历史。

## Task 4：门禁和运行证据

1. 聚焦后端、前端测试。
2. 完整 Pytest、Ruff、format、mypy、前端全量/build。
3. 迁移往返、Compose 旧卷启动对账、并发 retry 和重启复核。
4. 更新核心技术手册、开发日志、当前状态与 `DOCUMENT_INDEX.md`。
5. 停在人工提交审批，不 commit/push/merge。

## 实施结果

- Task 1–4 已按 RED/GREEN 完成。领域与前端先分别观察到缺失契约、缺失 retry client/入口的失败；浏览器验收又发现 scan 返回根 signal 时遗漏 successor，补充 RED App 测试后修复。
- 新增 `0008_signal_successor_lineage`。首次迁移因 PostgreSQL 约束名超过 63 字节失败，缩短为 `fk_signal_predecessor` 后完成迁移往返。
- 历史对账、重复对账、十路 successor/retry 竞态均通过；同一 predecessor 只能产生一个 successor。
- 完整后端 `607 passed in 329.96s`；前端 18 个文件 `58 passed` 且 production build 成功；Ruff、199 文件 format 和 mypy 80 个源文件通过。
- 旧持久卷启动后，三个过期关联 signal 均对账为 `attention_required`；旧 operation 保持 `expired`。
- 库存 predecessor 已创建唯一 successor `2cef23d3-1b30-436b-82b0-7a29125c6372` 与新 operation `157347ee-ba5b-4911-bfe9-3f64a47ad162`，后者在 API/MCP 重启后仍为 `awaiting_approval`；重复 retry 返回 HTTP 409。
- 浏览器验收显示两个可重试入口、一个已有后继谱系、一个调查中信号。详细证据见 `docs/release-evidence/signal-reconciliation-successor.md`。
- 本轮未调用 Real Kimi，未 commit/push/merge；人工审批和生产发布门禁未越过。
