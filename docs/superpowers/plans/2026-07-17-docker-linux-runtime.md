# Docker/Linux Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Hyper-V 承载的 Ubuntu 24.04 LTS VM 中，以 Docker Compose 可重复启动当前库存补货后端，并提供安全 liveness/readiness 和真实闭环证据。

**Architecture:** 单一非 root Python 3.12 镜像提供 API、MCP 与一次性 bootstrap 命令。Compose 编排 `postgres`、`bootstrap`、`mcp`、`api`；bootstrap 是唯一执行 Alembic 迁移和 LangGraph checkpointer 初始化的服务，API/MCP 只能在它成功后启动且不能隐式改写 Schema。

**Tech Stack:** Python 3.12、FastAPI 0.139.0、Uvicorn 0.51.0、MCP 1.28.1、PostgreSQL 18、Psycopg 3.3.4、SQLAlchemy 2.0.51、Alembic 1.18.5、Docker Engine、Docker Compose。

## Global Constraints

- 只实施 OperCerta；不得复用旧公司材料、不得虚构指标，`OperCerta release gate: CLOSED` 保持不变。
- 当前 Windows 10 LTSC 2021 build 19044.5011 不安装不受支持的 Docker Desktop；真实容器验收只在 Hyper-V 中的 Ubuntu 24.04 LTS VM 进行。
- 严格使用现有 `uv.lock` 的 `uv sync --frozen --no-dev`；不升级或新增 Python 依赖。
- 容器使用非 root 用户；不得使用 privileged、Docker socket、主机目录挂载或暴露 PostgreSQL/MCP 端口。
- `.env.compose` 不入库、不进日志、不进测试快照；只跟踪安全示例 `.env.compose.example`。
- `/health/live` 只证明进程可路由；readiness 不得泄露 URL、密码、异常文本或 traceback。
- 本阶段不实现 Redis、React、SSE、JWT/RBAC、设备场景、真实模型、Caddy、Prometheus、CI/CD 或公开部署。

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/opercerta/api/health.py` | API readiness 模型、协议与生产探针 |
| `src/opercerta/api/app.py` | 注入 readiness 并注册 API 健康端点 |
| `src/opercerta/tools/app.py` | MCP ASGI 包装层和内部健康端点 |
| `src/opercerta/runtime/{api,mcp,bootstrap}.py` | 三个容器入口；迁移/初始化只在 bootstrap |
| `tests/integration/api/test_health_api.py` | API liveness/readiness 契约 |
| `tests/integration/mcp/test_mcp_health.py` | MCP 健康端点与 `/mcp` 共存契约 |
| `Dockerfile`, `.dockerignore`, `compose.yaml` | 非 root 镜像与四服务编排 |
| `.env.compose.example`, `.gitignore` | 配置秘密边界 |
| `tests/unit/runtime/test_container_assets.py` | Docker/Compose 安全静态断言 |
| `scripts/verify_compose.py` | 真实 API→MCP→PostgreSQL smoke test |
| `docs/release-evidence/docker-linux-runtime.md` | Ubuntu VM 验收事实、范围与回滚点 |

---

### Task 0: 准备 Ubuntu Docker 运行环境（用户操作）

**Files:**
- Modify: `docs/development-log/daily/2026-07-17.md`

**Produces:** 可记录版本与命令输出的 Ubuntu 24.04 LTS VM；尚不声明容器运行成功。

- [ ] **Step 1: 以管理员 PowerShell 启用 Hyper-V 并重启 Windows**

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
Restart-Computer
```

- [ ] **Step 2: 重启后确认 Windows 功能状态**

Run: `Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V | Select-Object FeatureName, State`

Expected: `State` 为 `Enabled`。

- [ ] **Step 3: 在 Hyper-V 创建 Ubuntu 24.04 LTS VM，并按 Docker 官方 Ubuntu 文档安装 Engine、Buildx 与 Compose plugin**

Run: `sudo docker run --rm hello-world && docker compose version && docker buildx version`

Expected: `hello-world` 成功；记录 Ubuntu、Engine、Compose、Buildx 版本，但不记录秘密。

- [ ] **Step 4: 创建本地 Compose 密钥文件并限制权限**

```bash
cp .env.compose.example .env.compose
chmod 600 .env.compose
```

- [ ] **Step 5: 在每日日志记录观测事实，不提交 `.env.compose`**

Run: `git status --short`

Expected: `.env.compose` 不显示；日志只记录 VM 资源实测值、版本和命令结果。

### Task 1: API liveness/readiness 契约

**Files:**
- Create: `src/opercerta/api/health.py`
- Modify: `src/opercerta/api/app.py`
- Create: `tests/integration/api/test_health_api.py`

