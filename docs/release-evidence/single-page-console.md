# 单页运营控制台：本地验证证据

验证日期：2026-07-18（Asia/Shanghai）

## 已实现范围

- Vite + React + TypeScript 单页控制台，开发期 `/api` 请求代理到本机 FastAPI。
- 演示 JWT 仅保存在 `DemoSession` 的内存字段；不写入 localStorage、sessionStorage、URL 或页面文本。
- operator 创建库存补货处置；四种演示角色可读取；只有 approver 能看到可用的批准/驳回操作。
- 审批请求只从后端详情中的六个 `approval_binding` 字段构造。
- 审计采用携带 Authorization 的 fetch SSE 快照回放，支持 `Last-Event-ID`、按 sequence 去重；初始连接之外最多重连三次。
- 页面明确标示“发布门禁：CLOSED”，并声明未实现生产 IAM、SSO、实时订阅或公开部署。

## 本次真实命令与结果

在 `web/` 目录执行：

```text
npm run test:run
9 个测试文件、15 个测试通过。

npm run build
TypeScript 构建与 Vite 生产构建通过。
```

前端闭环测试只模拟浏览器 `fetch` 边界，覆盖“获取内存 token → 创建处置 → 读取详情 → 回放 SSE 快照”的客户端编排；它不是 FastAPI、PostgreSQL 或 Docker 的端到端证明。后端真实证据仍见同目录的库存补货、JWT/RBAC 和 SSE 文档。

## 同轮后端回归门禁

为确认前端加入没有扰动既有 Python 工程，本轮在仓库根目录实际执行并通过：

```text
uv run pytest -q
325 passed in 91.25s

uv run ruff check .
All checks passed!

uv run ruff format --check .
91 files already formatted

uv run mypy src
Success: no issues found in 46 source files
```

这些是本机回归结果；它们不把本地演示改写为生产发布证明。

## 已知限制

- 这是本机单页演示，不是公开部署或生产可用性声明。
- SSE 为持久化审计快照回放，不是 Redis/WebSocket 推送。
- 演示 token 端点及本地角色模型不能替代生产 IAM/SSO。
