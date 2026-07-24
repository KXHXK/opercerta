# OperCerta 手动实验手册

## 0. 安全规则

- 所有实验只用 `data/synthetic/` 合成数据和专用本地数据库。
- 不回显 `.env.local`、`.env.compose`、JWT、数据库密码或模型 key。
- 每次只改一个变量；先写下预期，再运行命令。
- 不把“命令退出码 0”直接当作业务成功，要查看 API 终态和数据库断言。
- 本手册记录的是可执行步骤；只有你亲手完成后，才在学习记录中写“已掌握”。

## 1. 环境与基线

在 PowerShell 检查 WSL2：

```powershell
wsl --status
wsl -l -v
wsl -d Ubuntu -- uname -a
```

进入 Ubuntu：

```bash
cd /mnt/d/CODEX/agent-portfolio/opercerta
docker info
docker compose version
git status --short
```

预期：Ubuntu 为 WSL2；Docker Server 可用；Git 只显示你已知的本地修改。

### 1.1 首次启动与 FastEmbed 缓存

`knowledge.search_sop` 使用固定的 `BAAI/bge-small-zh-v1.5`。首次创建空的 `fastembed_cache` volume 时，必须先允许 MCP 下载模型文件：

```bash
OPERCERTA_HF_HUB_OFFLINE=false docker compose up --build -d
docker compose ps
docker compose logs --tail=80 mcp
```

确认 MCP 为 `healthy` 后，模型文件会保留在命名 volume。此后才可以验证离线重启：

```bash
OPERCERTA_HF_HUB_OFFLINE=true docker compose up -d --force-recreate mcp api
docker compose ps
```

如果空 volume 第一次就设置 `OPERCERTA_HF_HUB_OFFLINE=true`，MCP 因找不到本地模型而失败是正确行为，不是 RAG 代码回归。不要删除已有 `fastembed_cache` 后仍声称“离线冷启动通过”；删除 volume 会同时删除缓存，需要重新执行在线预热。下载端点受网络环境影响时，只能在 ignored 本地配置中设置经过授权的镜像，不能把第三方地址或凭据写入产品 Compose。

## 2. 一条命令验证三业务闭环和重启恢复

保持在同一个 WSL 会话：

```bash
cd /mnt/d/CODEX/agent-portfolio/opercerta
docker compose up --build -d
python3 scripts/verify_compose.py
docker compose restart api mcp
python3 scripts/verify_compose.py --recovery-only
docker compose ps
```

预期：库存补货、设备维修、作业异常恢复批准后各一张工单；设备拒绝零工单；重复审批冲突；重启前的作业 operation 重启后仍等待审批。

实验结束：

```bash
docker compose down -v --remove-orphans
```

`-v` 会删除本次 Compose 的合成数据库 volume，所以只对本项目本次演示执行，不对未知项目或生产数据执行。

## 3. 浏览器完成一个完整业务

启动后端：

```bash
docker compose up --build -d
```

另开 PowerShell 启动前端：

```powershell
Set-Location D:\CODEX\agent-portfolio\opercerta\web
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173/console`：

1. 选择库存补货、设备维修或作业异常恢复；
2. 先点“查询状态”，确认 `completed`、零审批、零工单；
3. 点“创建处置”，确认进入 `awaiting_approval`；
4. 切换 approver，核对 binding 后批准；
5. 确认 `completed`、唯一工单和完整审计时间线；
6. 再次审批，预期得到冲突而不是第二张工单。

若审批窗口过期，控制台应显示“审批已过期”及重新创建处置的操作建议，而不是统一报“审批未提交”。这是安全终态：数据库保持零审批或零新工单，Trace run 结束而不是继续显示 `running`。

## 4. MCP 故障实验

基线健康后执行：

```bash
docker compose stop mcp
curl -i http://127.0.0.1:8080/health/ready
```

预期：readiness 返回 503；新建需要 MCP 取证的 operation 安全失败，不创建工单，响应不包含连接串、密码或 traceback。

恢复：

```bash
docker compose start mcp
docker compose restart api
python3 -c "from scripts.verify_compose import wait_for_ready; wait_for_ready()"
```

解释重点：liveness 只说明 API 进程活着，readiness 才检查关键依赖；MCP health 为 200 也不自动证明工具协议路径正确。

## 5. Redis 故障与缓存实验

先运行 2×2 矩阵：

```bash
bash scripts/run_performance_matrix.sh tmp/my-performance
```

读取 JSON，确认缓存关闭时每场景 10 次 MCP/0 hit，开启时 2 次 MCP/8 hit。然后在运行中的开发 Compose 停止 Redis：

```bash
docker compose stop redis
```

