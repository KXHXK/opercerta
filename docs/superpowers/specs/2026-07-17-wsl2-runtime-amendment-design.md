# WSL2 Ubuntu 26.04 运行环境修订设计

**状态：** 用户已确认

本修订替代 `2026-07-16-docker-linux-runtime-design.md` 中所有 Hyper-V VM 与 Ubuntu 24.04 的环境表述；其余 Compose 架构、健康契约、非 root、秘密边界和发布门禁保持不变。

## 决策

运行路径为 `Windows 10 LTSC 2021 → WSL2 → Ubuntu 26.04 LTS → Docker Engine/Compose → OperCerta`。不安装 Docker Desktop，不启用完整 Hyper-V 管理功能，不创建 Hyper-V VM。

## 安装来源例外（2026-07-17）

原计划的 Docker 厂商 APT 源在当前网络中不可达：Windows 与 WSL2 对 `download.docker.com` 的 TLS 握手均被重置。用户已确认改用 Ubuntu 26.04 官方签名仓库，不使用第三方镜像源。已安装的运行时为 `docker.io 29.1.3-0ubuntu4.1`、`docker-compose-v2 2.40.3+ds1-0ubuntu1`、`docker-buildx 0.30.1-0ubuntu1`；这只是包来源例外，不是 Compose 验收通过。

Docker Hub `registry-1.docker.io` 当前同样超时，因而尚不能拉取基础镜像、获得镜像 digest 或运行 OperCerta 容器。必须先恢复对所需镜像仓库的可验证访问；不得为绕过该问题擅自改用未审查的第三方 registry mirror。

## 数据库边界

现有 Windows 原生 PostgreSQL 保留用于本机集成测试。Compose 在 WSL2 内以独立 PostgreSQL 容器和 named volume 运行；不复制 Windows 数据目录、数据库数据或 `.env.local`，并由独立、忽略的 `.env.compose` 提供容器配置。

## 验收边界

真实验收在 WSL2 Ubuntu 内执行 `docker compose`；Windows 仅通过 WSL 路径访问 API。证据必须记录 Ubuntu 26.04、WSL2、Docker Engine、Compose、镜像 digest 和 Git commit。该单节点验证不代表高可用、性能、SLA 或公开发布，`OperCerta release gate: CLOSED` 保持不变。
