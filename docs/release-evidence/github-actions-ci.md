# GitHub Actions 分层 CI：远程验证证据

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
