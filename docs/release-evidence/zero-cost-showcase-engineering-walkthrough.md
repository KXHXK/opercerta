# 零成本公开专题与本地工程详解证据

核验日期：2026-07-20（Asia/Shanghai）  
功能分支：`feat/zero-cost-showcase-walkthrough`  
状态：本机发布候选与 Draft PR 快速门禁通过；PR 合并和 Netlify 生产替换尚未执行
生产发布门禁：`CLOSED`

## 目标与边界

本轮在不购买 VPS、不公开可写后端的前提下，将同一份 React 构建拆成三个明确职责：

- `/`：公开静态专题。只陈述库存补货、设备维修、作业异常恢复三条已验证合成业务，以及可靠性证据和未完成边界；不请求 API、不提供写按钮。
- `/engineering`：仅 Vite development 且 hostname 为 `localhost` 或 `127.0.0.1` 时渲染。提供 10 步请求链路、三业务差异、技术职责、真实事故复盘和本地掌握检查；公开主机不暴露。
- `/console`：真实本地控制台，连接本地 FastAPI/Caddy 后端执行 query、创建、审批、工单和审计演示。

页面未加入 AI/Codex 生成归因、旧公司材料、虚构指标、固定拖不动模块或伪造的公网交互。

## 实现提交

| 提交 | 内容 |
| --- | --- |
| `e3a78bc` | 展示事实和本地路由纯函数边界 |
| `129a6eb` | 三业务公开叙事、8 步路径与可靠性证据 |
| `666b518` | 暖色编辑式视觉、响应式与静态托管契约 |
| `1e57803` | localhost 工程详解、三业务矩阵与技术职责 |
| `540d60c` | 真实事故复盘与 localStorage 掌握检查 |

## 前端门禁

执行：

```powershell
cd web
npm ci
npm run test:run
npm run build
```

实际结果：

- npm 审计 122 个包，`0 vulnerabilities`；
- Vitest：16 个测试文件、40 条测试全部通过；
- TypeScript 与 Vite 构建通过，转换 41 个模块；
- 产物：`index.html` 0.57 kB（gzip 0.42 kB）、CSS 16.39 kB（gzip 4.09 kB）、JS 234.18 kB（gzip 75.77 kB）。

## 后端与仓库门禁

测试进程只从 ignored `.env.local` 加载 `OPERCERTA_DATABASE_URL`，没有导入真实模型变量。执行：

```powershell
uv sync --frozen --all-groups
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/verify_repository_safety.py
```

实际结果：

- 430 条测试全部通过，耗时 106.25 秒；
- Ruff lint 全部通过；
- 138 个文件格式一致；
- Mypy 检查 62 个源码文件，无问题；
- 仓库安全检查通过；
- `uv sync` 核对 92 个锁定包。

首次基线曾因测试命令整体注入 `.env.local` 而污染真实模型失败关闭用例。缩小为只加载数据库 URL 后恢复全绿；该问题与解决方法已记录到开发日志和面试案例集。

## Mock Compose 启动与恢复

使用功能工作树的 `scripts/verify_release_compose.sh`，临时复制 ignored Compose 配置，并在调用层显式设置：

- `OPERCERTA_MODEL_MODE=mock`；
- 模型地址、名称和 API Key 为空；
- 不调用真实 Kimi。

脚本从全新网络和数据卷构建并启动 PostgreSQL 18、Redis 8.8、bootstrap、MCP、API 和 Caddy；等待健康后执行三业务断言，再重启 API/MCP 并执行恢复断言。退出码为 0，最终观察到 PostgreSQL、Redis、MCP、API 健康，Caddy 暴露本地 18080/18443。退出 trap 清理容器、网络、数据卷和临时配置。

## 浏览器实机复核

在 Vite development server 上使用真实浏览器检查，不以组件测试替代布局和交互验证。浏览器自身注入的 `codex-browser-sidebar-comments-root` 被单独识别，不计入项目 CSS。

| 视口 | 路由 | 主标题字号 | 横向溢出 | 项目 fixed/sticky | 坏图 |
| --- | --- | ---: | --- | ---: | ---: |
| 1440×900 | `/` | 48 px | 无 | 0 | 0 |
| 1440×900 | `/engineering` | 57.6 px | 无 | 0 | 0 |
| 1440×900 | `/console` | 38.4 px | 无 | 0 | 0 |
| 768×900 | `/` | 36 px | 无 | 0 | 0 |
| 768×900 | `/engineering` | 38.4 px | 无 | 0 | 0 |
| 768×900 | `/console` | 24 px | 无 | 0 | 0 |
| 390×844 | `/` | 35.136 px | 无 | 0 | 0 |
| 390×844 | `/engineering` | 35.2 px | 无 | 0 | 0 |
| 390×844 | `/console` | 24 px | 无 | 0 | 0 |

补充观察：

- 三个页面均无浏览器 console warning/error；
- 公开专题两张本地证据图均加载成功；
- 工程页呈现 10 个链路按钮、10 个事故复盘折叠项、10 项技术职责和 4 个掌握检查；
- 第一项掌握检查勾选后刷新仍保持，证明 localStorage 恢复；验证结束后点击“重置本地进度”，4 项均恢复未勾选；
- 手机公开标题最初约 39 px，静态契约先 RED，随后收紧为约 35 px。

## 仍未完成

- Draft PR #6 已建立，但尚未人工批准合并；
- PR 事件不会运行 Compose smoke；合并后必须等待 `main` workflow 的 compose-smoke 通过；
- Netlify 生产专题仍是上一版，尚未用本分支构建产物替换；
- 作品集入口尚未同步新版专题事实；
- 公网可写 HTTPS 后端、生产 IAM/SSO、限流、防滥用、备份恢复和高可用仍未建设；
- Release Tag 与用户亲手演示/口述掌握检查仍待执行。

因此，本报告只能支持“零成本静态展示与本地工程详解已通过本机发布候选和 PR 快速门禁”，不能支持“生产系统已上线”或“新版页面已公开部署”。

## GitHub 远程门禁

功能分支相对刷新后的 `origin/main` 领先 22 个提交、落后 0 个提交，推送后建立 [Draft PR #6](https://github.com/KXHXK/opercerta/pull/6)。PR 明确包含此前尚未进入远程主线的三业务发布候选与本轮展示，不把 146 文件、13,919 行新增/528 行删除伪装成单纯视觉改动。

首轮 [Actions run 29738331269](https://github.com/KXHXK/opercerta/actions/runs/29738331269) 对提交 `655f30d0a402277a604d5aef70daf6fab65bea01` 的结果：

| Job | 结果 | 覆盖 |
| --- | --- | --- |
| `repository-safety` | success | 仓库秘密与安全资产扫描 |
| `python-quality` | success | 冻结依赖、Ruff lint/format、Mypy |
| `frontend` | success | 冻结依赖、Vitest、TypeScript/Vite build |
| `backend-tests` | success | PostgreSQL 服务、完整后端测试、42 条三业务契约评测 |
| `compose-smoke` | skipped | 工作流只在非 PR 事件运行；合并后必须独立核验 |

该远程结果证明当前 PR 的快速门禁通过，不证明尚未执行的 `main` Compose smoke、Netlify 生产替换或生产发布门禁通过。
