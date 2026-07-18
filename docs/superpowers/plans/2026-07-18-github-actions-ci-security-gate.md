# OperCerta GitHub Actions CI Security Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 OperCerta 建立受测试保护的仓库安全扫描、Private GitHub remote、分层 GitHub Actions、PostgreSQL 18 完整回归、前端门禁、Compose 业务 smoke 与可复核远程证据。

**Architecture:** 使用一个只读权限的 `.github/workflows/ci.yml`，把快速门禁拆成四个独立 job，并只在 `main`/手动触发时追加 Compose smoke。仓库安全规则由标准库 Python CLI 执行并用单元测试锁定；真实 GitHub run 全绿后才启用主分支保护并生成证据。

**Tech Stack:** Python 3.12、uv `0.11.28`、pytest、Ruff、mypy、Node 24、npm、PostgreSQL 18 service container、Docker Compose、GitHub Actions、GitHub CLI/connector。

## Global Constraints

- 只实施 OperCerta；不修改或启动其他项目。
- GitHub 仓库初始必须为 Private；转 Public、删除远程、强制推送或改写历史需要新的明确授权。
- 执行实现时从 `main` 基线创建 `ci/github-actions-gate` 分支或等价隔离 worktree；不得直接在受保护的 `main` 上继续功能提交。
- 本地运行时代码回滚基线为 `f806138`；设计提交 `3058870` 及本计划属于文档历史。
- CI 不读取 `.env.local`、`.env.compose` 或任何真实凭据；PostgreSQL/JWT/Compose 只使用隔离 runner 内的合成值。
- 所有远程 Action 固定到本计划已核验的完整 40 位 commit SHA，不使用可变 tag。
- Action release tag 与 SHA：checkout `v7.0.0` / `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`；setup-python `v6.3.0` / `ece7cb06caefa5fff74198d8649806c4678c61a1`；setup-node `v7.0.0` / `820762786026740c76f36085b0efc47a31fe5020`；setup-uv `v8.3.2` / `11f9893b081a58869d3b5fccaea48c9e9e46f990`。
- `uv sync --frozen --all-groups`、`npm ci` 和 lockfile 是唯一安装路径；CI 不修改依赖锁。
- 所有 job 失败关闭，禁止 `continue-on-error`；顶层权限仅 `contents: read`。
- Private Actions badge 不写入 README；本阶段不加入 CodeQL、付费 GHAS、自动部署、Caddy 或 HTTPS。
- 发布门禁始终保持 `CLOSED`；任何测试数字只记录实际输出。

---

### Task 1: 受测试保护的仓库安全扫描器

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/verify_repository_safety.py`
- Create: `tests/unit/scripts/__init__.py`
- Create: `tests/unit/scripts/test_verify_repository_safety.py`

**Interfaces:**
- Consumes: Git tracked paths from `git ls-files -z` and UTF-8 tracked text.
- Produces: `tracked_paths(root: Path) -> tuple[Path, ...]`, `scan_repository(root: Path) -> tuple[str, ...]`, `main() -> int`.
- Exit contract: zero findings returns 0; any forbidden path, placeholder, credential pattern, unpinned Action, write permission or changed attack allowlist returns 1.

- [ ] **Step 1: 写安全扫描 RED 测试**

```python
# tests/unit/scripts/test_verify_repository_safety.py
import subprocess
from pathlib import Path

from scripts.verify_repository_safety import scan_repository

PINNED_CHECKOUT = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
ATTACK_PATH = "src/opercerta/evaluation/executor.py"
ATTACK_LINES = """\
def headers(token: str) -> dict[str, str]:
    if token == "tampered":
        return {"Authorization": f"Bearer x{token[1:]}"}
    return {"Authorization": "Bearer malformed-wrong-issuer-token"}
"""


def tracked_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    return tmp_path


def clean_files() -> dict[str, str]:
    return {
        "README.md": "# OperCerta\nOperCerta release gate: CLOSED\n",
        ATTACK_PATH: ATTACK_LINES,
        ".github/workflows/ci.yml": (
            "permissions:\n  contents: read\n"
            f"steps:\n  - uses: actions/checkout@{PINNED_CHECKOUT}\n"
        ),
    }


