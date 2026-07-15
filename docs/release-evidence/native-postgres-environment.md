# Windows 原生 PostgreSQL 环境证据

## 范围

本文件只证明 OperCerta 本机集成测试可使用真实 PostgreSQL 18.4；它不证明完整可靠性内核、公开部署或发布门禁通过。

## 核验事实

- 核验时间：2026-07-15 21:44 Asia/Shanghai。
- 核验时 Git commit：`fc974f5`。
- 官方安装器：`postgresql-18.4-2-windows-x64.exe`，大小 358.89 MB。
- Authenticode：`Valid`；签名主体为 `EnterpriseDB Corporation`。
- SHA-256：`0698D1A6083DA490E5A57149257F5D9220D8C34109ED11B38AA592D320BF5385`。
- 二进制版本：`postgres (PostgreSQL) 18.4`。
- Windows 服务：`postgresql-x64-18`，状态 `Running`，启动类型 `Automatic`。
- 安装目录：`C:\Program Files\PostgreSQL\18`；数据目录：`D:\PostgreSQL\18\data`。

## 网络与认证

- 唯一监听地址：`127.0.0.1:55432`。
- `pg_isready -h 127.0.0.1 -p 55432` 返回 `accepting connections`。
- `postgresql.conf` 的有效设置：`listen_addresses = '127.0.0.1'`、`port = 55432`、`password_encryption = 'scram-sha-256'`。
- `pg_hba_file_rules`：普通 IPv4 回环规则为 `127.0.0.1 / scram-sha-256`；普通 IPv6 回环规则为 `::1 / reject`。服务没有 IPv6 监听；复制用途的 IPv6 规则不构成端口暴露。

## 真实连接探针

从已忽略 `.env.local` 在不输出连接串的前提下加载 `OPERCERTA_DATABASE_URL`，SQLAlchemy 查询返回：

```text
PostgreSQL 18.4 on x86_64-windows
database: opercerta_test
user: opercerta
server: 127.0.0.1/32:55432
```

## 回归与边界

- 最近单元测试：`uv run pytest -q`，`19 passed`，退出码 0。
- 静态检查：`uv run ruff check .` 通过；默认 `uv run mypy` 在加入 PEP 561 `src/opercerta/py.typed` 标记后实际检查 5 个源文件并通过，修复提交 `84a7b08`。
- PostgreSQL 迁移和审批竞态已实现并验证，详见 `docs/release-evidence/approval-atomicity.md`；幂等写入和 LangGraph checkpoint 重启恢复尚未实现或验证。
- Linux/Docker 一致性验证尚未执行。
- `OperCerta release gate: CLOSED`。
