# OperCerta GitHub Actions 分层 CI 安全门禁设计

日期：2026-07-18（Asia/Shanghai）
状态：已确认，实施计划已创建
仓库边界：只实施 OperCerta

## 1. 目标

把当前已通过的本地后端、PostgreSQL、前端和 Docker Compose 门禁固化为 GitHub Actions 自动化证据，为后续 HTTPS、公开部署和作品集展示提供可信基线。

本阶段只建立 Private GitHub 仓库与 CI，不部署服务、不公开仓库、不配置域名或 HTTPS，不启动其他项目。`OperCerta release gate` 始终保持 `CLOSED`。

## 2. 已确认前提

- GitHub 作为远程仓库与 CI 平台。
- 远程仓库初始可见性为 Private；转为 Public 必须再次获得用户明确授权。
- 当前本地 `main` 提交 `f806138` 是 CI 工作开始前的可回滚基线。
- 当前仓库没有 Git remote、`.github` workflow 或 CI 专用安全扫描器。
- 完整后端测试需要 PostgreSQL；`tests/integration/conftest.py` 会执行 Alembic upgrade，并按需初始化 LangGraph PostgreSQL checkpointer。
- 前端冻结安装入口为 `npm ci`，验证入口为 `npm run test:run` 与 `npm run build`。
- Compose smoke 复用现有 `scripts/verify_compose.py`，不得另写一个更容易通过但不能证明业务闭环的替代脚本。

## 3. 官方版本核验

2026-07-18 通过各官方 GitHub repository release API 核验：

- `actions/checkout` 当前 release tag：`v7.0.0`；
- `actions/setup-python` 当前 release tag：`v6.3.0`；
- `actions/setup-node` 当前 release tag：`v7.0.0`；
- `astral-sh/setup-uv` 当前 release tag：`v8.3.2`。

本机已验证 Python `3.12.13`、uv `0.11.28` 与 Node `24.18.0`。前端锁文件声明支持 Node `^20.19.0 || ^22.12.0 || >=24.0.0`，因此 CI 使用 Python 3.12 和 Node 24。

实际 workflow 不使用可变 tag，必须在实施时重新解析上述 release 对应的完整 commit SHA，以 `owner/action@<40-hex-sha>` 固定；release tag 只写在 YAML 注释中供人工维护。

## 4. 工作流触发与并发

新增一个 `.github/workflows/ci.yml`：

- `pull_request`：运行仓库安全、Python 静态门禁、完整后端测试和前端门禁；不运行 Compose smoke。
- `push` 到 `main`：运行上述快速门禁，并追加 Compose smoke 与重启恢复。
- `workflow_dispatch`：允许人工运行全部门禁。
- 使用 workflow + ref 组成 concurrency group；同一 ref 有新提交时取消旧的未完成运行。

工作流顶层权限固定为 `contents: read`。不得授予 `write-all`、发布、部署、包写入或身份令牌权限。

## 5. 五个 job

### 5.1 `repository-safety`

运行仓库内受测试保护的安全扫描器，检查：

- Git 跟踪文件中不存在 `.env`、`.env.local`、`.env.compose`、`.pem`、`.key` 等禁止文件；允许 `.env.example` 与 `.env.compose.example`。
- 交接、发布证据和运行源码中不存在未完成占位文本或疑似真实凭据。
- 所有远程 `uses:` 都固定到 40 位十六进制 commit SHA；本地 `./` action 路径例外。
- workflow 不包含 `write-all` 或未经确认的写权限。

固定评测执行器中两处已审计的 tampered/wrong-issuer Authorization 攻击输入使用路径与模式都精确匹配的 allowlist。路径、模式或数量发生变化必须失败；不得通过拆字、放宽全目录或跳过扫描来制造绿色结果。

该扫描器是确定性防线，不宣称等价于高熵 secret scanner、GitHub Secret Scanning 或付费 GitHub Advanced Security。

### 5.2 `python-quality`

- Ubuntu hosted runner；Python 3.12。
- 固定 SHA 的 `setup-uv`，只缓存 uv 下载缓存。
- `uv sync --frozen --all-groups`。
- `uv run ruff check .`。
- `uv run ruff format --check .`。
- `uv run mypy src`。

不得缓存 `.venv`。

### 5.3 `backend-tests`

- 使用 PostgreSQL 18 service container 和健康检查。
- 使用仅存在于隔离 runner 中的固定合成用户、数据库和密码；不使用 GitHub Secret，也不连接任何真实环境。
- `OPERCERTA_DATABASE_URL` 使用无密码 URL，密码单独通过 runner 环境中的 `PGPASSWORD` 提供，避免失败 traceback 展开带密码连接串。
- 执行 `uv sync --frozen --all-groups` 后运行完整 `uv run pytest -q`。
- fixture 负责迁移与 checkpointer 初始化；不另建绕过真实测试入口的 CI 专用数据库测试集。

### 5.4 `frontend`

