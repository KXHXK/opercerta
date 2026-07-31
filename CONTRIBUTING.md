# Contributing to OperCerta

<details name="contributing-language" open>
<summary><strong>简体中文</strong></summary>

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
仅本地使用的值，然后按照 [README 快速启动](README.md)操作。

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

- 公开项目行为变化时，同时更新 `README.md` 内的中英文面板并保持事实一致。
- 贡献流程变化时，同时更新 `CONTRIBUTING.md` 内的中英文面板。
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

</details>

<details name="contributing-language">
<summary><strong>English</strong></summary>

Thank you for helping improve OperCerta. Contributions should preserve its
core property: LLM output may assist investigation and explanation, but
deterministic policy, human approval, and database constraints control
high-risk business writes.

## Before You Start

- Search existing issues and pull requests before opening a duplicate.
- Open an issue before changing the Agent state model, approval boundary,
  persistence model, public API, or dependency architecture.
- Keep each change focused on one problem.
- Use only synthetic or anonymized examples.
- Never commit credentials, tokens, private endpoints, customer records, or
  confidential company material.

## Development Environment

The recommended environment is Linux or WSL2 with Docker Compose v2, Python
3.12 managed by `uv`, and Node.js 24.

```bash
git clone https://github.com/KXHXK/opercerta.git
cd opercerta

uv sync --frozen --all-groups

cd web
npm ci
```

For a local runtime, copy `.env.compose.example` to `.env.compose`, replace its
placeholders with local-only values, and follow the [Quick Start](README.md#quick-start).

## Development Workflow

1. Create a branch from the latest `main`.
2. Reproduce the problem or add a failing test.
3. Implement the smallest coherent change.
4. Run the relevant focused tests.
5. Run the required quality gates for the affected area.
6. Review `git diff` for unrelated changes and sensitive data.
7. Open a pull request with the problem, implementation, validation, and known limits.

Do not weaken or delete a safety assertion merely to make a test pass. When a
contract must change, explain the business reason and update implementation,
tests, documentation, and migration/recovery behavior together.

## Agent and Business Safety Rules

- Keep user inputs and model outputs behind strict typed schemas.
- Add tools to the explicit allowlist; do not enable arbitrary tool execution.
- Keep business quantities, permissions, and state transitions deterministic.
- Preserve human approval for controlled writes.
- Bind approvals to the relevant evidence, rule, fact, and plan hashes.
- Re-fetch authoritative facts after approval and before execution.
- Make write tools idempotent and verify their database postconditions.
- Fail closed on provider, parsing, policy, approval, or dependency errors.
- Preserve LangGraph restart behavior and do not treat checkpoints as the business source of truth.
- Do not log secrets, full prompts, hidden reasoning, SQL parameters, or sensitive evidence.

## Quality Gates

### Python and backend

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run python scripts/run_opercerta_evaluation.py
uv run python scripts/run_agent_evaluation.py
uv run python scripts/verify_repository_safety.py
```

Database integration tests require a compatible PostgreSQL/pgvector instance.
Use an isolated test database and never point the suite at business or personal
data.

### Frontend

```bash
cd web
npm run test:run
npm run build
```

### Compose behavior

With a fresh local Compose project:

```bash
docker compose up --build -d --wait
python3 scripts/verify_agent_compose.py
docker compose restart api mcp
python3 scripts/verify_agent_compose.py --recovery-only
```

Do not run the business verifier against a database whose state must be
preserved: it intentionally creates synthetic operations and work orders.

## Documentation

- Keep the Chinese and English panels in `README.md` equivalent when public
  project behavior changes.
- Keep the Chinese and English panels in `CONTRIBUTING.md` equivalent when the
  contribution process changes.
- Register every added, moved, or removed Markdown file in `DOCUMENT_INDEX.md`
  in the same commit.
- Distinguish observed results from assumptions, and do not present fixed
  synthetic evaluations as production accuracy or SLA evidence.

## Pull Request Checklist

A pull request should include:

- the problem and intended behavior;
- the implementation and important trade-offs;
- exact validation commands and results;
- database or API compatibility impact;
- recovery, idempotency, approval, and security impact when relevant;
- known limitations and follow-up work.

Before requesting review, confirm:

- [ ] the change is scoped and the branch is based on current `main`;
- [ ] behavior changes have tests;
- [ ] secrets and private data are absent;
- [ ] relevant Python/frontend/Compose gates pass;
- [ ] public English and Chinese documentation remain synchronized;
- [ ] `DOCUMENT_INDEX.md` is current.

## Reporting Security Issues

Do not publish exploitable details, credentials, or sensitive data in a public
issue. Contact the repository owner privately with a minimal reproduction,
affected versions, and impact. A dedicated security policy and private
reporting channel are planned but are not yet configured.

</details>