**Interfaces:**
- Produces: `ReadinessProbe` protocol：`async def check(self) -> ReadinessReport`。
- Produces: `ReadinessReport(status: Literal["ready", "not_ready"], dependencies: dict[DependencyName, DependencyState])`。

- [ ] **Step 1: 写 API 健康端点的失败测试**

```python
class ExplodingProbe:
    async def check(self) -> ReadinessReport:
        raise RuntimeError("secret must never reach response")

async def test_live_is_200_when_dependencies_fail(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}

async def test_ready_returns_safe_503(client_with_exploding_probe: AsyncClient) -> None:
    response = await client_with_exploding_probe.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "secret" not in response.text
```

- [ ] **Step 2: 运行失败测试**

Run: `uv run pytest tests/integration/api/test_health_api.py -v`

Expected: FAIL，因为路由或依赖注入尚不存在。

- [ ] **Step 3: 实现最小健康模型与端点**

```python
DependencyName = Literal["database", "checkpoint", "mcp"]
DependencyState = Literal["ready", "unavailable"]

class ReadinessProbe(Protocol):
    async def check(self) -> ReadinessReport: ...

@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "live"}

@app.get("/health/ready")
async def ready() -> JSONResponse:
    try:
        report = await runtime.readiness.check()
    except Exception:
        report = not_ready_report()
    return JSONResponse(report.model_dump(), status_code=200 if report.status == "ready" else 503)
```

`AppRuntime` 增加 `readiness` 字段；现有测试构造点注入稳定的假探针，生产构造点将在 Task 2 注入真实探针。

- [ ] **Step 4: 运行健康与既有 API 测试**

Run: `uv run pytest tests/integration/api/test_health_api.py tests/integration/api -v`

Expected: PASS；既有 operation、binding、approval API 无行为变化。

- [ ] **Step 5: 提交原子检查点**

```bash
git add src/opercerta/api/health.py src/opercerta/api/app.py tests/integration/api/test_health_api.py
git commit -m "feat: add api health contracts"
```

### Task 2: 生产 readiness、MCP 健康包装和容器入口

**Files:**
- Modify: `src/opercerta/api/health.py`
- Create: `src/opercerta/tools/app.py`
- Create: `src/opercerta/runtime/__init__.py`
- Create: `src/opercerta/runtime/api.py`
- Create: `src/opercerta/runtime/mcp.py`
- Create: `src/opercerta/runtime/bootstrap.py`
- Create: `tests/integration/mcp/test_mcp_health.py`
- Modify: `tests/integration/api/test_health_api.py`

**Interfaces:**
- Consumes: Task 1 `ReadinessProbe` 和 `ReadinessReport`。
- Produces: `ProductionReadinessProbe(engine, database_url, mcp_health_url)` 与 `create_mcp_app(catalog, engine, clock)`。

- [ ] **Step 1: 写真实探针和 MCP 路由共存的失败测试**

```python
async def test_mcp_health_routes_do_not_replace_mcp_tools(client: AsyncClient) -> None:
    assert (await client.get("/health/live")).json() == {"status": "live"}
    assert (await client.get("/health/ready")).status_code == 200
    tools = await list_tools_over_streamable_http(client, path="/mcp")
    assert {tool.name for tool in tools} == EXPECTED_INVENTORY_TOOL_NAMES

async def test_probe_maps_mcp_failure_to_safe_state(probe: ProductionReadinessProbe) -> None:
    report = await probe.check()
    assert report.status == "not_ready"
    assert report.dependencies["mcp"] == "unavailable"
```

- [ ] **Step 2: 运行失败测试**

Run: `uv run pytest tests/integration/mcp/test_mcp_health.py tests/integration/api/test_health_api.py -v`

Expected: FAIL，因为 MCP ASGI 包装层和生产探针尚不存在。

- [ ] **Step 3: 实现生产探针与 MCP 包装层**

```python
async def check(self) -> ReadinessReport:
    states = {"database": "unavailable", "checkpoint": "unavailable", "mcp": "unavailable"}
    try:
        with self._engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        states["database"] = "ready"
    except Exception:
        return report_for(states)
    try:
        with open_checkpointer(self._database_url, setup=False):
            pass
        states["checkpoint"] = "ready"
    except Exception:
        return report_for(states)
    try:
        response = await self._http_client.get(self._mcp_health_url)
        response.raise_for_status()
        states["mcp"] = "ready"
    except Exception:
        return report_for(states)
    return ready_report(states)
```

`create_mcp_app` 在 FastAPI 上注册两个健康路由，再将现有 `build_mcp_server(...).streamable_http_app()` 挂载在 `/mcp`；MCP readiness 仅执行数据库 `SELECT 1`。

