# OperCerta 单页运营控制台设计

**状态：** 已确认，待实施  
**日期：** 2026-07-18  
**范围：** 当前库存补货后端的本地演示单页 React 控制台。  
**非范围：** 生产 IAM、注册、SSO、多页路由、操作列表、Redis 实时订阅、真实模型、设备场景与公开部署。

## 1. 目标与诚实边界

将既有 FastAPI、演示 JWT、绑定审批、工单结果与 SSE 审计回放串成一个可操作的最小闭环：创建补货操作、读取业务事实、按角色审批、查看事件时间线。所有数据均为现有合成数据。

控制台必须明确显示“本地演示 JWT，不是生产 IAM”和“事件流为持久化审计快照回放，不保证实时跨实例推送”。不得显示 token、密码、数据库/MCP 地址、traceback 或内部推理。

## 2. 技术与目录

- 在仓库根目录新增独立 `web/` React + TypeScript + Vite 项目。
- 前端只通过浏览器 HTTP 调用 `/api/v1/auth/demo-token`、`/api/v1/operations`、`/api/v1/operations/{id}`、`/approval` 与 `/events`；不访问 PostgreSQL 或 MCP。
- 开发时 Vite 将 `/api` 同源代理到本地 FastAPI；部署时由后续 Caddy 同源反向代理。首版不依赖未配置的跨域 CORS。
- token 只保存在运行时内存；刷新页面后重新获取演示 token，不写入 localStorage、sessionStorage、URL 或日志。

## 3. 单页布局与行为

| 区域 | 内容 | 行为 |
| --- | --- | --- |
| 左侧控制区 | 演示角色、SKU、创建按钮 | operator 发起 `SKU-LOW-001` 等既有合成 SKU；其他角色禁用创建并说明原因。 |
| 中部业务区 | operation ID、状态、证据、评估、计划、审批绑定、工单/错误 | 创建后查询详情；approver 可批准或拒绝，审批请求只从详情复制六项绑定字段。 |
| 右侧时间线 | SSE 审计事件 | 以 `fetch` 流携带 Authorization header 读取 SSE；首次读取全量快照，随后用最后 sequence 作为 `Last-Event-ID` 请求续传；按 sequence 去重排序，最多重连三次。 |
| 页底说明区 | 评测范围与限制 | 显示当前为合成数据、本地演示 JWT、SSE 快照回放及发布门禁关闭；链接到仓库内的评测/限制文档。 |

用户可输入 operation ID 读取既有演示操作。错误按已有稳定 API envelope 显示中文提示：401、403、404、409、422、503 均不显示内部字符串。

## 4. 数据流

1. 用户选择演示角色，向 demo-token 端点换取内存 token；若 API 返回 401，前端只为当前选择的演示角色重新换取一次 token 后重试原请求。
2. operator 创建 `create_work_order + inventory + sku` 请求，获得 operation ID。
3. 前端读取 operation detail；若处于 `awaiting_approval`，approver 可用详情的 approval binding 提交决定。
4. 前端以 `fetch` 读取 SSE body，并在每次详情读取后请求审计快照；将已见最大 sequence 传为 `Last-Event-ID`。连接中断时最多重试三次；客户端仅追加更大 sequence。
5. 后端返回终态、工单或安全错误；前端渲染结构化字段，不解释或推断隐藏业务状态。

## 5. 测试与验收

- 前端单元测试覆盖角色可见性、创建请求、六字段审批绑定、稳定错误映射、SSE 文本解析、sequence 去重和最多三次重连。
- API client 测试覆盖 Authorization header 仅在内存调用中传递，不写持久存储。
- `npm run build` 成功；现有 Python 全量 pytest、Ruff、格式与 mypy 不退化。
- 本轮只证明本地单页演示闭环，不对可用性、性能、生产安全、实时性或公开上线作任何声明。

## 6. 未来演进

首版将表单、API client、operation detail、approval panel 与 audit timeline 分为独立组件。演进到多页版本时，可增加登录、operation 列表、详情路由和评测页面，而无需改变 API、审批绑定或 SSE sequence 契约。