预期：已启动 API 的只读缓存访问失败时旁路 MCP；批准后复核本来就不读缓存。恢复 Redis 后重启 API：

```bash
docker compose start redis
docker compose restart api
```

不要用 5 次本机样本声称生产性能提升，只解释调用次数和安全边界。

## 6. 重启恢复实验

```bash
docker compose up -d
python3 scripts/verify_compose.py
docker compose restart api mcp
python3 scripts/verify_compose.py --recovery-only
```

观察 `tmp/compose-recovery-operation.txt` 只保存合成 operation UUID，不保存凭据。解释：PostgreSQL 业务表决定待恢复集合，LangGraph checkpoint 决定图从哪里继续。

## 7. 单变量规则修改实验

不要直接在主线长期保留实验修改。先备份合成规则：

```powershell
Set-Location D:\CODEX\agent-portfolio\opercerta
New-Item -ItemType Directory -Force tmp\learning | Out-Null
Copy-Item data\synthetic\task_recovery_policies.json tmp\learning\task_recovery_policies.json.bak
```

用编辑器把 `TASK-BLOCKED-001` 的 `maximum_retry_count` 从 3 改为 0，运行对应场景测试或 Compose 查询，预测它会从“建议恢复”变为策略失败/不允许恢复。比较实际结果与预测。

恢复原文件并确认差异消失：

```powershell
Copy-Item tmp\learning\task_recovery_policies.json.bak data\synthetic\task_recovery_policies.json -Force
git diff -- data/synthetic/task_recovery_policies.json
```

预期最后一条命令无输出。不要删除备份，直到确认文件已恢复。

## 8. 测试与固定评测

PowerShell：

```powershell
Set-Location D:\CODEX\agent-portfolio\opercerta
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/run_opercerta_evaluation.py --output-dir tmp\my-eval
.venv\Scripts\ruff.exe check .
.venv\Scripts\mypy.exe src
```

评测报告应包含 30 条库存、6 条设备、6 条作业用例，以及期望/实际工具、终态、审批、工单和审计事实。通过数不是唯一证据。

## 9. PostgreSQL 观察（只读）

不要把密码放在命令行。使用 Compose 内部数据库：

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT status, COUNT(*) FROM operations GROUP BY status ORDER BY status;"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT kind, COUNT(*) FROM work_orders GROUP BY kind ORDER BY kind;"
```

如果 shell 没有这些变量，可在容器内通过固定的 `.env.compose` 配置执行，但不要 `cat` 文件或回显变量。

## 10. 每次实验后的口头复盘

不用文档回答：改了什么变量、哪一层首先失败、为什么没有错误写工单、什么自动化证据支持结论、还不能声称什么。把不懂的词写入桌面 `agent术语.md`，把真实故障补充到 interview casebook。

## 11. Agent 核心人工闭环：按这条路径独立完成

以下步骤默认使用 Mock 模型保证可重复，但 RAG 使用真实 FastEmbed、pgvector 和 MCP；它不是 Real Kimi 通过证明。

### 步骤 1：启动并建立可重复基线

- **输入：** `OPERCERTA_HF_HUB_OFFLINE=true docker compose --env-file .env.compose up --build -d`，随后运行 `python3 scripts/verify_agent_compose.py`。
- **预期：** 三业务验证退出码 0；API、MCP、PostgreSQL、Redis healthy；知识检索有 citation。
- **为什么：** 先用自动化证明依赖、迁移、RAG、审批和数据库断言一致，再做人工 UI 操作。
- **常见错误：** 首次机器没有 FastEmbed 缓存却强制 offline；此时先在获准网络下完成一次模型缓存，不要伪造向量。
- **面试怎么讲：** “Mock 固定模型用于回归确定性，embedding 和数据库仍是真实组件；Real 模型另立报告。”

### 步骤 2：operator 提交有限业务表单

- **输入：** 在 `http://127.0.0.1:5173/console` 选择 operator；任选 `SKU-LOW-001`、`EQ-PUMP-001`、`TASK-BLOCKED-001`，动作选“创建处置”。
- **预期：** 请求进入 `awaiting_approval`，页面出现结构化 Goal，而不是开放聊天回复。
- **为什么：** 场景、动作和对象来自可信枚举，避免自由文本决定高风险写操作。
- **常见错误：** 只输入 message 而未选对象；严格 API 会返回 422，且不应创建 operation。
- **面试怎么讲：** “感知层接受有限表单，LLM 只编码受控目标，Harness 禁止对象漂移。”

### 步骤 3：查看 Goal、Tool、RAG 与 Observation

