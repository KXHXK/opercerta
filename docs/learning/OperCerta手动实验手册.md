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
