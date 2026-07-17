# Single-Page Operations Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `web/` 提供美观、可读、可操作的 OperCerta 单页库存补货控制台。

**Architecture:** Vite 提供 React 19 + TypeScript 单页应用与 `/api` 开发代理；内存 session 层持有演示 JWT；类型化 API client 负责 REST、带 Authorization 的 fetch SSE 解析、一次 token 续签与最多三次回放重连。页面由控制区、详情/审批区、审计时间线和限制说明区组成。

**Tech Stack:** React 19、TypeScript、Vite、Vitest、Testing Library；复用既有 FastAPI JWT/REST/SSE 契约。React 19 已是官方稳定版本，Vite 官方发布页确认 Vite 7；实施时锁定实际安装版本与 lockfile，不伪造版本号。

## Global Constraints

- 仅实现库存补货本地演示；不接生产 IAM、SSO、多页路由、Redis 实时订阅、设备或真实模型。
- token 只在内存；不写入 Web Storage、URL、日志或页面文本。
- SSE 使用 `fetch` 流而非 EventSource，以传递 Authorization；只回放持久化快照，最多重连三次。
- Vite `/api` proxy 解决本地同源开发；不为首版新增宽松 CORS。
- 保持发布门禁 `CLOSED`；所有业务数据为合成数据。

---

### Task 1: Web 工程与视觉基础

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`
- Create: `web/src/main.tsx`, `web/src/styles.css`, `web/src/App.tsx`
- Test: `web/src/App.test.tsx`

**Interfaces:** 产出 `App` 根组件、`npm run dev/test/build` 命令及到 `http://127.0.0.1:8000` 的 `/api` proxy。

- [ ] **Step 1: 写失败渲染测试**

```tsx
it("renders the OperCerta console shell", () => {
  render(<App />)
  expect(screen.getByText("OperCerta｜智能运营处置 Agent")).toBeInTheDocument()
  expect(screen.getByText("发布门禁：CLOSED")).toBeInTheDocument()
})
```

- [ ] **Step 2: 运行 RED**

Run: `cd web && npm test -- --run App.test.tsx`  
Expected: FAIL，`App` 或测试运行环境尚不存在。

- [ ] **Step 3: 实现最小工程与壳层**

```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
})
```

实现石墨背景、蓝绿强调、语义状态色、响应式三栏/单列 CSS；顶部呈现合成数据、本地演示 JWT 与 CLOSED 标识。

- [ ] **Step 4: 运行 GREEN 与构建**

Run: `cd web && npm test -- --run App.test.tsx && npm run build`  
Expected: PASS，生成 `web/dist/`。

- [ ] **Step 5: 提交**

```bash
git add web
git commit -m "feat: scaffold operations console"
```

### Task 2: 内存身份与类型化 API client

**Files:**
- Create: `web/src/api/contracts.ts`, `web/src/api/client.ts`, `web/src/api/client.test.ts`
- Create: `web/src/session.ts`, `web/src/session.test.ts`

**Interfaces:** `DemoRole`、`ApiClient.createOperation`、`getOperation`、`submitApproval`、`issueToken`；`DemoSession` 仅在内存返回 `authorizationHeader()`。

- [ ] **Step 1: 写失败 API tests**

```ts
it("copies the six approval-binding fields and never persists a token", async () => {
  await client.submitApproval("operation-id", detail, "approved")
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/approval"), expect.objectContaining({
    headers: expect.objectContaining({ Authorization: "Bearer memory-only" }),
  }))
  expect(localStorage.length).toBe(0)
})
```

- [ ] **Step 2: 运行 RED**

Run: `cd web && npm test -- --run src/api/client.test.ts src/session.test.ts`  
Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 API 边界**

实现严格 TypeScript response 类型、稳定 401/403/404/409/422/503 中文映射；收到 401 时仅重新换取当前角色 token 一次并重试一次。审批 payload 只由 `detail.approval_binding` 的六字段构成。

- [ ] **Step 4: 运行 GREEN**

