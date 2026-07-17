# 库存补货固定契约评测证据

**日期：** 2026-07-18  
**范围：** 当前库存补货后端的 30 条冻结合成契约；真实 FastAPI、FastMCP、PostgreSQL 与 LangGraph 恢复边界。  
**结论：** 本地契约回归基线通过；不代表模型准确率、性能指标、生产效果、独立第三方评测或公开发布。

## 实测结果

- `uv run python scripts/run_replenishment_evaluation.py --suite data/evals/replenishment-v3.json --output-dir tmp/evals`：30 条，30 passed、0 failed；逐例脱敏报告输出至被 Git 忽略的 `tmp/evals/replenishment-v3-report.json`。
- `uv run pytest -q`：323 passed。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src`：均退出码 0。

## 诚实边界

- 覆盖当前已实现的输入拒绝、JWT/RBAC、审批绑定与竞态、幂等工单、事实变化、安全工具白名单和重启恢复。
- v1、v2 在首次有效基线前发现期望与真实稳定语义不符，均升级版本并留痕；当前有效套件为 v3。
- `OperCerta release gate: CLOSED`：前端、SSE、真实模型、完整生产 IAM/SSO、可观测性、CI/CD、公开部署和远程备份仍未完成。
