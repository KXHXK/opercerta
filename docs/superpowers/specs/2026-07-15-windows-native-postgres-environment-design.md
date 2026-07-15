# Windows 原生 PostgreSQL 测试环境设计

## 决策

OperCerta 在当前 Windows 工作站改用原生 PostgreSQL，以解除可靠性内核 Task 3 和 Task 4 的集成测试阻塞。WSL2、Docker Desktop 与 Docker Engine 不再是本地开发前置条件。

## 目标与边界

- 目标：为审批竞态、幂等写入、迁移和后续 LangGraph PostgreSQL 检查点提供本机真实 PostgreSQL。
- 不变：仅实施 OperCerta；Python 依赖锁、TDD 顺序、数据库事务语义和发布门禁保持不变。
- 延后：Redis 服务、容器编排、Linux 容器一致性验证和任何发布动作。
- 禁止：不因本地环境替换而宣称发布通过；不启动其他项目。

## 方案比较

1. Windows 原生 PostgreSQL 18（采用）：立即提供真实事务和并发语义，避免当前 Windows 组件损坏阻塞开发。
2. 远程 Linux PostgreSQL：更接近部署环境，但需要额外服务器、网络和凭据，超出本机开发最小范围。
3. WSL2 + Docker：原先首选，但 `VirtualMachinePlatform` 和 WSL 组件因未修复的 Windows 组件存储损坏持续回滚。

## 本地架构

```text
uv / pytest on Windows
        |
SQLAlchemy + psycopg
        |
127.0.0.1:<approved-port>
        |
PostgreSQL 18 Windows service
        |
opercerta_test database
```

安装器使用官方 PostgreSQL Windows 发行渠道。数据库仅绑定本机回环地址；测试账户、数据库名、端口和连接串均从未提交的本地环境文件读取。数据库密码不得写入源码、文档、提交记录或聊天记录。

## 行为与验证

1. 先确认 PostgreSQL 版本、服务状态、监听地址与认证方式。
2. 创建专用本地测试数据库；迁移只允许作用于该数据库。
3. 将 Task 3 的旧前置条件从 `docker version` 替换为可连接的 PostgreSQL 实例和成功的 `alembic upgrade head`。
4. 使用独立连接重复运行审批竞态与幂等写入测试，继续以数据库约束和事务结果作为事实证据。
5. 最终 Linux/Docker 验证仍是发布门禁的一部分；未完成前，OperCerta release gate 保持 CLOSED。

## 失败处理

- 若 PostgreSQL 18 安装器不支持或无法在此 Windows 版本运行，停止安装并记录证据；不降级业务语义或以 SQLite 替代并发测试。
- 若端口被占用，选择新的回环端口并记录在本地环境文件；不暴露到局域网。
- 若迁移或并发测试失败，按 TDD 和系统化排障流程修复，不跳过数据库集成测试。