Run: `cd web && npm test -- --run src/api/client.test.ts src/session.test.ts`  
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add web/src/api web/src/session.ts web/src/session.test.ts
git commit -m "feat: add console api client"
```

### Task 3: SSE fetch 回放与时间线

**Files:**
- Create: `web/src/audit-stream.ts`, `web/src/audit-stream.test.ts`
- Create: `web/src/components/AuditTimeline.tsx`, `web/src/components/AuditTimeline.test.tsx`

**Interfaces:** `readAuditSnapshot(operationId, afterSequence, authorization)` 返回有序 `AuditEvent[]`；解析 SSE `id/event/data`，只保留更大 sequence，网络中断最多重试三次。

- [ ] **Step 1: 写失败 SSE 测试**

```ts
it("deduplicates sequence and retries a broken snapshot at most three times", async () => {
  const events = await readAuditSnapshot("id", 2, "Bearer memory-only")
  expect(events.map((event) => event.sequence)).toEqual([3, 4])
  expect(fetch).toHaveBeenCalledTimes(3)
})
```

- [ ] **Step 2: 运行 RED**

Run: `cd web && npm test -- --run src/audit-stream.test.ts`  
Expected: FAIL，解析器不存在。

- [ ] **Step 3: 实现解析器和时间线**

以 `fetch` 的 body reader 解码 SSE，携带 `Authorization` 和可选 `Last-Event-ID`；仅渲染安全 event type、sequence 与 JSON data。时间线用语义状态图标与文本，不用颜色作为唯一信息。

- [ ] **Step 4: 运行 GREEN**

Run: `cd web && npm test -- --run src/audit-stream.test.ts src/components/AuditTimeline.test.tsx`  
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add web/src/audit-stream.ts web/src/components/AuditTimeline.tsx web/src/**/*.test.ts*
git commit -m "feat: show audit event timeline"
```

### Task 4: 业务控制台闭环与门禁

**Files:**
- Create: `web/src/components/OperationControls.tsx`, `OperationDetail.tsx`, `ApprovalPanel.tsx`, `ProjectBoundary.tsx`
- Modify: `web/src/App.tsx`, `web/src/styles.css`, `README.md`, `DOCUMENT_INDEX.md`
- Create: `docs/release-evidence/single-page-console.md`

**Interfaces:** `App` 组合角色选择、SKU 创建、operation ID 读取、详情/审批、SSE 时间线和限制说明；approver 外角色不能出现可用审批按钮。

- [ ] **Step 1: 写失败组件测试**

```tsx
it("shows approval only to approver and disables a second decision", async () => {
  render(<App />)
  await userEvent.selectOptions(screen.getByLabelText("演示角色"), "approver")
  expect(screen.getByRole("button", { name: "批准" })).toBeEnabled()
  await userEvent.click(screen.getByRole("button", { name: "批准" }))
  expect(screen.getByRole("button", { name: "批准" })).toBeDisabled()
})
```

- [ ] **Step 2: 运行 RED**

Run: `cd web && npm test -- --run src/App.test.tsx src/components`  
Expected: FAIL，业务组件不存在。

- [ ] **Step 3: 实现最小闭环**

实现既有 SKU 选择、operation ID 手工读取、详情卡片、六字段绑定审批、加载/空态/错误态、项目限制区和响应式布局；不显示密钥或内部错误。

- [ ] **Step 4: 运行完整门禁并记录真实证据**

Run: `cd web && npm test -- --run && npm run build; cd .. && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`  
Expected: 全部退出码 0；文档只记录实际通过数量与本地范围。

- [ ] **Step 5: 提交**

```bash
git add web README.md DOCUMENT_INDEX.md docs
git commit -m "feat: add single page operations console"
```

## 自审

- 覆盖规格中的内存 token、同源代理、创建/读取/审批、fetch SSE、三次重连、视觉状态、响应式与限制说明。
- 未引入生产 IAM、多页路由、Redis 订阅、真实模型或公开部署。
- 本计划只依赖本计划定义的前端模块与既有已验证 API 契约；没有 TODO/TBD 占位步骤。
