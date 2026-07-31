# 参与 OperCerta 开发

[English](CONTRIBUTING.md) | **简体中文**

感谢你帮助改进 OperCerta。所有贡献都应保留项目的核心属性：LLM 输出可以辅助
调查和解释，但高风险业务写入必须由确定性规则、人工审批和数据库约束控制。

## 开始之前

- 新建 Issue 前先搜索已有 Issue 和 Pull Request，避免重复。
- 修改 Agent 状态模型、审批边界、持久化模型、公开 API 或依赖架构前，先建立 Issue 讨论。
- 每次变更只解决一个明确问题。
- 示例只使用合成或匿名数据。
- 禁止提交凭据、token、私有地址、客户记录或原单位机密材料。

## 开发环境

推荐使用 Linux 或 WSL2、Docker Compose v2、由 `uv` 管理的 Python 3.12，
以及 Node.js 24。

```bash
git clone https://github.com/KXHXK/opercerta.git
cd opercerta

uv sync --frozen --all-groups

cd web
npm ci
```

本地运行时需要把 `.env.compose.example` 复制为 `.env.compose`，将占位符替换为
仅本地使用的值，然后按照[快速启动](README.zh-CN.md#快速启动)操作。

## 开发流程

1. 从最新 `main` 创建分支。
2. 复现问题或先增加失败测试。
3. 实现最小且完整的修改。
4. 运行受影响范围的定向测试。
5. 运行对应区域的必需质量门禁。
6. 检查 `git diff`，排除无关修改和敏感数据。
7. 创建 Pull Request，说明问题、实现、验证和已知边界。

不得仅为让测试通过而削弱或删除安全断言。如果契约确实需要修改，应说明业务
原因，并同步更新实现、测试、文档以及迁移/恢复行为。

## Agent 与业务安全规则

- 用户输入和模型输出必须经过严格的类型化 Schema。
- 工具必须加入显式白名单，禁止任意工具执行。
- 业务数量、权限和状态转换必须保持确定性。
- 受控写入必须保留人工审批。
- 审批必须绑定相关证据、规则、事实和计划哈希。
- 审批后、执行前必须重新读取权威事实。
- 写工具必须幂等，并验证数据库后置条件。
- provider、解析、规则、审批或依赖异常时必须 fail closed。
- 保持 LangGraph 重启恢复语义，不得把 checkpoint 当成业务事实源。
- 不得记录密钥、完整 Prompt、隐藏推理、SQL 参数或敏感证据。

## 质量门禁

### Python 与后端

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run python scripts/run_opercerta_evaluation.py
uv run python scripts/run_agent_evaluation.py
uv run python scripts/verify_repository_safety.py
```

数据库集成测试需要兼容的 PostgreSQL/pgvector。必须使用隔离测试数据库，禁止把
测试指向业务或个人数据。

### 前端

```bash
cd web
npm run test:run
npm run build
```

### Compose 行为

在全新的本地 Compose 项目中执行：

```bash
docker compose up --build -d --wait
python3 scripts/verify_agent_compose.py
docker compose restart api mcp
python3 scripts/verify_agent_compose.py --recovery-only
```

业务验证脚本会创建合成 operation 和工单，不得对需要保留状态的数据库运行。

## 文档规则

- 公开项目行为变化时，保持 `README.md` 与 `README.zh-CN.md` 结构和事实一致。
- 贡献流程变化时，保持 `CONTRIBUTING.md` 与 `CONTRIBUTING.zh-CN.md` 一致。
- 新增、移动或删除 Markdown 文件时，必须在同一提交更新 `DOCUMENT_INDEX.md`。
- 区分实测结果与假设，不得把固定合成评测表述为生产准确率或 SLA 证据。

## Pull Request 检查表

Pull Request 应包含：

- 问题与预期行为；
- 实现方式和重要取舍；
- 准确的验证命令与结果；
- 数据库或 API 兼容性影响；
- 与恢复、幂等、审批和安全相关的影响；
- 已知限制和后续工作。

请求 Review 前确认：

- [ ] 变更范围明确，分支基于最新 `main`；
- [ ] 行为变化具有测试；
- [ ] 不包含密钥和私有数据；
- [ ] 相关 Python、前端或 Compose 门禁通过；
- [ ] 公开中英文文档保持同步；
- [ ] `DOCUMENT_INDEX.md` 已更新。

## 报告安全问题

不要在公开 Issue 中发布可利用细节、凭据或敏感数据。请私下联系仓库所有者，
提供最小复现、受影响版本和影响范围。项目计划增加独立安全策略和私密报告渠道，
但当前尚未配置。