- [ ] **Step 4: 实现三个入口的明确职责**

```python
# runtime/api.py
uvicorn.run(create_production_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

# runtime/mcp.py
app = create_mcp_app(catalog=load_catalog(), engine=create_engine_from_settings(), clock=system_clock)

# runtime/bootstrap.py
command.upgrade(alembic_config(), "head")
with open_checkpointer(settings.database_url, setup=True):
    pass
```

API 与 MCP 入口都不调用 `command.upgrade` 或 `setup=True`；bootstrap 复用现有迁移、SecretStr 与临时 `PGPASSWORD` 边界。

- [ ] **Step 5: 运行聚焦测试与静态检查**

Run: `uv run pytest tests/integration/api/test_health_api.py tests/integration/mcp/test_mcp_health.py -v`

Expected: PASS，四个 MCP 工具名和 `/mcp` 契约不变。

Run: `uv run ruff check src tests && uv run mypy src`

Expected: PASS。

- [ ] **Step 6: 提交原子检查点**

```bash
git add src/opercerta/api src/opercerta/tools/app.py src/opercerta/runtime tests/integration/api/test_health_api.py tests/integration/mcp/test_mcp_health.py
git commit -m "feat: add runtime health and entrypoints"
```

### Task 3: 非 root Docker 镜像与 Compose 安全编排

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.env.compose.example`
- Modify: `.gitignore`
- Create: `tests/unit/runtime/test_container_assets.py`

**Interfaces:**
- Consumes: Task 2 的 `python -m opercerta.runtime.{bootstrap,mcp,api}`。
- Produces: 仅 API 可被 VM 局域网访问的四服务 Compose 配置。

- [ ] **Step 1: 写 Docker 与 Compose 静态失败测试**

```python
def test_compose_has_only_required_services_and_no_internal_host_ports() -> None:
    compose = Path("compose.yaml").read_text(encoding="utf-8")
    assert all(name in compose for name in ("postgres:", "bootstrap:", "mcp:", "api:"))
    assert "privileged:" not in compose
    assert "docker.sock" not in compose
    assert "postgres:5432" not in compose

def test_image_uses_non_root_and_locked_dependencies() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER opercerta" in dockerfile
```

- [ ] **Step 2: 运行失败测试**

Run: `uv run pytest tests/unit/runtime/test_container_assets.py -v`

Expected: FAIL，因为镜像与 Compose 文件尚不存在。

- [ ] **Step 3: 编写最小非 root Dockerfile 和忽略规则**

```dockerfile
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN groupadd --gid 10001 opercerta && useradd --uid 10001 --gid 10001 --create-home opercerta
USER opercerta
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src
```

`.dockerignore` 排除 `.git`、`.env*`、`.venv`、`__pycache__`、`.pytest_cache`、`tests` 和本地日志。

- [ ] **Step 4: 编写四服务 Compose 编排**

```yaml
services:
  postgres:
    image: postgres:18
    env_file: .env.compose
    volumes: [postgres_data:/var/lib/postgresql/data]
  bootstrap:
    build: .
    env_file: .env.compose
    command: ["python", "-m", "opercerta.runtime.bootstrap"]
    depends_on:
      postgres: {condition: service_healthy}
  mcp:
    build: .
    env_file: .env.compose
    command: ["python", "-m", "opercerta.runtime.mcp"]
    depends_on:
      bootstrap: {condition: service_completed_successfully}
  api:
    build: .
    env_file: .env.compose
    command: ["python", "-m", "opercerta.runtime.api"]
    ports: ["${OPERCERTA_API_BIND:-127.0.0.1}:${PORT:-8080}:8080"]
    depends_on:
      bootstrap: {condition: service_completed_successfully}
volumes:
  postgres_data:
```

补全 PostgreSQL、MCP、API healthcheck；MCP 和 PostgreSQL 都不写 `ports`，API 不得以 `0.0.0.0` 为主机发布默认值。示例变量只给安全占位值，真实 `.env.compose` 只在用户本机。

- [ ] **Step 5: 运行静态配置测试与 Compose 语法校验**

Run: `uv run pytest tests/unit/runtime/test_container_assets.py -v`

Expected: PASS。

Run: `docker compose config -q`

Expected: 仅在 Ubuntu VM 的 `.env.compose` 已配置后 PASS。

- [ ] **Step 6: 提交原子检查点**

```bash
git add Dockerfile .dockerignore compose.yaml .env.compose.example .gitignore tests/unit/runtime/test_container_assets.py
git commit -m "feat: containerize replenishment runtime"
```

### Task 4: Ubuntu Compose 验收、重启恢复和证据归档

**Files:**
- Create: `scripts/verify_compose.py`
- Create: `docs/release-evidence/docker-linux-runtime.md`
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-17.md`

