# Demo JWT and RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 为 OperCerta 的业务 API 增加本地短时 JWT 与四角色 RBAC，并让审批审计只使用经过验证的身份主体。

**Architecture:** 在 src/opercerta/api/auth.py 集中定义角色、演示账户、签发/验证和 FastAPI 依赖；AppRuntime 持有认证器，路由只声明需要的角色。生产设置从环境读取 JWT 约束；Compose smoke 分别以 operator 和 approver 调用，不改变 PostgreSQL 审批原子性、工单幂等与重启恢复。

**Tech Stack:** Python 3.12、FastAPI 0.139.0、Pydantic 2.13.4、PyJWT 2.13.0、HTTPX 0.28.1、PostgreSQL、Docker Compose。

## Global Constraints

- 只实施 OperCerta；不引入 SSO/OAuth、账号注册、前端、SSE、Redis、多租户或其他项目。
- pyjwt[crypto]==2.13.0 已锁定；禁止新增认证库或升级锁定依赖。
- JWT 仅允许 HS256，验证 iss、aud、iat、exp、sub、role、jti；签名密钥为 SecretStr，不能进入 Git、日志、响应或测试快照。
- /health/live 和 /health/ready 保持公开；其他业务 /api/v1/* 路由需要 Bearer JWT。
- 认证失败发生在 runner、MCP 和业务数据库写入之前；批准主体只能来自 JWT sub。
- 保留六项 approval binding 和现有事务、竞态、幂等、恢复语义；发布门禁持续 CLOSED。
- 使用 uv run。每项先观察 RED，再写最小 GREEN；每项独立提交。

---

## 文件结构与职责

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| src/opercerta/api/auth.py | 新建 | 角色、演示账户、JWT 签发/验证、角色依赖。 |
| tests/unit/api/test_auth.py | 新建 | JWT 声明和无效令牌纯单元测试。 |
| src/opercerta/api/models.py | 修改 | 删除请求体 approver_id；增加演示 token 模型。 |
| src/opercerta/api/app.py | 修改 | 设置、运行时认证器、稳定错误映射、token 路由、RBAC。 |
| tests/integration/api/test_operations_api.py | 修改 | 真实 token、越权、可信审批主体、零写入断言。 |
| tests/integration/api/test_health_api.py | 修改 | 健康路由公开回归。 |
| .env.compose.example | 修改 | 非真实 JWT 配置示例。 |
| scripts/verify_compose.py | 修改 | 获取两种演示 token 的端到端 smoke。 |
| tests/unit/runtime/test_container_assets.py | 修改 | 示例变量与无 approver_id 的 smoke 资产检查。 |
| README.md、IMPLEMENTATION_HANDOFF.md、docs/development-log、docs/release-evidence | 修改/新建 | 仅记录真实执行证据和未完成限制。 |

## Task 1: JWT 契约与验证器

**Files:**
- Create: src/opercerta/api/auth.py
- Create: tests/unit/api/test_auth.py

**Interfaces:**
- Produces Role(StrEnum): OPERATOR、APPROVER、AUDITOR、DEMO_ADMIN。
- Produces immutable AuthenticatedActor(subject: str, role: Role)。
- Produces JwtSettings(signing_key: SecretStr, issuer: str, audience: str, ttl_seconds: PositiveInt, demo_token_enabled: bool)。
- Produces JwtAuthenticator.issue_demo_token(account: DemoAccount, now: datetime) -> str。
- Produces JwtAuthenticator.authenticate(authorization: str | None, now: datetime) -> AuthenticatedActor。

- [ ] **Step 1: 写失败的单元测试**

~~~python
def test_issued_token_round_trips_to_fixed_demo_actor() -> None:
    auth = make_authenticator()
    token = auth.issue_demo_token(DemoAccount.APPROVER, NOW)
    assert auth.authenticate(f"Bearer {token}", NOW) == AuthenticatedActor(
        subject="demo.approver", role=Role.APPROVER
    )


@pytest.mark.parametrize("authorization", [None, "Basic x", "Bearer malformed"])
def test_missing_or_malformed_authorization_is_not_authenticated(
    authorization: str | None,
) -> None:
    with pytest.raises(AuthenticationRequired):
        make_authenticator().authenticate(authorization, NOW)
~~~

再分别测试：过期 token、篡改签名、错误 iss、错误 aud、未知 role 均抛出 InvalidAccessToken；DemoAccount 只接受四个固定枚举；demo_token_enabled=False 时抛出 DemoTokenUnavailable。

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/unit/api/test_auth.py -q  
Expected: 退出码 1，原因是 opercerta.api.auth 不存在；不修改 API 路由。

- [ ] **Step 3: 实现最小认证模块**

~~~python
class Role(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


class DemoAccount(StrEnum):
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


DEMO_ACTORS = {
    DemoAccount.OPERATOR: AuthenticatedActor("demo.operator", Role.OPERATOR),
    DemoAccount.APPROVER: AuthenticatedActor("demo.approver", Role.APPROVER),
    DemoAccount.AUDITOR: AuthenticatedActor("demo.auditor", Role.AUDITOR),
    DemoAccount.DEMO_ADMIN: AuthenticatedActor("demo.admin", Role.DEMO_ADMIN),
}
~~~

用 jwt.encode 签发含 sub、role、iss、aud、UTC iat/exp 和 jti=uuid4().hex 的 HS256 token。用 jwt.decode 的 algorithms=["HS256"]、issuer、audience 与 require=[sub, role, iss, aud, iat, exp, jti] 验证；只将 PyJWT 验证异常转为稳定本地异常，绝不回传库异常文本。

- [ ] **Step 4: 运行 GREEN 与静态检查**

Run: uv run pytest tests/unit/api/test_auth.py -q; uv run ruff check src/opercerta/api/auth.py tests/unit/api/test_auth.py; uv run ruff format --check src/opercerta/api/auth.py tests/unit/api/test_auth.py; uv run mypy src/opercerta/api/auth.py  
Expected: 全部退出码 0。

- [ ] **Step 5: 提交**

~~~bash
git add src/opercerta/api/auth.py tests/unit/api/test_auth.py
git commit -m "feat: add demo jwt authentication contract"
~~~

## Task 2: API RBAC 与可信审批主体

**Files:**
- Modify: src/opercerta/api/models.py
- Modify: src/opercerta/api/app.py
- Modify: tests/integration/api/test_operations_api.py
- Modify: tests/integration/api/test_health_api.py

**Interfaces:**
- Consumes JwtAuthenticator、AuthenticatedActor、Role、AuthenticationRequired、InvalidAccessToken、PermissionDenied、DemoTokenUnavailable。
- Produces POST /api/v1/auth/demo-token: 输入 {"account":"operator"|"approver"|"auditor"|"demo-admin"}，输出 {"access_token": str, "token_type":"bearer", "expires_in": int}。
- Produces权限：create=operator；read=四角色；approval=approver。

- [ ] **Step 1: 写 API RED 测试并更新测试 harness**

~~~python
async def test_business_request_without_bearer_token_returns_401_and_writes_nothing(...) -> None:
    response = await harness.client.post("/api/v1/operations", json=operation_payload())
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert await count_operations(engine) == 0


async def test_operator_cannot_approve_and_body_cannot_spoof_approver(...) -> None:
    created = await harness.create_operation(role=Role.OPERATOR)
    detail = await harness.get_operation(created["operation_id"], role=Role.OPERATOR)
    response = await harness.approve(
        created["operation_id"], detail, role=Role.OPERATOR,
        extra={"approver_id": "demo.approver"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert await count_approvals(engine, created["operation_id"]) == 0
~~~

添加成功审批断言：approver token 产生的 approval.approver_id 等于 demo.approver；请求体含 approver_id 时严格模型返回 422；auditor 与 demo-admin 创建/审批均为 403；篡改、过期 token 为 401；health 两路径无 Authorization 仍为 200。

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/integration/api/test_operations_api.py -q  
Expected: 退出码 1，至少一个断言显示预期 401/403 而旧 API 返回 202，或新依赖尚不存在；不能接受测试夹具缺少数据库配置的失败。

- [ ] **Step 3: 接入 FastAPI 依赖与错误映射**

在 AppRuntime 增加 authenticator: JwtAuthenticator；ProductionSettings 增加 OPERCERTA_JWT_SIGNING_KEY、OPERCERTA_JWT_ISSUER、OPERCERTA_JWT_AUDIENCE、OPERCERTA_JWT_TTL_SECONDS、OPERCERTA_DEMO_TOKEN_ENABLED，并在 _open_production_runtime 构造认证器。

~~~python
class DemoTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    account: DemoAccount


class DemoTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
~~~

ApprovalRequest 仅保留 decision、reason 和六项 binding。审批路由由验证后的 actor.subject 创建命令：

~~~python
async def submit_approval(
    operation_id: UUID,
    approval_request: ApprovalRequest,
    actor: Annotated[AuthenticatedActor, Depends(require_roles(Role.APPROVER))],
) -> OperationAccepted:
    command = BoundApprovalCommand(
        operation_id=operation_id,
        approver_id=actor.subject,
        decision=approval_request.decision,
        reason=approval_request.reason,
        expected_binding=approval_request.approval_binding(),
    )
~~~

异常处理器固定映射：缺失格式=401 authentication_required，验证失败=401 invalid_access_token，角色不足=403 permission_denied，禁用演示签发=403 demo_token_unavailable。响应不含 token、密钥、JWT 异常或 traceback。

- [ ] **Step 4: 运行 GREEN、竞态和恢复回归**

Run: uv run pytest tests/integration/api -q; uv run pytest tests/integration/db/test_approval_race.py tests/integration/db/test_bound_approval.py tests/integration/workflow/test_replenishment_restart.py -q  
Expected: 全部退出码 0；并发审批仍一条审批、至多一条工单；恢复按原已存决定推进。

- [ ] **Step 5: 提交**

~~~bash
git add src/opercerta/api/app.py src/opercerta/api/models.py tests/integration/api
git commit -m "feat: protect operations with demo jwt roles"
~~~

## Task 3: Compose 配置与认证 smoke

**Files:**
- Modify: .env.compose.example
- Modify: scripts/verify_compose.py
- Modify: tests/unit/runtime/test_container_assets.py

**Interfaces:**
- Consumes Task 2 token endpoint 和角色规则。
- Produces先获 operator token 用于创建/读取、再获 approver token 用于审批的无密钥 smoke。

- [ ] **Step 1: 写资产 RED 测试**

~~~python
def test_compose_example_declares_required_demo_jwt_settings() -> None:
    content = Path(".env.compose.example").read_text(encoding="utf-8")
    assert "OPERCERTA_JWT_SIGNING_KEY=CHANGE_ME_DEVELOPMENT_ONLY" in content
    assert "OPERCERTA_DEMO_TOKEN_ENABLED=true" in content


def test_compose_smoke_never_posts_approver_id() -> None:
    content = Path("scripts/verify_compose.py").read_text(encoding="utf-8")
    assert '"approver_id"' not in content
    assert '"/api/v1/auth/demo-token"' in content
~~~

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/unit/runtime/test_container_assets.py -q  
Expected: 退出码 1，示例没有 JWT 变量且 smoke 仍含 approver_id。

- [ ] **Step 3: 实现 secret-safe 运行时资产**

.env.compose.example 增加：

~~~dotenv
OPERCERTA_JWT_SIGNING_KEY=CHANGE_ME_DEVELOPMENT_ONLY
OPERCERTA_JWT_ISSUER=opercerta-local-demo
OPERCERTA_JWT_AUDIENCE=opercerta-api
OPERCERTA_JWT_TTL_SECONDS=300
OPERCERTA_DEMO_TOKEN_ENABLED=true
~~~

为 request 增加 headers: dict[str, str] | None；新增：

~~~python
def demo_headers(account: str) -> dict[str, str]:
    status, body = request("POST", "/api/v1/auth/demo-token", {"account": account})
    assert status == 200
    return {"Authorization": f"Bearer {body['access_token']}"}
~~~

main 依次得到 demo_headers("operator") 与 demo_headers("approver")；创建/读取用前者，审批/重复审批用后者，审批 JSON 删除 approver_id。本地被忽略 .env.compose 由操作者写入随机开发密钥，不能打印、写日志或提交。

- [ ] **Step 4: 运行 GREEN 和实际 Compose smoke**

Run: uv run pytest tests/unit/runtime/test_container_assets.py -q; uv run ruff check scripts/verify_compose.py; uv run ruff format --check scripts/verify_compose.py  
Expected: 全部退出码 0。

在 WSL2 Ubuntu 中，以不回显方式补齐被忽略 .env.compose 后：

~~~bash
docker compose up --build -d
uv run python scripts/verify_compose.py
docker compose restart api mcp
uv run python scripts/verify_compose.py --recovery-only
~~~

Expected: 四服务健康；完整 smoke 证明 operator 创建、approver 审批、重复审批 409、数据库一条审批/工单；重启后健康恢复。任何失败都停止证据写入并按系统化调试流程处理。

- [ ] **Step 5: 提交**

~~~bash
git add .env.compose.example scripts/verify_compose.py tests/unit/runtime/test_container_assets.py
git commit -m "test: authenticate compose replenishment smoke"
~~~

## Task 4: 全量门禁、实际证据与交接

**Files:**
- Modify: README.md
- Modify: IMPLEMENTATION_HANDOFF.md
- Modify: DOCUMENT_INDEX.md
- Modify: docs/development-log/current-state.md
- Modify: docs/development-log/daily/2026-07-17.md
- Modify: docs/development-log/interview-casebook.md
- Create: docs/release-evidence/demo-jwt-rbac.md

**Interfaces:**
- Consumes真实测试、静态检查和 Compose 输出；不从本计划假设结果。
- Produces可复核的本地单节点认证证据，并明确生产 IAM、SSO、前端、SSE、评测、可观测性与公开部署仍未完成。

- [ ] **Step 1: 运行最终质量门禁**

Run: uv sync --frozen --all-groups; uv run pytest -q; uv run ruff check .; uv run ruff format --check .; uv run mypy src  
Expected: 全部退出码 0。记录真实测试数量和耗时；不能把它写成业务或生产指标。

- [ ] **Step 2: 写入实际结果与限制**

demo-jwt-rbac.md 只记录真实执行命令、日期、退出状态、HTTP/数据库断言、实际镜像 digest（若重新构建）、回滚方式和未验证范围。README 与交接说明 JWT 是本地演示边界，demo-token 默认关闭且公开部署不能启用；这不是生产 IAM。日志记录 RED 原因、修复、GREEN 结果；案例本记录“从可伪造审批字段到服务端可信主体”的威胁模型和限制。

- [ ] **Step 3: 验证文档并提交**

Run: git diff --check; git status --short; git diff -- docs/release-evidence/demo-jwt-rbac.md README.md IMPLEMENTATION_HANDOFF.md  
Expected: 无空白错误，且没有 .env.compose、JWT、数据库 URL、密码或真实客户数据。

~~~bash
git add README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs/development-log docs/release-evidence/demo-jwt-rbac.md
git commit -m "docs: record demo jwt rbac verification"
~~~

## 自审结果

- 规格覆盖：Task 1 覆盖 HS256、必需声明、短时 token 与禁用入口；Task 2 覆盖四角色、稳定 401/403、可信审批主体和零写入；Task 3 覆盖 Compose 设置及 smoke；Task 4 覆盖门禁、证据与未完成范围。
- 占位检查：所有代码步骤、测试命令、RED/GREEN 预期和提交范围均已明确。
- 类型一致性：JwtAuthenticator、AuthenticatedActor、Role、DemoAccount 在 Task 1 定义；Task 2 和 Task 3 只消费这些名称；ApprovalRequest 的 approver_id 在 Task 2 明确删除。

