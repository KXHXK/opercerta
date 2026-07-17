# 本地演示 JWT/RBAC 验证证据

**验证日期：** 2026-07-18 Asia/Shanghai  
**范围：** OperCerta 本地单节点 JWT、角色权限、审批主体绑定与 WSL2 Docker Compose。  
**发布结论：** 本证据不构成公开发布或生产 IAM 通过；`OperCerta release gate: CLOSED`。

## 已验证行为

- 缺失 Bearer token 的业务创建请求返回 `401 authentication_required`，不会进入业务操作。
- `operator` 可以创建补货操作但不能审批；越权审批返回 `403 permission_denied`。
- `approver` 的审批主体由 JWT `sub` 注入，API 请求体不再接受 `approver_id`。
- `auditor` 能读取 operation；JWT 过期、篡改、错误签发方/受众和未知角色被拒绝。
- PostgreSQL 审批竞态、幂等工单和 LangGraph 重启恢复回归继续通过。

## 实际执行证据

Windows 本地最终门禁：

```text
uv sync --frozen --all-groups
uv run pytest -q                         -> 310 passed in 63.19s
uv run ruff check .                      -> All checks passed!
uv run ruff format --check .             -> 81 files already formatted
uv run mypy src                          -> Success: no issues found in 42 source files
```

WSL2 Ubuntu 中的 Docker 实测：

```text
docker compose up --build -d
python3 scripts/verify_compose.py        -> exit 0
docker compose restart api mcp
python3 scripts/verify_compose.py --recovery-only -> exit 0
```

完整 smoke 使用 operator 演示 token 创建/读取、approver 演示 token 审批/重复审批；它断言重复审批为 `409`、数据库对该 operation 仅一条审批和一条工单，且末尾审计事件是 `operation_completed`。

## 已知限制与回滚

- `POST /api/v1/auth/demo-token` 仅是显式启用的本地演示入口；公开部署必须保持关闭。
- 这不是密码管理、OIDC/SSO、账号生命周期、多租户数据隔离或生产 IAM。
- Compose 仅验证 WSL2 本地单节点；不证明高可用、外网 HTTPS、公开部署或第三方身份服务。
- 回滚认证代码可使用 Git 提交 `69ea3e0` 之前的已知提交；回滚前先停止 Compose 服务并重新运行完整门禁。不得回滚或提交被忽略的 `.env.compose`。