def test_clean_repository_and_exact_attack_allowlist_pass(tmp_path: Path) -> None:
    root = tracked_repo(tmp_path, clean_files())

    assert scan_repository(root) == ()


def test_forbidden_local_environment_file_fails(tmp_path: Path) -> None:
    files = clean_files() | {".env.local": "SECRET=value\n"}
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("forbidden tracked file: .env.local" in item for item in findings)


def test_unknown_credential_and_duplicate_attack_sample_fail(tmp_path: Path) -> None:
    files = clean_files()
    files["README.md"] += "Authorization example: Bearer actual-looking-token\n"
    files[ATTACK_PATH] += (
        'duplicate = {"Authorization": "Bearer malformed-wrong-issuer-token"}\n'
    )
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("credential-like content: README.md" in item for item in findings)
    assert any("attack allowlist count" in item for item in findings)


def test_unpinned_action_and_write_permission_fail(tmp_path: Path) -> None:
    files = clean_files()
    files[".github/workflows/ci.yml"] = """\
permissions: write-all
steps:
  - uses: actions/checkout@v7
"""
    root = tracked_repo(tmp_path, files)

    findings = scan_repository(root)

    assert any("unpinned action" in item for item in findings)
    assert any("write permission" in item for item in findings)
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/scripts/test_verify_repository_safety.py -q
```

Expected: collection exits 1 with `ModuleNotFoundError: No module named 'scripts.verify_repository_safety'`.

- [ ] **Step 3: 实现最小扫描器**

```python
# scripts/verify_repository_safety.py
"""Fail closed on tracked local secrets, placeholders and mutable Actions."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

_ALLOWED_ENV_NAMES = {".env.example", ".env.compose.example"}
_FORBIDDEN_SUFFIXES = {".pem", ".key"}
_PLACEHOLDER = re.compile(r"T[B]D|T[O]DO|稍后填[写]|待[定]|暂[定]")
_CREDENTIALS = (
    re.compile(r"Bearer [A-Za-z0-9._-]+"),
    re.compile(r"postgresql[^\s]*://[^\s:]+:[^\s@]+@"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}"),
)
_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)", re.MULTILINE)
_PINNED_ACTION = re.compile(r"^[^@]+@[0-9a-f]{40}$")
_WRITE_PERMISSION = re.compile(
    r"^\s*(?:permissions:\s*write-all|[A-Za-z_-]+:\s*write)\s*$",
    re.MULTILINE,
)
_ATTACK_PATH = "src/opercerta/evaluation/executor.py"
_ALLOWED_ATTACK_LINES = {
    'return {"Authorization": f"Bearer x{token[1:]}"}',
    'return {"Authorization": "Bearer malformed-wrong-issuer-token"}',
}


def tracked_paths(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(Path(item) for item in result.stdout.split("\0") if item)


def _is_forbidden_path(path: Path) -> bool:
    name = path.name
    return (
        (name.startswith(".env") and name not in _ALLOWED_ENV_NAMES)
        or path.suffix.lower() in _FORBIDDEN_SUFFIXES
    )


def _is_content_scope(relative: str) -> bool:
    return (
        relative in {"README.md", "IMPLEMENTATION_HANDOFF.md", "DOCUMENT_INDEX.md"}
        or relative == "docs/development-log/current-state.md"
        or relative.startswith("docs/release-evidence/")
        or relative.startswith("src/")
        or relative.startswith(".github/workflows/")
    )


def scan_repository(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    paths = tracked_paths(root)
    relative_names = {path.as_posix() for path in paths}
    attack_counts: Counter[str] = Counter()

    for path in paths:
        relative = path.as_posix()
        if _is_forbidden_path(path):
            findings.append(f"forbidden tracked file: {relative}")
        if not _is_content_scope(relative):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF-8 scoped file: {relative}")
            continue

        if _PLACEHOLDER.search(text):
            findings.append(f"placeholder content: {relative}")

        for line in text.splitlines():
            stripped = line.strip()
            if relative == _ATTACK_PATH and stripped in _ALLOWED_ATTACK_LINES:
                attack_counts[stripped] += 1
                continue
            if any(pattern.search(line) for pattern in _CREDENTIALS):
                findings.append(f"credential-like content: {relative}")

        if relative.startswith(".github/workflows/"):
            for action in _USES.findall(text):
                if action.startswith("./"):
                    continue
                if not _PINNED_ACTION.fullmatch(action):
                    findings.append(f"unpinned action: {relative}: {action}")
            if _WRITE_PERMISSION.search(text):
                findings.append(f"write permission: {relative}")

    if _ATTACK_PATH in relative_names:
        for allowed_line in sorted(_ALLOWED_ATTACK_LINES):
            if attack_counts[allowed_line] != 1:
                findings.append(
                    "attack allowlist count: "
                    f"{_ATTACK_PATH}: expected 1, observed {attack_counts[allowed_line]}"
                )

    return tuple(findings)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_repository(root)
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("repository safety checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create empty `scripts/__init__.py` and `tests/unit/scripts/__init__.py`.

- [ ] **Step 4: 运行 GREEN、真实仓库扫描和静态检查**

Run:

```powershell
uv run pytest tests/unit/scripts/test_verify_repository_safety.py -q
```

Expected: `4 passed`.

Run:

```powershell
uv run python scripts/verify_repository_safety.py
```

Expected: exit 0 and `repository safety checks passed`.

Run:

```powershell
uv run ruff check scripts tests/unit/scripts
uv run ruff format --check scripts tests/unit/scripts
```

Expected: both exit 0.

- [ ] **Step 5: 提交扫描器**

```powershell
git add scripts/__init__.py scripts/verify_repository_safety.py tests/unit/scripts
git commit -m "feat: verify repository safety"
```

---

### Task 2: Pull Request 快速 GitHub Actions 门禁

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/unit/runtime/test_ci_assets.py`

**Interfaces:**
- Consumes: Task 1 CLI, `uv.lock`, `web/package-lock.json`, PostgreSQL 18 and existing pytest fixtures.
- Produces: stable job/check names `repository-safety`, `python-quality`, `backend-tests`, `frontend`.

- [ ] **Step 1: 写快速 workflow 契约 RED 测试**

```python
# tests/unit/runtime/test_ci_assets.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

ACTION_PINS = {
    "actions/checkout": "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "astral-sh/setup-uv": "11f9893b081a58869d3b5fccaea48c9e9e46f990",
}


def workflow_text() -> str:
    assert WORKFLOW.is_file(), "GitHub Actions workflow is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_has_read_only_triggers_concurrency_and_pinned_actions() -> None:
    text = workflow_text()

    assert "pull_request:" in text
    assert "workflow_dispatch:" in text
    assert "branches: [main]" in text
    assert "contents: read" in text
    assert "cancel-in-progress: true" in text
    assert "write-all" not in text
    for owner_action, sha in ACTION_PINS.items():
        assert f"{owner_action}@{sha}" in text


def test_ci_fast_jobs_use_frozen_python_postgres_and_frontend_gates() -> None:
    text = workflow_text()

    for job_name in (
        "repository-safety",
        "python-quality",
        "backend-tests",
        "frontend",
    ):
        assert f"name: {job_name}" in text
    assert "python-version: \"3.12\"" in text
    assert "version: \"0.11.28\"" in text
    assert "uv sync --frozen --all-groups" in text
    assert "uv run python scripts/verify_repository_safety.py" in text
    assert "uv run ruff check ." in text
    assert "uv run ruff format --check ." in text
    assert "uv run mypy src" in text
    assert "image: postgres:18" in text
    assert "OPERCERTA_DATABASE_URL: postgresql+psycopg://opercerta_ci@127.0.0.1:5432/opercerta_ci" in text
    assert "PGPASSWORD: opercerta_ci_only" in text
    assert "uv run pytest -q" in text
    assert "node-version: \"24\"" in text
    assert "npm ci" in text
    assert "npm run test:run" in text
    assert "npm run build" in text
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/runtime/test_ci_assets.py -q
```

Expected: both tests fail with `GitHub Actions workflow is missing`.

- [ ] **Step 3: 实现四个快速 job**

```yaml
# .github/workflows/ci.yml
name: OperCerta CI

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  repository-safety:
    name: repository-safety
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
      - name: Set up Python
        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.12"
      - name: Verify repository safety
        run: python scripts/verify_repository_safety.py

  python-quality:
    name: python-quality
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
      - name: Set up Python
        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.12"
      - name: Set up uv
        uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "0.11.28"
          enable-cache: true
          cache-dependency-glob: uv.lock
      - name: Install frozen Python dependencies
        run: uv sync --frozen --all-groups
      - name: Run Ruff
        run: uv run ruff check .
      - name: Check Ruff formatting
        run: uv run ruff format --check .
      - name: Run mypy
        run: uv run mypy src

  backend-tests:
    name: backend-tests
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: opercerta_ci
          POSTGRES_PASSWORD: opercerta_ci_only
          POSTGRES_DB: opercerta_ci
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U opercerta_ci -d opercerta_ci"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 20
    env:
      OPERCERTA_DATABASE_URL: postgresql+psycopg://opercerta_ci@127.0.0.1:5432/opercerta_ci
      PGPASSWORD: opercerta_ci_only
      LANGGRAPH_STRICT_MSGPACK: "true"
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
      - name: Set up Python
        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.12"
      - name: Set up uv
        uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          version: "0.11.28"
          enable-cache: true
          cache-dependency-glob: uv.lock
      - name: Install frozen Python dependencies
        run: uv sync --frozen --all-groups
      - name: Run complete backend tests
        run: uv run pytest -q

  frontend:
    name: frontend
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    defaults:
      run:
        working-directory: web
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
      - name: Set up Node
        uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install frozen frontend dependencies
        run: npm ci
      - name: Run frontend tests
        run: npm run test:run
      - name: Build frontend
        run: npm run build
```

- [ ] **Step 4: 运行 GREEN 与扫描器回归**

Run:

```powershell
uv run pytest tests/unit/runtime/test_ci_assets.py tests/unit/scripts/test_verify_repository_safety.py -q
```

Expected: `6 passed`.

Run:

```powershell
uv run python scripts/verify_repository_safety.py
```

Expected: exit 0.

Run:

```powershell
uv run ruff check .github scripts tests/unit
uv run ruff format --check scripts tests/unit
```

Expected: both exit 0.

- [ ] **Step 5: 提交快速门禁**

```powershell
git add .github/workflows/ci.yml tests/unit/runtime/test_ci_assets.py
git commit -m "ci: add fast github actions gates"
```

---

### Task 3: `main`/手动 Compose 业务 smoke 与本地总门禁

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/unit/runtime/test_ci_assets.py`

**Interfaces:**
- Consumes: Task 2 four fast jobs and `scripts/verify_compose.py`.
- Produces: stable job/check name `compose-smoke`, safe failure diagnostics and unconditional cleanup.

- [ ] **Step 1: 写 Compose workflow RED 测试**

Append:

```python
# tests/unit/runtime/test_ci_assets.py
def test_ci_compose_smoke_is_main_or_manual_only_and_always_cleans_up() -> None:
    text = workflow_text()

    assert "name: compose-smoke" in text
    assert "needs: [repository-safety, python-quality, backend-tests, frontend]" in text
    assert "github.event_name == 'workflow_dispatch'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "docker compose up --build -d" in text
    assert "python scripts/verify_compose.py" in text
    assert "docker compose restart api mcp" in text
    assert "python scripts/verify_compose.py --recovery-only" in text
    assert "if: failure()" in text
    assert "docker compose ps" in text
    assert "if: always()" in text
    assert "docker compose down -v --remove-orphans" in text
```

- [ ] **Step 2: 运行 RED**

Run:

```powershell
uv run pytest tests/unit/runtime/test_ci_assets.py::test_ci_compose_smoke_is_main_or_manual_only_and_always_cleans_up -q
```

Expected: fail because `compose-smoke` is absent.

- [ ] **Step 3: 在 workflow 末尾增加 Compose job**

```yaml
  compose-smoke:
    name: compose-smoke
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'push' && github.ref == 'refs/heads/main')
    needs: [repository-safety, python-quality, backend-tests, frontend]
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - name: Check out repository
        uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
      - name: Set up Python
        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0
        with:
          python-version: "3.12"
      - name: Create isolated Compose environment
        shell: bash
        run: |
          cp .env.compose.example .env.compose
          sed -i 's/CHANGE_ME_DEVELOPMENT_ONLY/ci-only-signing-key-at-least-32-bytes/' .env.compose
          sed -i 's/CHANGE_ME/ci-only-database-password/' .env.compose
      - name: Build and start Compose services
        run: docker compose up --build -d
      - name: Verify replenishment smoke
        run: python scripts/verify_compose.py
      - name: Restart API and MCP
        run: docker compose restart api mcp
      - name: Verify health after restart
        run: python scripts/verify_compose.py --recovery-only
      - name: Show safe Compose status on failure
        if: failure()
        run: docker compose ps
      - name: Remove Compose services and volumes
        if: always()
        run: docker compose down -v --remove-orphans
```

- [ ] **Step 4: 运行 GREEN、完整本地后端与前端门禁**

Run:

```powershell
uv run pytest tests/unit/runtime/test_ci_assets.py tests/unit/scripts/test_verify_repository_safety.py -q
```

Expected: `7 passed`.

Run from repository root:

```powershell
uv run python scripts/verify_repository_safety.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Expected: all exit 0; record actual counts instead of reusing earlier `332`/`100`/`50` values.

Run from `web/`:

```powershell
npm ci
npm run test:run
npm run build
```

Expected: all exit 0; record actual test file/test counts and build result.

- [ ] **Step 5: 提交 Compose 门禁**

```powershell
git add .github/workflows/ci.yml tests/unit/runtime/test_ci_assets.py
git commit -m "ci: verify compose on main"
```

---

### Task 4: 创建 Private GitHub remote、PR 与真实 Actions run

**Files:**
- No repository file change required unless real Actions diagnostics prove a workflow defect.

**Interfaces:**
- Consumes: authenticated GitHub connector or `gh`, clean `ci/github-actions-gate` branch and Tasks 1–3 commits.
- Produces: Private `opercerta` repository, configured `origin`, initial PR run and merged `main` run.

- [ ] **Step 1: 核验 GitHub 身份并设置人工确认点**

Run:

```powershell
gh auth status
gh api user --jq .login
```

Expected: authenticated account login is printed without token. Show that login to the user and obtain explicit confirmation that it is the intended owner before creating the repository. If `gh` is unavailable, use the installed GitHub connector; if neither is authenticated, stop and ask the user to complete GitHub authentication.

- [ ] **Step 2: 核验本地分支、工作区与远程名称可用性**

Run:

```powershell
git branch --show-current
git status --short
git remote -v
```

Expected: current branch is `ci/github-actions-gate` (or the isolated execution branch), worktree is clean, and no `origin` exists.

Resolve owner from the authenticated account and check whether the target already exists:

```powershell
$owner = gh api user --jq .login
gh repo view "$owner/opercerta" --json nameWithOwner,visibility,url
```

Expected for a new repository: exit 1/not found. If it exists, stop; do not overwrite or reuse it without user direction.

- [ ] **Step 3: 创建 Private 仓库并验证可见性**

```powershell
$owner = gh api user --jq .login
gh repo create "$owner/opercerta" --private --description "Controlled, auditable operations workflow agent"
gh repo view "$owner/opercerta" --json nameWithOwner,visibility,url
```

Expected: JSON reports the confirmed owner, repository `opercerta`, and `visibility: PRIVATE`.

- [ ] **Step 4: 配置 origin，先推 main 基线，再推 CI 分支并创建 PR**

```powershell
$owner = gh api user --jq .login
git remote add origin "https://github.com/$owner/opercerta.git"
git push -u origin main
git push -u origin HEAD
gh pr create --base main --head (git branch --show-current) --title "ci: add github actions security gate" --body "Adds pinned, read-only Python, PostgreSQL, frontend, repository-safety and Compose CI gates. Release gate remains CLOSED."
```

Expected: both branches push without force, and one open PR targets `main`.

- [ ] **Step 5: 观察 PR 快速门禁，失败时按证据修复**

```powershell
$commit = git rev-parse HEAD
$deadline = (Get-Date).AddMinutes(2)
do {
    $runId = gh run list --workflow ci.yml --commit $commit --limit 1 --json databaseId --jq '.[0].databaseId'
    if ($runId) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not $runId) { throw "GitHub Actions run was not created before the deadline" }
gh run watch $runId --exit-status
gh run view $runId --json headSha,event,status,conclusion,jobs,url
```

Expected: `repository-safety`、`python-quality`、`backend-tests`、`frontend` success；`compose-smoke` skipped on PR. If any job fails, inspect only that job with `gh run view $runId --log-failed`, identify the root cause, add or tighten a local regression test, commit the fix, push normally and repeat this step. Do not use `continue-on-error`, remove assertions or expose environment variables.

- [ ] **Step 6: 合并 PR 并观察 main 的全部五个 job**

```powershell
gh pr merge --merge --delete-branch=false
git switch main
git pull --ff-only
$commit = git rev-parse HEAD
$deadline = (Get-Date).AddMinutes(2)
do {
    $runId = gh run list --workflow ci.yml --commit $commit --limit 1 --json databaseId --jq '.[0].databaseId'
    if ($runId) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)
if (-not $runId) { throw "GitHub Actions main run was not created before the deadline" }
gh run watch $runId --exit-status
gh run view $runId --json headSha,event,status,conclusion,jobs,url
```

Expected: main run has all five jobs success, including `compose-smoke`; commit SHA and run URL are retained for Task 6 evidence.

---

### Task 5: `main` 分支保护或真实能力限制

**Files:**
- No repository file change unless the GitHub capability limitation must be recorded later in Task 6.

**Interfaces:**
- Consumes: Task 4 successful main run and authenticated owner.
- Produces: verified branch protection requiring the four fast checks, or an evidence-backed account limitation.

- [ ] **Step 1: 读取当前 protection 状态**

```powershell
$owner = gh api user --jq .login
gh api "repos/$owner/opercerta/branches/main/protection"
```

Expected before configuration: 404/unprotected or existing settings that must be shown to the user before modification. Never overwrite unexpected existing protection silently.

- [ ] **Step 2: 启用不要求外部 reviewer 的 protection**

Run in PowerShell with the confirmed owner:

```powershell
$owner = gh api user --jq .login
$payload = @'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "repository-safety",
      "python-quality",
      "backend-tests",
      "frontend"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
'@
$payload | gh api --method PUT "repos/$owner/opercerta/branches/main/protection" --input -
```

Expected: success JSON. If GitHub returns a plan/capability error, do not retry by weakening repository visibility or purchasing a plan; capture the status/code for Task 6 and use the documented manual rule.

- [ ] **Step 3: 回读并验证保护事实**

```powershell
$owner = gh api user --jq .login
gh api "repos/$owner/opercerta/branches/main/protection" --jq '{checks: .required_status_checks.contexts, enforce_admins: .enforce_admins.enabled, force_push: .allow_force_pushes.enabled, deletion: .allow_deletions.enabled}'
```

Expected if supported: four exact fast contexts; `enforce_admins: true`、`force_push: false`、`deletion: false`. `compose-smoke` is not a PR-required check because it intentionally skips PR events.

---

### Task 6: 远程 CI 证据、索引、交接与最终门禁

**Files:**
- Create: `docs/release-evidence/github-actions-ci.md`
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-18.md`
- Modify: `docs/superpowers/plans/2026-07-18-github-actions-ci-security-gate.md`

**Interfaces:**
- Consumes: actual PR/main run JSON, current Git commit, repository visibility and protection response.
- Produces: Chinese evidence with observed facts only and a clean local `main` tracking `origin/main`.

- [ ] **Step 1: 采集远程只读事实，不采集 token**

Run:

```powershell
$owner = gh api user --jq .login
$commit = git rev-parse HEAD
gh repo view "$owner/opercerta" --json nameWithOwner,visibility,url,defaultBranchRef
gh run list --workflow ci.yml --branch main --limit 3 --json databaseId,headSha,event,status,conclusion,url,createdAt
git status --short
git branch -vv
```

Expected: Private repository, default branch `main`, successful current main run, clean worktree and local main tracking origin/main. Record only the actual returned run ID/SHA/event/conclusion/URL.

- [ ] **Step 2: 写中文远程 CI 证据**

Create `docs/release-evidence/github-actions-ci.md` with exactly these sections and only observed values from Step 1 and Tasks 4–5:

```markdown
# GitHub Actions 分层 CI：远程验证证据

## 范围与仓库可见性
记录实际 Private owner/repository、default branch 和验证时间；不记录认证方式或 token。

## PR 快速门禁
记录实际 PR run ID、commit SHA、URL，以及 repository-safety、python-quality、backend-tests、frontend 的真实结论；说明 compose-smoke 在 PR 按设计 skipped。

## main 完整门禁
记录实际 main run ID、commit SHA、URL、五个 job 的真实结论和日志中实际测试数字；不得沿用本地数字。

## 供应链与凭据边界
记录四个 Action 的完整 SHA、只读权限、冻结安装、合成 CI 凭据、无密码数据库 URL 和安全扫描 allowlist 边界。

## 主分支保护
记录 protection 回读的真实结果；如果账号能力不支持，记录实际错误与人工替代规则，不写成已启用。

## 已知限制
明确未实现 CodeQL/GHAS、漏洞扫描、自动部署、Caddy/HTTPS、生产 IAM 或公开仓库，release gate 为 CLOSED。
```

- [ ] **Step 3: 同步 README、索引、当前状态、交接和日志**

Only state facts proven by remote output:

- Private GitHub remote exists and `origin` is configured.
- Exact remote CI jobs and run IDs that passed.
- Compose smoke/restart result from main, if success.
- Branch protection actual state or capability limitation.
- No public deployment or Public repository; release gate remains `CLOSED`.
- Next boundary is Caddy/HTTPS design or production identity/handoff, requiring a separate decision.

Mark completed plan checkboxes `- [x]` without deleting RED/GREEN commands or failure diagnostics.

- [ ] **Step 4: 运行最终本地门禁与敏感扫描**

Run from repository root:

```powershell
uv run python scripts/verify_repository_safety.py
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Run from `web/`:

```powershell
npm run test:run
npm run build
```

Expected: all exit 0; evidence records the fresh actual counts.

Run:

```powershell
git diff --check
git status --short
```

Expected: diff check exits 0; only the planned documentation files are modified.

- [ ] **Step 5: 提交证据并推送受保护 main**

Because Task 5 may now protect `main`, create a documentation branch if direct push is rejected:

```powershell
git switch -c docs/github-actions-ci-evidence
git add README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs
git commit -m "docs: record github actions ci evidence"
git push -u origin docs/github-actions-ci-evidence
gh pr create --base main --head docs/github-actions-ci-evidence --title "docs: record github actions ci evidence" --body "Records observed Private GitHub Actions results and keeps the release gate CLOSED."
```

Expected: PR checks pass. Merge with `gh pr merge --merge --delete-branch=false`, then `git switch main` and `git pull --ff-only`. If protection was unavailable and direct main workflow is still used, commit normally but never force push.

After the evidence PR merge, use the same bounded run lookup from Task 4 Step 6 for the new `main` commit and run `gh run watch $runId --exit-status`. Final completion requires all five jobs on that current `main` commit to succeed.

## Self-Review Mapping

- 规格第 3 节官方版本与 SHA：Global Constraints、Tasks 1–3。
- 规格第 4 节触发、并发、最小权限：Task 2。
- 规格第 5.1 节仓库安全与精确 allowlist：Task 1。
- 规格第 5.2–5.4 节 Python/PostgreSQL/前端：Task 2。
- 规格第 5.5 节 Compose 业务与重启：Task 3、Task 4 main run。
- 规格第 6–7 节失败、超时、证据、缓存与供应链：Tasks 1–4、Task 6。
- 规格第 8 节 Private remote 与保护：Tasks 4–5。
- 规格第 9 节 TDD 和文件边界：Tasks 1–3、Task 6。
- 规格第 10–11 节完成与回滚：Tasks 4–6、Global Constraints。

计划没有部署、Public 转换、CodeQL/GHAS、Caddy/HTTPS、生产 IAM、远程删除、force push 或其他项目任务。
