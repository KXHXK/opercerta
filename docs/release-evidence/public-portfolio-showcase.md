# OperCerta 公开专题部署证据

## 2026-07-30 安全头发布候选 Preview

- 候选分支：`chore/release-readiness-20260730`；候选源码提交：`4cd1e8563a2a8967775abc360ff2cd391b1012d5`。
- 发布前门禁：发布/静态/索引定向契约 `18 passed`，文档索引 `115/115`，仓库安全扫描通过；前端 `19` 个测试文件、`60` 条用例通过，TypeScript/Vite production build 成功。
- 新电脑首次执行 Windows `netlify deploy --build` 及 `--dir` 失败：Windows Netlify CLI 调用了 Windows npm，但 `web/node_modules` 由 WSL 安装，导致 `tsc` 不可用。失败 deploy 为 `6a6b1742b0a84f106a2d6c02`、`6a6b17b006114307809dc315`；它们未替换 production。
- 修正方式不是复制 OAuth token 或重新生成未验证产物，而是复用已在 WSL 通过测试和构建的 `web/dist`，执行 `netlify deploy --dir web/dist --no-build`。
- 成功 Preview deploy：`6a6b17cf496c38056f737264`；不可变地址：<https://6a6b17cf496c38056f737264--opercerta-kxh.netlify.app>。
- 真实 HTTP 核验：`GET /`、`GET /console`、`GET /api/v1/auth/demo-token` 均为 `200 text/html`。第三项证明该站仍是 SPA 静态回退，没有伪装公开业务 API。
- Preview 已实际返回 `Content-Security-Policy`、`Cross-Origin-Opener-Policy`、`Permissions-Policy`、`Referrer-Policy`、`X-Content-Type-Options` 和 `X-Frame-Options`；Preview 自带 `X-Robots-Tag: noindex`，符合预览环境预期。
- 线上 JS 为 `index-Ckvsq13U.js`，大小 `254,845 bytes`，SHA-256 为 `dcd31a4d6e1c53f06c1a16cc6fb65f7f5d347926a078dc56fe08606c8052abb1`，与本地已验证产物完全一致。
- 在该核验时点仅完成 Preview，尚未替换 production。FastAPI、LangGraph、MCP、PostgreSQL、Redis 与模型密钥仍未部署到公网；OperCerta 原产品 release gate 保持 `CLOSED`。

### 主线门禁与 Production 晋级

