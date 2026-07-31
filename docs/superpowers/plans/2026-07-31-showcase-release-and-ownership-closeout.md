# OperCerta Showcase Release 与 Ownership 收口实施计划

**规格依据：** `docs/superpowers/specs/2026-07-31-showcase-release-gate-amendment-design.md`

**目标：** 完成可自动化的 Showcase 候选收口，并进入必须由项目所有者亲自通过的验收

**排除：** 公网可写后端、生产 IAM、ForenTrail、FieldPilot 代码

## Task 1：用测试固定收口契约

- 为双门禁、Apache-2.0 许可证、最新测试数、ownership 手册和 Docker uv 版本添加 RED 测试。
- 为 README 中文版和两份 Contributing 增加凭据扫描回归。
- 保留 RED 输出作为“缺口真实存在”的实施证据。

## Task 2：实施发布治理

- 新增 Apache-2.0 `LICENSE`。
- 把 Dockerfile 的 uv 与 CI 固定为 `0.11.28`。
- 扩展仓库安全扫描到全部公共入口 Markdown。
- 将 README 的后端门禁数字同步到最新 main 事实。

## Task 3：同步唯一当前事实

- 重写 `docs/development-log/current-state.md`，只保留当前权威状态与历史导航。
- 重写 `IMPLEMENTATION_HANDOFF.md`，删除会误导新对话的旧“当前”状态。
- 更新 2026-07-31 审计、每日日志和 `DOCUMENT_INDEX.md`。
- 明确 Showcase、Product 和个人掌握三类状态。

## Task 4：建立 Ownership 验收

- 新增 `docs/learning/opercerta-ownership-acceptance.md`。
- 要求项目所有者亲自完成环境、业务、代码、故障和口述五组验收。
- operation/work-order 标识、截图、口述和视频只能来自本人实际操作，不得由 Codex 自动代签。

## Task 5：自动化门禁与合并

- 运行定向测试、仓库安全、文档索引、Ruff/format 和必要前后端门禁。
- 通过 PR 合并 main，等待 main-only Compose smoke。
- 不在人工验收前创建最终 Showcase Tag。

## Task 6：人工验收与最终 Tag

- 项目所有者按手册完成一个完整库存闭环、一次重启恢复和一次代码讲解。
- 完成 30 秒、3 分钟、10 分钟口述以及 3–5 分钟录屏。
- 将验收日期、operation_id、work_order_id、视频位置和诚实边界写入开发日志。
- 自动化与人工证据全部通过后创建最终 Showcase Tag，并记录回滚提交。
