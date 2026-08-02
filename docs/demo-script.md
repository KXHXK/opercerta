# OperCerta 面试演示脚本

本脚本只使用本地合成数据，目标时长 5--8 分钟。公开专题可即时打开；真实交互前确认本地 Docker Compose 健康，并准备 `http://localhost:5173/engineering` 与 `http://localhost:5173/console`。`/engineering` 不部署到公开主机。

1. 先打开公开项目专题，说明三业务是库存补货、设备维修、作业异常恢复；公开页面用于即时招聘展示，公网可写生产门禁仍为 `CLOSED`。
2. 面试官追问技术时打开本地 `/engineering`：用 10 步链路说明 React → FastAPI → PostgreSQL signal/operation → 单根 LangGraph → FastMCP/Redis/Kimi → HITL → Verifier → 幂等工单 → Trace/SSE；再用三业务矩阵说明共享可靠性内核与类型化变化点。
3. 切换到 `/console`，保持 `operator`，点击“扫描业务异常”。说明固定演示监控清单对三个合成对象执行 6 次只读 MCP 调用和确定性规则，只有检测到异常才生成 case，不让 LLM 猜测是否异常。
4. 选择一张“待调查”case，点击“启动 Agent 调查”。展示编码后的 Goal、Model↔Tool Observation、SOP citation、模型建议与确定性计划，并确认 LangGraph 停在 `awaiting_approval`。
5. 切换到 `approver`，核对并提交绑定审批；说明证据 ID、规则版本、事实哈希、计划哈希和参数来自后端，审批身份来自演示 JWT，调用者不能在请求体冒充审批人。
6. 审批通过后展示 Verifier、最终状态、唯一工单 ID、写后读和审计时间线；切换 `auditor` 读取同一处置，强调 Trace、业务 audit 和 OpenTelemetry 的职责不同。
7. 解释两项自动化证据：PostgreSQL 行锁让并发审批只有一个原子胜者；API/MCP 重启后由业务表寻找候选、LangGraph checkpoint 决定续跑位置，重复执行仍复用同一幂等工单。
8. 展示 Mock/Real 分层证据：Mock 冻结评测 9/9 和真实 FastEmbed/pgvector、PostgreSQL、MCP、Compose 重启通过；Real Kimi 冻结质量评测 9/9，覆盖三业务正常查询、提示注入和审批写入，未授权工具调用、审批绕过、重复工单均为 0。固定本地小样本不解释为生产准确率、SLA、token 或成本指标。
9. 如面试官追问工程排障，从 `/engineering` 选择 1--2 个案例，按“观察—根因—修复—验证—限制”讲述。结束时主动说明生产 IAM/SSO、公网可写 HTTPS 后端、限流、备份、高可用、自动部署和 Release Tag 尚未完成。

录制视频时只保留浏览器业务区域，不展示本机用户名、文件路径、令牌、数据库连接或环境变量。只有实际完成上述流程的录屏才能放入公开专题；失败或未验证的运行不得剪辑成成功结果。
