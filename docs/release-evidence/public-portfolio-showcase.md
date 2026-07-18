# OperCerta 公开专题本地证据

**核验日期：** 2026-07-18

**证据范围：** 本地 WSL2 Ubuntu、Docker Compose、Vite 控制台、合成库存数据

**发布状态：** 静态专题尚未外部部署；OperCerta release gate 仍为 `CLOSED`

## 本地运行事实

使用当前源码重新构建并启动 `api`、`mcp`、`bootstrap` 与 PostgreSQL 18 服务：

```text
docker compose build api mcp bootstrap
docker compose up -d --force-recreate
GET http://127.0.0.1:8080/health/ready
```

readiness 实际返回 `status=ready`，`database`、`checkpoint`、`mcp` 均为 `ready`。随后在 `http://127.0.0.1:5173/console` 使用本地内存 JWT 完成一条合成库存补货流程。

## 观察到的业务结果

- 合成库存 SKU：`SKU-LOW-001`
- operation：`670eac76-2c52-48ce-9091-ecb2c55a236f`
- 推荐补货数量：`18`
- 审批决定：`approved`
- 最终 operation 状态：`completed`
- 唯一工单：`8289d0d0-e1a5-41ed-aec9-a049390f6d15`
- 工单状态：`created`
- 最终审计序列：`10`
- SSE 响应：`200 OK`，`content-type: text/event-stream`

以上 ID 和状态来自本次实际本地运行，不是预设占位或生产指标。

## 截图证据

| 文件 | 内容 | 尺寸 | SHA-256 |
| --- | --- | --- | --- |
| `web/public/evidence/console-approval-flow.png` | 等待审批、operation、推荐数量和 approver 操作 | 380×701 | `95fe1a13f1b385c9796bb42319af321656ac69f1f08227aef7cde4e3f629a093` |
| `web/public/evidence/console-audit-flow.png` | 审计序列 1–10 回放并结束于处置完成 | 365×673 | `fd0d01063ebfff0502943a9b8c77690236f0af91b2d61186dfd2e5ca84e19267` |

截图只包含本地合成业务数据，没有 token、密码、连接串、用户目录或数据库凭据。

## 本轮发现并解决的问题

1. 控制台详情读取成功但审计回放返回 404。API 日志证明旧容器镜像缺少当前源码中的 SSE 路由；重新构建当前镜像后，同一路由返回 `200 text/event-stream`。
2. Compose 服务在同一秒全部以 0 退出，PostgreSQL 日志显示收到管理员快速关机，而不是应用崩溃。根因是无持久 WSL 会话时 Linux 实例结束，`Live Restore` 又关闭，Docker daemon 随之停止。本次使用可追踪的临时 WSL 保活进程完成验证，结束后清理，不写入系统启动项。
3. Dockerfile 在依赖同步前复制 `README.md`，本轮文档变化使依赖层缓存失效，首次 `uv sync` 重新下载耗时较长。该问题记录为后续构建层优化，不在本证据任务中临时改动镜像结构。
4. 后端已返回唯一工单，但前端事实区没有显示工单编号。新增失败测试后只补充工单编号和状态展示；聚焦测试、前端全量测试和构建均重新通过。

## 自动化验证

- `npm run test:run -- --run src/showcase/ShowcasePage.test.tsx`：3 条通过。
- `npm run test:run`：11 个测试文件、24 条测试通过。
- `npm run build`：成功生成 Vite 静态产物。

## 边界

这是本地合成数据演示证据，不是在线生产演示。公开页面不会连接 API、MCP、PostgreSQL 或 LangGraph，也不提供公开写入口。Netlify 站点创建与生产静态部署仍需用户明确授权；生产 IAM/SSO、设备场景、真实模型评测、完整浏览器 E2E 与原设计发布门禁仍未完成。