- **输入：** 展开 Agent Trace 和工具证据区。
- **预期：** 能看到 goal、场景白名单工具、`knowledge.search_sop`、citation reference、主体/规则 Observation 摘要；看不到 prompt、隐藏推理或 SOP 全文。
- **为什么：** MCP 提供实时事实，RAG 提供版本化知识，两者不可互相替代。
- **常见错误：** 把审计时间线当 Trace；audit 记录状态变更，Trace 才解释 Agent 节点。
- **面试怎么讲：** “Tool Calling 经过 schema、白名单、对象绑定、预算和类型化返回五层校验。”

### 步骤 4：approver 审批绑定计划

- **输入：** 切换 approver，核对 rule version、facts hash、plan hash 和参数后批准。
- **预期：** 审批身份来自 JWT；旧 binding、重复审批或已过期审批被拒绝。
- **为什么：** 人工批准的是一份证据快照，不是脱离上下文的布尔值。
- **常见错误：** 刷新后仍提交旧 binding，预期 409，不要绕过后端校验。
- **面试怎么讲：** “PostgreSQL 行锁让并发审批只有一个原子胜者。”

### 步骤 5：观察 Verifier

- **输入：** 批准后查看 Trace 中 verification/guardrail 节点。
- **预期：** 系统绕过 Redis 重新读取主体和规则，并给出 `proceed`；事实漂移会 `abort` 或 `escalate`，零工单或进入重新审批。
- **为什么：** 消除审批等待造成的 TOCTOU 风险。
- **常见错误：** 认为“批准后必须执行”；实际批准只在绑定事实仍成立时有效。
- **面试怎么讲：** “LLM 给复核建议，确定性 binding 比较决定是否允许执行。”

### 步骤 6：工单写入与回读

- **输入：** 查看终态和 work order 区，再刷新详情。
- **预期：** `completed`、一张类型正确的工单；重放仍返回同一 ID。
- **为什么：** idempotency key、唯一约束、事务和写后读共同提供 effectively-once 副作用。
- **常见错误：** 把它称为全链路 exactly-once；外部非幂等系统仍需 outbox/补偿。
- **面试怎么讲：** “图允许至少一次重放，数据库保证业务只产生一个有效结果。”

### 步骤 7：auditor 读取脱敏 Trace

- **输入：** 切换 auditor，重新打开同一 operation 的 `.../agent-trace` 视图。
- **预期：** sequence 连续，包含感知、模型、工具、RAG、规则、人工、执行与反馈摘要；operator/approver 权限范围不同。
- **为什么：** Trace 是持久化投影，重启重放通过 semantic key 去重。
- **常见错误：** 寻找模型完整思维链；产品明确不存储也不展示。
- **面试怎么讲：** “Trace、audit、OTel 分别服务解释、合规和运维。”

### 步骤 8：做 PostgreSQL 断言

- **输入：**

  ```bash
  docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT status, count(*) FROM operations GROUP BY status ORDER BY status"'
  docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT kind, count(*) FROM work_orders GROUP BY kind ORDER BY kind"'
  ```

- **预期：** UI 终态与数据库一致；目标 operation 只有一条审批和一张工单。
- **为什么：** 页面成功提示不是最终证据，业务表才是事实源。
- **常见错误：** 在宿主 shell 展开容器变量或把密码写入命令行。
- **面试怎么讲：** “测试同时断言 HTTP、图状态和数据库副作用，避免自己设计用例又只验证自己返回值。”

### 步骤 9：重启恢复

- **输入：** `docker compose restart api mcp`，再运行 `python3 scripts/verify_agent_compose.py --recovery-only`。
- **预期：** 重启前等待审批的 operation 仍可读且 Trace 不重复；四个服务最终 healthy。
- **为什么：** 业务表提供候选集合，checkpoint 提供节点位置，两者共同恢复。
- **常见错误：** 在 full 验证前先跑 `--recovery-only`，会缺少 marker；或误删 volume 后再期待恢复。
- **面试怎么讲：** “这是 A/B 进程实例恢复，不是同一进程内暂停后继续。”

### 步骤 10：运行冻结 Agent 评测

- **输入：** `python3 scripts/run_agent_evaluation.py --output-dir tmp/evals`。
- **预期：** 报告覆盖 9 类安全/恢复契约，并写入 `tmp/evals/opercerta-agent-v1-mock-report.json`。
- **为什么：** 用例引用真实 pytest node ID，包含数据库与重启证据，不按模型文案做主观打分。
- **常见错误：** 把 9/9 当生产准确率；它只是冻结合成契约回归。
- **面试怎么讲：** “评测由我设计，但每例公开 expected trajectory 和可执行测试定位，避免只报一个无法审查的分数。”
