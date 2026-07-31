# GitHub Actions 分层 CI：远程验证证据

## 2026-07-31 双门禁收口 PR #23 与 main 总门禁

- [PR #23](https://github.com/KXHXK/opercerta/pull/23) 的 `repository-safety`、`python-quality`、`backend-tests`、`frontend` 全部成功，`compose-smoke` 按 PR 事件规则跳过；随后以普通 merge commit `7bb9ecda8170ed8752049331f5597ea2368d77b1` 合入 main。
- 对应 [main run 30629194460](https://github.com/KXHXK/opercerta/actions/runs/30629194460) 五项 job 全部为 `success`。
- `backend-tests` 通过完整 671 条后端测试、三业务固定契约和冻结 Agent 安全/恢复评测 `9/9`；`frontend` 通过 19 个测试文件/60 条用例和 Vite production build。
- `python-quality` 通过 Ruff、format 与 mypy；`repository-safety` 通过双语公开文档凭据扫描、固定 Action 和权限边界检查。
- `compose-smoke` 在干净 GitHub Linux 环境使用 Dockerfile 固定的 uv `0.11.28` 构建镜像，启动 PostgreSQL、Redis、MCP 和 API，验证三业务 Agent 轨迹与数据库副作用，重启 API/MCP 后完成 recovery-only 验证，并删除隔离资源。
- 本次远程结果关闭本机 GHCR 拉取超时导致的容器构建证据缺口。它证明本地可复现单节点 Agent MVP，不证明公网交互、生产 IAM、高可用或 SLA。
- 当前 `Showcase Release gate: AWAITING_OWNER_VALIDATION`；`Product Release gate: CLOSED`。

## 2026-07-31 最终证据合并与 Showcase Pre-release

- [PR #18](https://github.com/KXHXK/opercerta/pull/18) 已合入 main `298fc5978a56961d36e73888f4ae73017e302715`，未绕过检查。
- [main run 30541088053](https://github.com/KXHXK/opercerta/actions/runs/30541088053) 的 `repository-safety`、`python-quality`、`frontend`、`backend-tests`、`compose-smoke` 五个 job 全部为 `success`。
- 远程门禁继续记录完整后端 `667 passed`、三业务固定契约、冻结 Agent 安全/恢复评测 `9/9`、前端 19 个测试文件/60 条用例和 Vite production build；`compose-smoke` 实际验证三业务数据库副作用、API/MCP 重启恢复并清理隔离资源。
- [Showcase 预发布 `v0.1.0-showcase.1`](https://github.com/KXHXK/opercerta/releases/tag/v0.1.0-showcase.1) 为非草稿 prerelease，tag 与 release target 均精确指向 `298fc59`。
- 本节证明可复现的求职静态展示和本地单节点 Agent 发布候选，不证明公网可写后端、生产 IAM、限流、备份、高可用、SLA 或产品级正式发布。

## 2026-07-30 发布准备 PR #17 与最新 main 总门禁

- [PR #17](https://github.com/KXHXK/opercerta/pull/17) 的 `repository-safety`、`python-quality`、`frontend`、`backend-tests` 全部成功，`compose-smoke` 按 PR 事件规则跳过；随后以普通 merge commit `b6aa5fa13c7645bd3351092fc23b6c3e132a284d` 合入 main，未绕过检查。
- 对应 [main run 30539160493](https://github.com/KXHXK/opercerta/actions/runs/30539160493) 的五个 job 全部为 `success`。
- 远程日志记录完整后端 `667 passed in 73.95s`、三业务契约评测 `1 passed in 8.61s`、冻结 Agent 安全/恢复评测 `9/9 passed`；前端 19 个测试文件、60 条用例和 Vite production build 均成功。
- `compose-smoke` 在隔离环境构建并启动 PostgreSQL、Redis、MCP、API，验证 Agent 轨迹与三业务数据库副作用，重启 API/MCP 后执行恢复检查，最后删除临时服务、网络和数据卷；总 job 用时约 1 分 10 秒。
- 本轮证明 main 的单节点发布候选和静态求职展示可晋级；不证明公网可写后端、生产 IAM、限流、备份、高可用或 SLA。

## 2026-07-30 换机收口 main 总门禁

- [PR #15](https://github.com/KXHXK/opercerta/pull/15) 以普通 merge commit 合入 main `42ba9744ca91b4d6e2ade7dd81d6a7752ec40a1c`，未强推、未绕过检查。
- 对应 [main run 30525556998](https://github.com/KXHXK/opercerta/actions/runs/30525556998) 的 `repository-safety`、`python-quality`、`frontend`、`backend-tests`、`compose-smoke` 五个 job 全部为 `success`。
- 远程日志记录完整后端 `665 passed in 75.48s`；三业务契约评测 `1 passed`；冻结 Agent 安全/恢复评测 `9/9 passed`。前端为 19 个测试文件、60 条用例全部通过，Vite production build 成功。
- `compose-smoke` 从隔离环境和新数据卷构建、启动服务，验证 Agent 轨迹与三业务数据库副作用，重启 API/MCP 后再验证恢复，最后无条件删除临时服务、网络和卷。
- 本机随后 fast-forward 到同一 main，并在不删除原开发卷的前提下恢复 PostgreSQL、Redis、MCP、API 四服务；四者均 healthy，readiness 返回 database/checkpoint/MCP 全部 ready。
- 以上证据关闭换机环境风险和单节点发布候选门禁；它不证明公网可写后端、生产 IAM、限流、备份、高可用或 SLA。

## 2026-07-27 PR #8 与 main 单根 Agent 总门禁

- [PR #8](https://github.com/KXHXK/opercerta/pull/8) head `d22d247db2329f81f927866dde4ff3f59d5a2f8d` 在合并前状态为 `CLEAN`；PR run [30201946098](https://github.com/KXHXK/opercerta/actions/runs/30201946098) 的 `repository-safety`、`python-quality`、`backend-tests`、`frontend` 全部成功，`compose-smoke` 按 PR 条件跳过。
- PR 以 merge commit `609f8f7dcbfbadb9d12f4371cf49815d48884a4e` 合入 `main`。
- 对应 main push run [30203438564](https://github.com/KXHXK/opercerta/actions/runs/30203438564) 结论为 `success`；`repository-safety`、`python-quality`、`backend-tests`、`frontend`、`compose-smoke` 五个 job 全部成功。
- `backend-tests` 实际依次通过完整后端、三业务契约评测和冻结 Agent 安全/恢复评测。
- `compose-smoke` 实际依次通过隔离环境创建、服务构建启动、Agent 轨迹与数据库副作用验证、API/MCP 重启、重启后 Agent 恢复和无条件资源清理。失败诊断步骤因总流程成功而按条件跳过。
- 以上是 GitHub Actions 新鲜远程事实，不用历史 run 或本地结果替代；它证明合并提交的单节点 CI/Compose 发布候选门禁，不代表生产高可用或公网写服务。

## 范围与仓库可见性

- 核验时间：2026-07-18（Asia/Shanghai）。
- 仓库：`KXHXK/opercerta`，GitHub API 返回 `visibility: PRIVATE`。
- 默认分支：`main`；远程地址：`https://github.com/KXHXK/opercerta`。
- 本证据不记录认证方式、OAuth scope、token、密码或本地凭据内容。

## PR 快速门禁

- PR：`#1`，地址：`https://github.com/KXHXK/opercerta/pull/1`。
- run ID：`29642286517`；commit：`265d611225341431cb94bf2a6b954155a40f0606`；event：`pull_request`；结论：`success`。
- run 地址：`https://github.com/KXHXK/opercerta/actions/runs/29642286517`。
- `repository-safety`、`python-quality`、`backend-tests`、`frontend` 均为 `success`。
- `compose-smoke` 为 `skipped`，符合只在 `main` push 或手动触发时运行的设计。

## main 完整门禁

- PR 合并 commit：`be00ee78e12b841bfd8d17f30f2ad4f9fdc15bf6`。
- run ID：`29642363033`；event：`push`；结论：`success`。
- run 地址：`https://github.com/KXHXK/opercerta/actions/runs/29642363033`。
- 五个 job 的远程结论均为 `success`：`repository-safety`、`python-quality`、`backend-tests`、`frontend`、`compose-smoke`。
- 远程日志实际结果：仓库安全扫描通过；Ruff 通过；104 个文件格式正确；mypy 检查 50 个源文件无问题；后端 `339 passed in 29.46s`；前端 9 个测试文件、15 条测试通过；`npm ci` 审计为 0 个漏洞；Vite 生产构建用时 205ms。
- `compose-smoke` 远程步骤依次成功：构建并启动服务、执行库存补货 smoke、重启 API/MCP、执行恢复健康验证、无条件删除服务、网络和 PostgreSQL volume。失败诊断步骤因 run 成功而按设计跳过。
- setup-uv 在并发 job 保存相同 cache 时产生一次非致命 reservation annotation；job 和整个 run 的结论仍为 `success`，未通过 `continue-on-error` 放宽门禁。
- 证据 PR `#2` 合并后，commit `4b392ed4eeb6998d4f2bd666880453c3bd4a275b` 的 main run `29642949588` 再次验证五个 job 全部 `success`，其中 `compose-smoke` 完成业务 smoke、API/MCP 重启、恢复验证和清理。

## 供应链与凭据边界

- workflow 顶层权限为 `contents: read`，所有 job 失败关闭，未配置 `continue-on-error`。
- Python 使用 `uv sync --frozen --all-groups` 和 `uv 0.11.28`；前端使用 `npm ci`；PostgreSQL service 使用 `postgres:18`。
- 四个远程 Action 固定到完整 commit SHA：
  - `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`
  - `actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1`
  - `actions/setup-node@820762786026740c76f36085b0efc47a31fe5020`
  - `astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990`
- PostgreSQL、JWT 与 Compose 只使用 GitHub runner 内的合成值；CI 不读取 `.env.local`、`.env.compose` 或真实本地凭据。
- 仓库安全扫描器只允许固定评测执行器中两行、各出现一次的攻击样本；未知凭据模式、数量变化、可变 Action、写权限、受禁跟踪文件和占位文本均失败关闭。

## 主分支保护

- 对 `main` 读取 branch protection 时，GitHub API 返回 HTTP 403：当前账户计划需要升级 GitHub Pro 或将仓库改为 Public 才能启用该 Private 仓库功能。
- 未把仓库改为 Public，未购买套餐，未写成已经启用保护，也未尝试削弱检查。
- 当前人工替代规则：所有改动通过 PR；合并前必须确认 `repository-safety`、`python-quality`、`backend-tests`、`frontend` 全绿；禁止 force push 和删除远程历史。`compose-smoke` 在合并后的 `main` run 验证。

## 已知限制

- 证据文档完成后的最终本地复验为：仓库安全扫描通过；后端 `339 passed in 75.85s`；Ruff 通过；104 个文件格式正确；mypy 检查 50 个源文件无问题；前端 9 个测试文件、15 条测试通过；Vite 生产构建用时 2.40s。该组数字与上文远程日志数字分开记录。
- 未实现 CodeQL/GHAS、漏洞扫描、自动部署、Caddy/HTTPS、生产 IAM、公开仓库或公开服务。
- 当前证据证明 Private GitHub Actions 分层 CI 与单节点 Compose 重启恢复门禁通过，不代表生产高可用、SLA 或公开上线。
- `OperCerta release gate: CLOSED`。
