# Contributing to OperCerta

**English** | [简体中文](CONTRIBUTING.zh-CN.md)

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

- Keep `README.md` and `README.zh-CN.md` structurally equivalent when public
  project behavior changes.
- Keep `CONTRIBUTING.md` and `CONTRIBUTING.zh-CN.md` equivalent when the
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