- Node 24；`npm ci`。
- npm cache 只缓存下载内容，不缓存 `node_modules`。
- 执行 `npm run test:run` 与 `npm run build`。
- 不上传 `dist/`，因为本阶段没有部署或发布 artifact。

### 5.5 `compose-smoke`

- 只在 `push` 到 `main` 或 `workflow_dispatch` 时运行，并依赖前四个 job 成功。
- 运行时生成被 `.gitignore` 排除的 `.env.compose`，其中只有 CI 合成值；文件不得上传为 artifact。
- 构建并启动 `postgres`、`bootstrap`、`mcp`、`api`。
- 运行 `scripts/verify_compose.py`，证明健康检查、补货创建、绑定审批、重复审批冲突、一条审批、一条工单和终态审计。
- 重启 API/MCP 后运行 `scripts/verify_compose.py --recovery-only`。
- 使用 shell trap/finally 语义保证 `docker compose down -v --remove-orphans` 在成功或失败时都执行。

Compose 失败日志只允许输出服务状态、健康状态和安全错误摘要；不得输出 `.env.compose`、环境变量全集、JWT、数据库 URL 或请求正文。

## 6. 失败、超时和证据

- 所有门禁失败关闭；禁止 `continue-on-error`。
- 每个 job 设置有限 `timeout-minutes`；PostgreSQL、Docker 或网络问题不得无限等待。
- 新提交取消同一 ref 的旧运行，旧 commit 的绿色结果不能替代当前 commit。
- 不上传数据库 dump、环境文件、token、完整正文或未审计容器日志。
- GitHub run URL、run ID、commit SHA、各 job 结论和实际测试数字在真实运行后写入本地发布证据；不得在运行前预填。
- Private Actions badge 不加入 README；仓库公开后是否添加 badge 另行确认。

## 7. 缓存与供应链

- uv/npm cache key必须包含相应 lockfile hash。
- 缓存仅用于下载层；冻结锁文件仍是安装事实来源。
- CI 不自动更新 `uv.lock` 或 `package-lock.json`。
- 本阶段不把 CodeQL、在线漏洞数据库、自动 Dependabot 合并或容器漏洞扫描设为必需门禁；它们依赖账号能力或新增第三方供应链，应在基础 CI 稳定后独立设计。

## 8. Private 仓库与主分支规则

1. 在获得用户对 GitHub 身份/owner 的确认后，创建名为 `opercerta` 的 Private 仓库。
2. 配置 `origin` 并推送当前干净 `main`；认证 token 不进入命令输出、Git、日志或文档。
3. 首次 CI 全绿后，再尝试为 `main` 启用 required status checks、禁止 force push 和禁止删除。
4. 个人项目不要求外部 reviewer，避免无人可审批；后续使用 feature branch + PR，并在检查全绿后合并。
5. 如果账号套餐或仓库类型不支持所需规则，记录实际限制与人工替代流程，不伪称保护已启用。

删除远程仓库、转为 Public、强制推送、改写历史或放宽门禁都需要新的明确授权。

## 9. 文件边界与 TDD

计划新增：

- `.github/workflows/ci.yml`；
- `scripts/verify_repository_safety.py`；
- `tests/unit/scripts/test_verify_repository_safety.py`；
- `tests/unit/runtime/test_ci_assets.py`；
- 实际 GitHub run 通过后新增 `docs/release-evidence/github-actions-ci.md`。

TDD 顺序：

1. 安全扫描器测试先因模块缺失 RED，再实现最小扫描器 GREEN。
2. Workflow 契约测试先因 `ci.yml` 不存在 RED，再实现 CI YAML GREEN。
3. 运行完整本地后端、静态、前端和构建门禁。
4. 创建 Private remote、推送、观察真实 Actions；失败必须按实际日志诊断，不通过降低断言或删除 job 制造绿色。
5. 只有真实远程 run 全绿后才写发布证据和更新交接。

## 10. 完成条件

- GitHub 仓库实际为 Private，`origin` 已配置且本地工作区干净。
- `repository-safety`、`python-quality`、`backend-tests`、`frontend` 在当前 commit 真实通过。
- `main` 或手动运行的 `compose-smoke` 真实通过业务 smoke 与重启恢复。
- workflow 的远程 Action 全部固定到完整 commit SHA。
- 主分支保护实际启用；或已记录账号能力限制与人工替代规则。
- 发布证据只记录真实 run ID、commit、命令输出和限制。
- README、文档索引、当前状态、交接和当日日志同步。
- `OperCerta release gate: CLOSED`；没有部署、公开仓库或启动其他项目。

## 11. 回滚

- 本地回滚基线：`f806138`。
- CI 代码问题通过新的回退提交撤销，不使用 `git reset --hard` 或强制改写历史。
- 远程 Actions 可通过回退 workflow 提交停止；删除 Private 仓库、移除远程或修改可见性不属于自动回滚，必须再次征得用户授权。
