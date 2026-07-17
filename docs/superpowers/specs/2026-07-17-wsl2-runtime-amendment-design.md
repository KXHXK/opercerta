# WSL2 Ubuntu 26.04 运行环境修订设计

**状态：** 用户已确认

本修订替代 `2026-07-16-docker-linux-runtime-design.md` 中所有 Hyper-V VM 与 Ubuntu 24.04 的环境表述；其余 Compose 架构、健康契约、非 root、秘密边界和发布门禁保持不变。

## 决策

运行路径为 `Windows 10 LTSC 2021 → WSL2 → Ubuntu 26.04 LTS → Docker Engine/Compose → OperCerta`。不安装 Docker Desktop，不启用完整 Hyper-V 管理功能，不创建 Hyper-V VM。

## 安装来源例外（2026-07-17）

原计划的 Docker 厂商 APT 源在当前网络中不可达：Windows 与 WSL2 对 `download.docker.com` 的 TLS 握手均被重置。用户已确认改用 Ubuntu 26.04 官方签名仓库，不使用第三方镜像源。已安装的运行时为 `docker.io 29.1.3-0ubuntu4.1`、`docker-compose-v2 2.40.3+ds1-0ubuntu1`、`docker-buildx 0.30.1-0ubuntu1`；这只是包来源例外，不是 Compose 验收通过。

Docker Hub `registry-1.docker.io` 直连当前超时。经用户提供并授权的候选清单实测，`docker.m.daocloud.io`、`docker.1ms.run` 与 `docker.xuanyuan.me` 可完成 Registry v2 TLS/API 探针，`dockerproxy.com` 超时且未配置。三项可达服务已写入 `/etc/docker/daemon.json` 的 `registry-mirrors`，并作为第三方供应链例外记录。

验证只使用普通名称 `hello-world`：Docker 成功经配置的 mirror 拉取并运行，实际 digest 为 `sha256:c3cbe1cc1aa588a64951ac6286e0df7b27fe2e6324b1001c619bb358770c0178`。这证明 Docker 基础链路可用，不等同于 OperCerta 镜像、Compose 或业务闭环通过；后续仍须逐项记录实际镜像 digest 与业务验收结果。

## 数据库边界

现有 Windows 原生 PostgreSQL 保留用于本机集成测试。Compose 在 WSL2 内以独立 PostgreSQL 容器和 named volume 运行；不复制 Windows 数据目录、数据库数据或 `.env.local`，并由独立、忽略的 `.env.compose` 提供容器配置。

## 验收边界

真实验收在 WSL2 Ubuntu 内执行 `docker compose`；Windows 仅通过 WSL 路径访问 API。证据必须记录 Ubuntu 26.04、WSL2、Docker Engine、Compose、镜像 digest 和 Git commit。该单节点验证不代表高可用、性能、SLA 或公开发布，`OperCerta release gate: CLOSED` 保持不变。
