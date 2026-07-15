# 决策：Windows 原生 PostgreSQL 18.4 作为当前集成测试数据库

## 背景

当前 Windows 工作站的 WSL2/虚拟化组件修复未成功，Docker Desktop 与 Docker Engine 不再作为本地开发前置条件。审批竞态、幂等写入和 LangGraph PostgreSQL checkpoint 仍需要真实 PostgreSQL 事务语义。

## 候选方案

1. Windows 原生 PostgreSQL 18.4。
2. 远程 Linux PostgreSQL。
3. WSL2 加 Docker Desktop。

## 采用方案

采用 Windows 原生 PostgreSQL 18.4，服务仅监听 `127.0.0.1:55432`，使用 SCRAM 认证，专用测试数据库为 `opercerta_test`。

## 理由

该方案能在当前工作站立即提供真实并发和事务验证，且不因未修复的 Windows 组件存储问题阻塞可靠性内核。远程服务会额外引入网络和凭据边界；WSL2 加 Docker 在当前机器上仍是已知阻塞。

## 影响与验证

本地 Task 3 的前置条件改为可连接的 PostgreSQL 实例。验证要求包括 PostgreSQL 18.4、`127.0.0.1:55432` 唯一监听、SCRAM、专用角色/数据库和真实 SQL 探针。Linux/Docker 一致性验证仍属于后续发布门禁。

## 回滚条件

若官方 PostgreSQL 18.4 Windows 安装器不能在当前 Windows 版本正常安装或无法满足回环/SCRAM 验证，停止环境安装并记录证据；不使用 SQLite 替代并发测试，也不宣称发布通过。

## 关联记录

- 设计：`docs/superpowers/specs/2026-07-15-windows-native-postgres-environment-design.md`，提交 `d506c8c`。
- 端口锁定：提交 `51c1583`。
- 实施计划：`docs/superpowers/plans/2026-07-15-windows-native-postgres-environment.md`，提交 `85c04d1`。
