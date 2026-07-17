# WSL2 Ubuntu 26.04 运行环境修订设计

**状态：** 用户已确认

本修订替代 `2026-07-16-docker-linux-runtime-design.md` 中所有 Hyper-V VM 与 Ubuntu 24.04 的环境表述；其余 Compose 架构、健康契约、非 root、秘密边界和发布门禁保持不变。

## 决策

运行路径为 `Windows 10 LTSC 2021 → WSL2 → Ubuntu 26.04 LTS → Docker Engine/Compose → OperCerta`。不安装 Docker Desktop，不启用完整 Hyper-V 管理功能，不创建 Hyper-V VM。

## 数据库边界

现有 Windows 原生 PostgreSQL 保留用于本机集成测试。Compose 在 WSL2 内以独立 PostgreSQL 容器和 named volume 运行；不复制 Windows 数据目录、数据库数据或 `.env.local`，并由独立、忽略的 `.env.compose` 提供容器配置。

## 验收边界

真实验收在 WSL2 Ubuntu 内执行 `docker compose`；Windows 仅通过 WSL 路径访问 API。证据必须记录 Ubuntu 26.04、WSL2、Docker Engine、Compose、镜像 digest 和 Git commit。该单节点验证不代表高可用、性能、SLA 或公开发布，`OperCerta release gate: CLOSED` 保持不变。
