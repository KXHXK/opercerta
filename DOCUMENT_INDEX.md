# OperCerta 文档索引

最后核验：2026-07-15，日志初始化 commit `f70411f`。

本文件是 OperCerta 重要文档的中文目录，不复制正文。自动压缩或新会话开始时先阅读本文件，再按“优先级”读取当前状态、过程日志、相关决策、交接和实施计划。

| 路径 | 用途 | 状态 | 最后核验 commit | 优先级 |
| --- | --- | --- | --- | --- |
| `README.md` | 项目概览与使用边界 | 需要随最小纵向闭环同步 | `a0564b1` | 2 |
| `IMPLEMENTATION_HANDOFF.md` | 会话交接与下一动作 | 需要在 PostgreSQL 环境验证后同步 | `a0564b1` | 3 |
| `docs/specs/2026-07-14-agent-project-naming-design.md` | 命名设计 | 已冻结基线 | `c7fa618` | 4 |
| `docs/specs/AI_Agent四项目总体设计规格.md` | 总体设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-agent-portfolio-design.md` | 组合设计 | 已冻结基线 | `48d299c` | 5 |
| `docs/specs/2026-07-14-opercerta-design.md` | OperCerta 详细设计 | 已冻结基线 | `48d299c` | 4 |
| `docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md` | 本机数据库环境决策 | 已确认 | `51c1583` | 4 |
| `docs/superpowers/specs/2026-07-15-development-log-design.md` | 开发日志与上下文恢复规则 | 已确认 | `a0564b1` | 1 |
| `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` | 可靠性内核 TDD 计划 | Task 3 前置条件待环境计划同步 | `24ea72a` | 3 |
| `docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md` | PostgreSQL 环境计划 | 待执行 | `85c04d1` | 1 |
| `docs/superpowers/plans/2026-07-15-development-log-bootstrap.md` | 日志初始化计划 | 执行记录见开发日志 | `6c97d5d` | 1 |
| `docs/development-log/README.md` | 日志机制说明 | 已初始化 | `f70411f` | 1 |
| `docs/development-log/current-state.md` | 当前已验证状态 | 已初始化 | `f70411f` | 1 |
| `docs/development-log/daily/2026-07-15.md` | 当日过程记录 | 已初始化 | `f70411f` | 2 |
| `docs/development-log/decisions/2026-07-15-windows-native-postgres.md` | 环境架构决策 | 已初始化 | `f70411f` | 2 |

## 计划创建

docs/release-evidence/ 仅在实际测试或发布验证产生可复查证据后创建；当前没有对应文件。它不能替代 `docs/development-log/`，也不能在发布门禁关闭时被写成已完成发布。

## 维护规则

- 新增、移动、废弃或改变重要文档状态时，在同一 Git commit 更新本索引。
- 索引只列出已存在的文件；计划创建的目录只以普通文字说明，不伪造 Markdown 链接。
- 索引不保存密码、token、API key、私有连接串、真实客户数据或模型内部推理。
- 日志、Git、测试或实际服务状态冲突时，以新鲜命令输出为准，并在当日过程日志记录更正。