- [PR #17](https://github.com/KXHXK/opercerta/pull/17) 全部必需检查通过，并以普通 merge commit `b6aa5fa13c7645bd3351092fc23b6c3e132a284d` 合入 main。
- [main run 30539160493](https://github.com/KXHXK/opercerta/actions/runs/30539160493) 五项全部成功：完整后端 `667 passed`、三业务契约 `1 passed`、冻结 Agent 评测 `9/9`、前端 19 文件/60 条，以及真实 Compose 构建、数据库副作用、API/MCP 重启恢复和清理。
- Windows CLI 直接执行 `netlify deploy --prod` 返回 `403 Forbidden`，没有替换线上版本。站点 owner、active 状态和 `prevent_non_git_prod_deploys=false` 均经 API 核对；随后使用 Netlify 官方、可回滚的 `restoreSiteDeploy` 把已验证 Preview 晋级，没有重传或重新构建产物。
- 当前 production deploy：`6a6b17cf496c38056f737264`；发布时间：`2026-07-30T11:54:34.258Z`；上一 production `6a6631d24958714a43ddc508` 保留为回滚目标。
- 生产根页、`/console` 与 `/api/v1/auth/demo-token` 均为 `200 text/html`；六项安全响应头全部存在。线上 JS 仍为 `254,845 bytes`，SHA-256 仍为 `dcd31a4d6e1c53f06c1a16cc6fb65f7f5d347926a078dc56fe08606c8052abb1`。
- 这里的 production 仅指 Netlify 静态站生产别名。公网 FastAPI、LangGraph、MCP、PostgreSQL、Redis、模型密钥和生产身份仍未发布，OperCerta 产品 release gate 继续 `CLOSED`。

## 2026-07-27 单根 Agent 版本生产替换

- 对应源码合并提交：`609f8f7dcbfbadb9d12f4371cf49815d48884a4e`；PR：[KXHXK/opercerta#8](https://github.com/KXHXK/opercerta/pull/8)。
- 发布前本地契约：4 个发布相关测试文件、21 条测试通过；TypeScript/Vite production build 成功。
- Preview deploy：`6a660a8f77aa692302ad00aa`；浏览器真实读取到三业务、受控 Agent 链路、可靠性证据与诚实边界。
- Production deploy：`6a6631d24958714a43ddc508`；生产 URL：<https://opercerta-kxh.netlify.app>；[部署日志](https://app.netlify.com/projects/opercerta-kxh/deploys/6a6631d24958714a43ddc508)。
- `GET /`、`GET /console`、独立 deploy 根页和 `GET /api/v1/auth/demo-token` 均返回 `200 text/html`，共同证明静态 SPA 可访问且没有伪装公开 API。
- 线上 JS：`index-Ckvsq13U.js`；SHA-256：`dcd31a4d6e1c53f06c1a16cc6fb65f7f5d347926a078dc56fe08606c8052abb1`，与发布前本地候选完全一致。
- 回滚目标：上一 production deploy `6a5e0bb5563acf4706a09c0d`。Netlify 保留不可变 deploy URL，无需改写 Git 历史。
- 能力边界：本轮只替换公开静态专题；没有发布 FastAPI、LangGraph、MCP、PostgreSQL、Redis 或模型密钥，也没有把静态回退描述成业务接口。

**核验日期：** 2026-07-18

**证据范围：** 本地 WSL2 Ubuntu、Docker Compose、Vite 控制台、合成库存数据，以及 Netlify 静态生产部署

**静态专题地址：** <https://opercerta-kxh.netlify.app>

**发布状态：** 静态专题已部署；OperCerta 原产品 release gate 仍为 `CLOSED`

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

## Netlify 生产部署验证

- Netlify site id：`c9a55c47-8ee1-4d38-be4d-aeb8355cfa74`。
- 最终生产 deploy id：`6a5ba2ebacf340a5a0649f91`。
- 部署日志：<https://app.netlify.com/projects/opercerta-kxh/deploys/6a5ba2ebacf340a5a0649f91>。
- `GET /` 与 `GET /console`：均为 `200 text/html`。
- 线上标题：`OperCerta | 可恢复运营 Agent`。
- 线上资源指纹：`index-CUPW156B.js`、`index-0pGkm15M.css`，与本次功能工作树构建产物一致。
- 两张证据图均为 `200 image/png`。
- `GET /api/v1/auth/demo-token` 返回 `200 text/html`，证明 Netlify 只做 SPA 静态回退，没有伪装或暴露 API。

首次生产部署虽返回成功，但线上仍是旧控制台，资源指纹也与功能工作树不符。`netlify build --dry --debug` 证明 Netlify 把 Git 公共根目录解析到主 checkout，并将相对 `web/dist` 指向主工作区。修复没有修改业务代码，而是对已验证的功能工作树产物执行显式 `--dir=web/dist --no-build` 部署；随后用 HTTPS 响应类型和资源指纹重新核验。

## 个人作品集入口验证

- 在 `D:\CODEX\resume\portfolio\app\page.tsx` 的现有用户改造基础上追加第 04 张 OperCerta 卡片，外链使用本页记录的真实 HTTPS 地址。
- 入口实现前的契约探针按预期因名称、URL 和安全外链属性缺失而失败；实现后同一契约通过。
- 作品集原 `npm run build` 在 Windows 因 POSIX 环境变量语法失败；该失败在入口实现前已经复现。仅对当前子进程指定 Git Bash 为 npm script shell 后，原 build script 完整通过。
- 构建后的 SSR HTML 真实包含 `OperCerta`，且同一外链带有正确 URL、`target="_blank"` 与 `rel="noreferrer"`。
- 作品集工作区此前已有大量用户未提交改动，`app/page.tsx` 也是整文件未提交重写。本轮没有暂存或提交该文件，避免吸收用户已有 hunk；作品集尚未生产部署。

## 最终本地门禁

2026-07-19 对当前功能工作树从头执行完整门禁，观察结果如下：

- `uv run pytest -q`：`342 passed in 65.94s`。
- `uv run ruff check .`：`All checks passed!`。
- `uv run ruff format --check .`：105 个文件格式正确。
- `uv run mypy`：50 个源文件无问题。
- `uv run python scripts/verify_repository_safety.py`：通过。
- `npm run test:run`：11 个测试文件、24 条测试通过。
- `npm run build`：成功；JS/CSS 指纹仍与已部署 Netlify 产物一致。

第一次完整执行在 342 条后端测试通过后被 Ruff `I001` 阻断；根据 `ruff check --diff` 只删除测试文件顶部多余空行，再从头重跑以上整条门禁。这里记录的是修复后当前工作树的结果，不复用修改前的部分通过结果。

## GitHub PR 与 main 远程门禁

- 功能分支 head：`811885e67a7ad0a6f53be6723deaea8e0dae50ec`。
- [PR #4](https://github.com/KXHXK/opercerta/pull/4) 已合并；PR run [29652818349](https://github.com/KXHXK/opercerta/actions/runs/29652818349) 结论为 `success`。
- PR run 的 `repository-safety`、`python-quality`、`backend-tests`、`frontend` 四个快速 job 全部成功；`compose-smoke` 按 workflow 条件跳过。
- 合并提交：`0f262e0d08044ceb6e6408443af90f21a8a4344b`。
- main push run [29652991288](https://github.com/KXHXK/opercerta/actions/runs/29652991288) 结论为 `success`；五个 job 全部成功。
- main 的 `compose-smoke` job [88102487952](https://github.com/KXHXK/opercerta/actions/runs/29652991288/job/88102487952) 成功，证明当前合并提交通过 workflow 中已有的 Compose 业务 smoke、API/MCP 重启恢复与无条件清理步骤。

以上远程状态通过 GitHub API 读取实际 PR、run 和 check-run 结果，不是根据本地结果推断。个人作品集仍未生产部署；演示视频录制仍是用户后续动作，当前没有文件或证据声称已经录制。

## 边界

公开页面展示的是本地合成数据流程证据，不是在线生产后端。页面不会连接 API、MCP、PostgreSQL 或 LangGraph，也不提供公开写入口。个人作品集入口已完成本地构建但尚未部署。生产 IAM/SSO、设备场景、真实模型评测、完整浏览器 E2E、公开 API 与原设计发布门禁仍未完成；因此 `OperCerta production release gate: CLOSED`。
