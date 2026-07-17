# WSL2 Ubuntu Docker Compose 运行时证据

**核验日期：** 2026-07-17（Asia/Shanghai）  
**被核验实现：** `91cffa8f68c66ed3d89c92daf9f9b956cae45064`

## 环境与供应链边界

- 运行路径：Windows 10 LTSC 2021 → WSL2 → Ubuntu 26.04 LTS → Docker Engine → Compose。
- Docker 来自 Ubuntu 官方签名仓库：Engine `29.1.3`、Compose `2.40.3+ds1-0ubuntu1`、Buildx `0.30.1-0ubuntu1`。
- Docker 厂商 APT 源与 Docker Hub 直连在本机网络超时。经用户授权，`/etc/docker/daemon.json` 仅配置了实测可达的 DaoCloud、1ms、轩辕三个第三方 registry mirror；这是供应链例外，不含账号或凭据。
- `hello-world` 已通过普通名称拉取并运行，digest 为 `sha256:c3cbe1cc1aa588a64951ac6286e0df7b27fe2e6324b1001c619bb358770c0178`。
- Compose PostgreSQL 使用独立 named volume `opercerta_postgres_data`；未复制 Windows PostgreSQL 数据或 `.env.local`。真实 `.env.compose` 为被 Git 忽略的本机文件，使用随机本地数据库密码，未写入本证据。

## 镜像事实

- Python 基础镜像构建解析为 `python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b`。
- uv 工具镜像构建解析为 `ghcr.io/astral-sh/uv:0.10.10@sha256:cbe0a44ba994e327b8fe7ed72beef1aaa7d2c4c795fd406d1dbf328bacb2f1c5`。
- PostgreSQL 18 实际 repo digest 为 `postgres@sha256:32ca0af8e77bfb8c6610c488e4691f83f972a3e9e64d3b02facf3ab111ad5500`。
- 最终本地 Compose image ID：API `6476f0cd77f0`、bootstrap `172cd52fe2af`、MCP `9a4e188b0f8d`。这些是本机 BuildKit 产物标识，不是已推送的远程镜像。

## 实施中发现并固定的缺陷

1. Dockerfile 在 `uv sync --frozen --no-dev` 前未复制 Hatchling 所需的 `README.md` 和 `src/`，首次真实构建以 `Readme file does not exist` 失败。新增容器资产 RED 测试后修复复制顺序。
2. `postgres:18` 拒绝旧的 `/var/lib/postgresql/data` named-volume 挂载，以防止跨主版本数据目录误用。新增 RED 测试后改为 `/var/lib/postgresql`；原 volume 未删除。
3. FastMCP 默认拒绝 Compose 内部 `Host: mcp:8001`，导致 API operation 安全失败为 `dependency_unavailable`。新增真实 Streamable HTTP 会话 RED 测试后，限制性加入 `mcp[:8001]`、loopback 与当前监听地址白名单；未允许任意 Host。

## 真实验收命令与结果

```text
docker compose config -q                              exit 0
docker compose build --pull                           exit 0
docker compose up --build --wait                      exit 0
python3 scripts/verify_compose.py                     exit 0
docker compose restart api mcp                        exit 0
docker compose up --wait --no-deps api mcp            exit 0
python3 scripts/verify_compose.py --recovery-only     exit 0
```

最终 `docker compose ps` 显示 PostgreSQL、MCP、API 均为 `healthy`；bootstrap 成功退出；PostgreSQL 与 MCP 没有主机端口，API 仅发布 `127.0.0.1:8080`。

真实 smoke 使用合成的 `SKU-LOW-001`，证明：live/ready、创建低库存 operation、读取 approval binding、批准、重复批准 `409 approval_already_decided`、同一 operation 恰有一条审批与一条工单，且审计终态为 `operation_completed`。API/MCP 重启后，`--recovery-only` 再次确认 live/ready，named volume 未删除。

完整本机质量门禁：`297 passed in 62.67s`，Ruff clean，`79 files already formatted`，mypy 对 `41 source files` 无错误。

## 回滚与未验证范围

- 停止本地容器可执行 `docker compose down`，该操作保留 named volume；只有明确决定丢弃容器测试数据时才使用 `docker compose down -v`。
- 代码回滚点为 `91cffa8` 之前的提交；镜像代理、Ubuntu Docker 包来源与网络可达性仍是本机环境风险。
- 本证据仅证明单节点 WSL2 Ubuntu Compose 的重复启动和业务闭环，不证明高可用、性能、SLA、认证、前端、固定评测、安全回归、可观测性或公开部署。
- `OperCerta release gate: CLOSED`。
