# OperCerta 项目所有权与演示验收

## 1. 验收目的

本验收把“代码和文档已经完成”转化为“项目所有者能够独立运行、定位、解释和演示”。
自动化测试可以证明系统行为，但不能证明个人掌握。本文件的完成状态不得由 Codex 自动代签；
必须由项目所有者亲自操作、先回答，再由 Codex 根据实际输出纠错。

当前状态：`AWAITING_OWNER_VALIDATION`。

## 2. 通过规则

以下五组均为必做项，不使用可以被总分掩盖的加权评分：

1. 能独立启动和停止环境，并解释每个服务的职责。
2. 能完成一个库存短缺到补货工单的完整业务闭环。
3. 能沿真实代码解释 Agent、工具、审批和数据库边界。
4. 能执行一次重启恢复或幂等实验，并解释为什么不会重复写入。
5. 能完成 30 秒、3 分钟、10 分钟口述和 3–5 分钟录屏。

可以查命令帮助，但不能只照读答案。首次回答错误不算失败；纠正后必须重新脱稿回答。

## 3. 验收一：环境与服务

在 WSL2 中执行：

```bash
cd /mnt/d/CODEX/agent-portfolio/opercerta
docker compose -p opercerta-demo ps
curl -fsS http://127.0.0.1:8080/health/ready
```

本人必须解释：

- PostgreSQL 为什么是权威业务事实和 checkpoint 存储，而 Redis 不是；
- FastAPI、MCP、LangGraph 分别处于哪一层；
- 为什么 MCP 和数据库不直接暴露到公网；
- readiness 中每个依赖失败时系统应如何处理。

验收证据：命令输出、本人解释摘要、验收日期。

## 4. 验收二：完整库存业务

浏览器打开 `http://127.0.0.1:5173/console`，本人依次完成：

1. 使用 operator 扫描业务异常；
2. 打开库存短缺 case，启动 Agent 调查；
3. 观察 Goal、模型决策、MCP Observation、SOP citation 和 Agent Trace；
4. 切换 approver，核对绑定事实后批准；
5. 切换 auditor，确认新鲜事实复核、唯一工单、写后读和终态审计。

必须记录：

```text
operation_id:
work_order_id:
最终状态:
审批绑定中的三个关键字段:
Verifier 结论:
最后四个审计事件:
```

本人必须解释：为什么不能在扫描前直接创建写操作；为什么批准后仍要重新取证；为什么 LLM
不能直接写 PostgreSQL。

## 5. 验收三：代码链路

按实际执行顺序找到并解释下列入口：

1. `web/src/App.tsx`：页面状态和角色切换；
2. `src/opercerta/api/app.py`：协议、JWT/RBAC 和安全错误；
3. `src/opercerta/application/signal_detection.py`：异常信号感知；
4. `src/opercerta/application/controlled_agent_root_runner.py`：运行和恢复入口；
5. `src/opercerta/workflow/inventory_agent_root_graph.py`：唯一 LangGraph 生命周期；
6. `src/opercerta/infrastructure/langchain_model_gateway.py`：真实模型 Tool Calling；
7. `src/opercerta/agent/tool_policy.py`：工具 allowlist 和参数约束；
8. `src/opercerta/infrastructure/mcp_gateway.py`：MCP 传输与类型校验；
9. `src/opercerta/infrastructure/db/approval_repository.py`：审批竞态；
10. `src/opercerta/infrastructure/db/work_order_repository.py`：幂等写入。

本人必须独立画出并讲解：

```text
React → FastAPI → Signal → LangGraph → LLM → Tool Policy → MCP
      → Observation/RAG → LangGraph → HITL → Fresh Facts/Verifier
      → Idempotent Write → PostgreSQL → Trace/Audit → React
```

## 6. 验收四：故障与恢复

在一个处置处于 `awaiting_approval` 时执行：

```bash
docker compose -p opercerta-demo restart api mcp
curl -fsS http://127.0.0.1:8080/health/ready
```

刷新页面并继续原处置。本人必须说明：

- LangGraph checkpoint 保存什么；
- 业务表保存什么；
- 为什么节点可能重放，但业务工单仍有效一次；
- 重复审批为什么返回冲突；
- Redis 丢失为什么不应改变批准后的权威事实。

验收证据：重启前后同一 `operation_id`、最终 `work_order_id` 和零重复写入结论。

## 7. 验收五：口述与录屏

### 30 秒

只讲业务问题、Agent 价值、三业务和当前发布边界。

### 3 分钟

讲清业务动机、Agent 循环、MCP/RAG、HITL、幂等/恢复、测试证据和限制。

### 10 分钟

结合代码讲清状态机、模型边界、工具协议、PostgreSQL 事务、Redis 缓存、Trace 与一次真实故障。

### 3–5 分钟录屏

必须包含：

- 10–20 秒说明业务问题；
- 扫描异常和启动库存调查；
- Agent Trace 中一次模型决策、一次 MCP Observation 和一个 RAG citation；
- approver 批准与 auditor 查看唯一工单；
- 一句话声明“公网是静态展示，完整 Agent 在本地 Compose 运行”。

视频不得出现密码、API key、`.env` 内容、手机号或无关桌面隐私。

## 8. 最终签收记录

以下内容只有完成实际验收后填写：

```text
验收日期:
验证提交:
operation_id:
work_order_id:
重启恢复结果:
30 秒口述: 未验收
3 分钟口述: 未验收
10 分钟口述: 未验收
录屏文件或链接:
Showcase Release gate: AWAITING_OWNER_VALIDATION
```

全部通过后，更新当前状态、开发日志和 Release Evidence，再创建最终 Showcase Tag。
