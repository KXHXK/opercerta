# OperCerta 三业务本地发布候选证据

## 结论与范围

2026-07-20 在提交 `a3994ef` 上完成本地单节点发布候选验证。库存补货、设备维修、作业异常恢复通过同一个 Caddy 入口访问 React 与 FastAPI；PostgreSQL、Redis、MCP、API 和 metrics 管理面均未直接映射宿主机端口。验证对象使用合成数据、演示 JWT 和 Mock 模型。

这份证据只证明“可重复构建并在本机 WSL2/Docker Compose 跑通”。真实模型随后已在独立证据中完成代表性验证；本文仍不证明生产 IAM/SSO、公网 HTTPS、限流/防滥用、高可用、备份恢复、自动部署或 Release Tag 已完成。生产发布门禁保持 `CLOSED`。

## 发布资产

- `compose.release.yaml`：仅 Caddy 暴露 HTTP/HTTPS；PostgreSQL、Redis、MCP、API 只在 Compose 网络内可达。
- `deploy/Dockerfile`：Node `24-alpine3.24` 构建 React 静态产物，Caddy `2.11.4-alpine` 提供静态站点和反向代理。
- `deploy/Caddyfile`：`/api/*`、`/health/live`、`/health/ready` 转发到 API；其他路径使用 SPA fallback；没有 `/metrics`、MCP、PostgreSQL 或 Redis 公共路由。
- `scripts/verify_release_compose.sh`：构建、启动、从 Caddy 等待应用就绪、验证三业务、重启 API/MCP、验证恢复、检查 metrics 不公开，并在成功或失败后删除容器和数据卷。

## 新鲜命令与结果

### 后端与静态门禁

```powershell
uv sync --frozen --all-groups
python -m pytest -q
ruff check .
ruff format --check .
mypy src
python scripts/verify_repository_safety.py
```

- 后端：`422 passed in 94.96s`
- Ruff lint：通过
- Ruff format：`136 files already formatted`
- mypy：`62 source files` 无问题
- 依赖同步：检查 92 个包，锁文件未漂移
- 仓库安全扫描：通过

### 前端

```powershell
cd web
npm ci
npm run test:run
npm run build
```

- `npm ci`：安装 121 个包，审计 122 个包，0 vulnerabilities
- Vitest：12 个测试文件、25 条测试全部通过
- TypeScript/Vite：生产构建通过；生成 HTML、CSS 和 JS 产物

首次执行 `npm ci` 因正在运行的本项目 Vite 进程锁定 `web/node_modules` 而返回 Windows `EPERM`。只停止该 OperCerta Vite 进程后重跑上述完整前端门禁通过；没有删除其他 Node 进程或修改业务代码。

### Caddy 配置

```bash
docker run --rm -v "$PWD/deploy:/work" caddy:2.11.4-alpine \
  caddy fmt --overwrite /work/Caddyfile
docker run --rm -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.11.4-alpine caddy validate --config /etc/caddy/Caddyfile
```

结果为 `Valid configuration`。本地地址固定为 HTTP，因此校验日志明确提示不会启用自动 HTTPS；设置真实域名并完成 DNS/80/443 入站配置后才允许验证和声明公网 HTTPS。

### 一键发布候选 smoke

```powershell
wsl.exe -d Ubuntu -- bash -lc \
  'cd /mnt/d/CODEX/agent-portfolio/opercerta && bash scripts/verify_release_compose.sh'
```

2026-07-20 新鲜运行退出码为 0，耗时 70.8 秒。脚本验证：

- Caddy 根路径返回 OperCerta 静态页面；业务 API 只经 Caddy 访问。
- 三业务批准后分别形成唯一 `replenishment`、`repair`、`task_recovery` 工单。
- 拒绝路径零工单，重复审批冲突，PostgreSQL 审批/工单/终态事实一致。
- API/MCP 重启后，重启前的待审批 operation 仍能通过公开入口恢复读取。
- `/metrics` 返回 SPA 的 `text/html`，没有被反向代理到内部 metrics 端点。
- trap 最终执行 `docker compose down -v --remove-orphans`，不保留本轮合成数据。

脚本最后的 `docker compose ps` 发生在 API/MCP 刚重启后，二者显示 `health: starting`；随后恢复请求已成功，但该瞬时列表不能写成“所有容器最终均 healthy”。

## 本轮发现并修复的真实缺陷

1. Caddy 指令排序曾让 `/health/ready` 落入 SPA fallback。改为互斥 `handle @api` 与静态 `handle`，并用资产测试保护路由形状。
2. 设备评估哈希曾包含持续变化的 `heartbeat_age_seconds`，导致事实未变时批准后一秒也错误报 `approval_snapshot_mismatch`。哈希改为稳定源事实与分类结果，展示年龄仍保留。
3. Caddy 在 API/MCP 重启窗口可能返回空正文 502。release smoke 的响应解码改为容忍非 JSON 启动错误，但业务断言仍严格检查终态。

## 仍未完成的门禁

- 三业务真实模型代表性验证已完成，见 `docs/release-evidence/real-model-representative-validation.md`；它不是公网或生产运行证明。
- 选择公网后端资源，配置真实域名、HTTPS、生产密钥、限流、防滥用、备份/恢复和回滚演练。
- 将固定提交推送远程并等待当前五个 GitHub Actions job 全绿，再决定 pre-release 或 Release Tag。
- 用户亲手完成一个业务闭环、一次规则修改和一次 MCP 故障实验；完成前不声称个人熟练掌握。
