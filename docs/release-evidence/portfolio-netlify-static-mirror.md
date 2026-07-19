# 作品集 Netlify 静态镜像发布证据

**核验日期：** 2026-07-19（Asia/Shanghai）

**生产地址：** <https://kxh-agent-portfolio.netlify.app>

**OperCerta 专题：** <https://opercerta-kxh.netlify.app>

**证据边界：** 只证明作品集静态镜像可公开访问并能跳转至 OperCerta 静态专题；不证明 OperCerta 公开后端、生产身份、公开写入或产品发布门禁通过。

**当前生产 deploy：** `6a5c986587eaef5b3156f49b`

## 决策与隔离

- `D:\CODEX\resume\portfolio` 继续作为唯一人工维护的 Vinext/Sites 源作品集。
- 独立镜像仓库为 `D:\CODEX\agent-portfolio\portfolio-netlify`，不包含 `.openai/hosting.json`、Netlify Function、API、数据库或密钥。
- 镜像只消费源作品集构建产物，执行 SSR 首页导出、静态资源复制与失败关闭验证。
- 新 Netlify site id 为 `bb607935-3c7f-45a2-b527-dcfd625d8ce7`，与既有 `opercerta-kxh` 站点独立。

原计划镜像路径位于 `D:\CODEX\resume\portfolio-netlify`。实施时受限权限环境无法稳定写入该目录，因此把已有镜像工作复制到工作区内的独立仓库继续，没有删除原目录或覆盖源作品集。规格和计划已同步记录这一环境修订。

## TDD 与本地导出证据

Windows Node.js `24.18.0` 直接启动 `npm.cmd` 返回 `spawn EINVAL`。诊断对照证明：

- `spawnSync("npm.cmd", ...)` 返回 `EINVAL`；
- `shell: true` 可运行但产生 Node `DEP0190` 安全警告；
- 使用当前 `node.exe` 直接执行 npm CLI JavaScript 入口可正常返回 npm `11.16.0`。

回归测试先因待实现的 `resolveNpmInvocation` export 缺失而退出 1，随后最小实现改为 Windows 上执行 `node.exe <npm-cli.js> run build`。最终：

- `npm test`：6 条通过；
- `npm run verify`：6 条测试再次通过，源作品集 Vinext 构建与静态导出成功；
- `dist`：15 个文件；
- HTML 中 OperCerta 精确 URL：1 次；
- 本地资源引用：7 个；缺失资源：0；
- `git diff --check`：通过。

镜像仓库的原子提交：

- `3438a48`：定义静态镜像导出契约；
- `4fe90aa`：实现已验证的静态镜像写入；
- `97a7ce7`：实现真实源构建与 SSR 导出，并修复 Windows npm 启动；
- `d62d878`：记录发布、回滚与边界。

## Netlify 两阶段发布

WSL Ubuntu 中没有 `netlify` 命令。Windows 端 Netlify 会话已登录团队 `KXH`，因此使用 npm registry 当时返回的 `netlify-cli@26.2.0` 通过一次性 `npx` 执行，没有全局安装。

### Preview

- deploy id：`6a5c814643be8e4160b17def`
- draft URL：<https://6a5c814643be8e4160b17def--kxh-agent-portfolio.netlify.app>
- 部署日志：<https://app.netlify.com/projects/kxh-agent-portfolio/deploys/6a5c814643be8e4160b17def>
- 公网探针：`200 text/html; charset=UTF-8`
- 标题：`KXH — AI Agent / 大模型应用开发工程师`
- OperCerta 精确 URL 与 `target="_blank"`、`rel="noreferrer"`：通过

### Production

- deploy id：`6a5c8184ffb46a40d1b49b6d`
- production URL：<https://kxh-agent-portfolio.netlify.app>
- unique deploy URL：<https://6a5c8184ffb46a40d1b49b6d--kxh-agent-portfolio.netlify.app>
- 部署日志：<https://app.netlify.com/projects/kxh-agent-portfolio/deploys/6a5c8184ffb46a40d1b49b6d>
- 公网探针：`200 text/html; charset=UTF-8`
- 标题、OperCerta 精确 URL 与外链安全属性：通过
- 同轮 OperCerta 专题探针：`200 text/html; charset=UTF-8`
- 浏览器语义快照：页面正常渲染，包含导航、项目列表和第 04 张 `OperCerta` 卡片，卡片目标 URL 精确为 <https://opercerta-kxh.netlify.app>。

## 403 对照与问题解决

既有 Sites 地址 <https://kxh-agent-portfolio.sage-wren-5074.chatgpt.site> 在 2026-07-19 同轮公网探针中仍返回 HTTP 403。该事实证明“平台产生部署”与“匿名公网可访问”是不同门禁；没有足够平台侧证据时，不进一步猜测账户或边缘策略根因。

本轮解决方案不是重写源作品集，而是建立可重复执行的纯静态导出器，并用本地契约、preview、production、HTTP Content-Type、标题、资源存在性和浏览器渲染逐层验证。

## 回滚与剩余边界

- 回滚目标是本作品集站点的上一份已验证 `dist` 或对应 deploy；禁止部署到 `opercerta-kxh`。
- 当前为人工 CLI 发布，不是 Git 自动部署。
- 首次部署时联系邮箱仍是占位地址；2026-07-19 单页刷新已由用户明确提供并替换为公开邮箱和手机号，见下节追加证据。
- OperCerta 公开 API、生产 IAM/SSO、设备场景、集中告警、后端 HTTPS 和自动部署仍未完成。

`OperCerta production release gate: CLOSED`。

## 2026-07-19 单页刷新

- 删除内部 `href="#..."` 导航，生产 HTML 的 hash 链接数为 0；入口统一为 <https://kxh-agent-portfolio.netlify.app>。
- 项目顺序固定为 OperCerta、ForenTrail、SiteVerum、Federune。后三项只标记“规划中 · 未启动”，不提供无效项目链接。
- 公开联系信息更新为用户明确提供的邮箱和手机号；公开 GitHub 为 <https://github.com/KXHXK/opercerta>，GitHub API 确认仓库为 public。
- 源作品集渲染契约 3/3 通过；镜像失败关闭契约 8/8 通过；真实构建与静态导出成功。
- preview deploy：`6a5c92ca65ca5b75486b82d1`；production deploy：`6a5c986587eaef5b3156f49b`。
- 生产 URL 返回 `200 text/html; charset=UTF-8`，标题为 `KXH — AI Agent 工程作品集`，四项目顺序和联系信息通过。