**Interfaces:**
- Consumes: Tasks 1–3 的健康端点、业务 API、MCP 与 Compose 网络。
- Produces: 已验证的单节点 Ubuntu Compose 事实；不改变发布门禁。

- [ ] **Step 1: 写 smoke 脚本的失败测试**

```python
def test_smoke_script_checks_health_duplicate_approval_and_database_facts() -> None:
    script = Path("scripts/verify_compose.py").read_text(encoding="utf-8")
    for required in ("/health/live", "/health/ready", "approval_already_decided", "docker compose exec -T postgres"):
        assert required in script
    assert "OPERCERTA_DATABASE_URL" not in script
```

- [ ] **Step 2: 运行失败测试**

Run: `uv run pytest tests/unit/runtime/test_container_assets.py -v`

Expected: FAIL，因为 smoke 脚本断言尚未满足。

- [ ] **Step 3: 实现不泄露秘密的 smoke 脚本**

```python
assert get_json("/health/live") == {"status": "live"}
assert get_json("/health/ready")["status"] == "ready"
operation_id = create_low_inventory_operation()
assert get_binding(operation_id)["operation_id"] == operation_id
assert approve(operation_id).status_code == 200
duplicate = approve(operation_id)
assert duplicate.status_code == 409
assert duplicate.json()["detail"]["code"] == "approval_already_decided"
assert postgres_counts(operation_id) == {"approvals": 1, "work_orders": 1}
assert audit_events(operation_id)[-1] == "work_order_completed"
```

数据库查询仅通过 `docker compose exec -T postgres`，读取 `.env.compose` 的变量名而不打印值；失败时输出 HTTP 状态、容器状态、脱敏日志摘要和退出码。

- [ ] **Step 4: 在 Ubuntu VM 进行第一次真实验收**

```bash
git rev-parse --short HEAD
docker version --format '{{.Server.Version}}'
docker compose version
docker buildx version
docker compose config -q
docker compose build --pull
docker compose up --build --wait
docker compose ps
python scripts/verify_compose.py
```

Expected: bootstrap 成功退出，API/MCP/PostgreSQL 健康；脚本证明 live、ready、创建、binding、审批、重复审批 `409`、一条审批、一条工单和正确终态审计事件。

- [ ] **Step 5: 进行 API/MCP 重启后的恢复验证**

```bash
docker compose restart api mcp
docker compose ps
python scripts/verify_compose.py --recovery-only
```

Expected: readiness 恢复为 `200`，已完成审批/工单记录仍满足数据库断言；普通重启不删除 named volume。

- [ ] **Step 6: 运行完整质量门禁并记录真实输出**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`

Expected: 全部 PASS；将实际版本、镜像 digest、Git commit、命令/结果、未验证范围与回滚点写入证据。若任何命令失败，先记录 `docker compose ps`、安全日志摘要和退出码，修复原因后从 bootstrap 开始重跑，不删除 volume。

- [ ] **Step 7: 更新中文交接与索引，并提交证据检查点**

```bash
git add scripts/verify_compose.py docs/release-evidence/docker-linux-runtime.md README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/development-log
git commit -m "docs: record docker linux runtime evidence"
```

证据必须明确：这是 Ubuntu Docker Compose 单节点重复启动验证，不代表高可用、性能、SLA、公开部署或发布门禁通过。

## Self-Review

- **规格覆盖：** Task 0 覆盖 Hyper-V/Ubuntu/Docker 事实记录；Task 1–2 覆盖 API/MCP liveness、readiness、安全响应和 bootstrap 契约；Task 3 覆盖四服务、非 root、端口、volume、锁定依赖与秘密边界；Task 4 覆盖干净构建、真实业务闭环、数据库断言、重启、质量门禁、回滚和证据。
- **明确排除：** 全局约束逐项保留；计划没有把 Redis、公开入口或发布声明提前。
- **一致性：** API probe 名称、`/health/live`、`/health/ready`、MCP `/mcp` 路径和四个 Compose 服务在各任务中一致；只有 `bootstrap` 迁移与 `setup=True`。
- **占位扫描：** 本计划不含待定任务或“以后实现”步骤；用户外部操作以 Task 0 的可执行命令列出。

## Execution Handoff

本计划已为当前对话的 **Inline Execution** 设计：按任务顺序执行，每个任务完成后运行其测试与原子提交，再进入下一项。Task 0 需要用户在 Windows/Ubuntu VM 中手动完成；其余任务在仓库内按测试驱动实施。
