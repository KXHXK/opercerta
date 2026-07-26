# OperCerta 面试演示脚本

本脚本只使用本地合成数据，目标时长 5--8 分钟。公开专题可即时打开；真实交互前确认本地 Docker Compose 健康，并准备 `http://localhost:5173/engineering` 与 `http://localhost:5173/console`。`/engineering` 不部署到公开主机。

1. 先打开公开项目专题，说明三业务是库存补货、设备维修、作业异常恢复，并指出交互生产发布门禁仍为 `CLOSED`。
2. 面试官追问技术时打开本地 `/engineering`：用 10 步链路说明 React → FastAPI → PostgreSQL Operation → LangGraph → FastMCP/Redis/Kimi → 审批恢复 → 幂等工单 → SSE；再用三业务差异矩阵说明共享可靠性内核与类型化变化点。
3. 切换到 `/console`，选择一个场景和 `operator`；先执行“查询状态”，展示 completed、零审批、零工单，再执行“创建处置”进入等待审批。
4. 切换到 `approver`，提交绑定审批；展示审批绑定中的证据、规则版本、事实哈希、计划哈希和建议参数均来自后端事实，调用者不能提交审批身份。
5. 审批通过后展示最终状态、唯一工单 ID 和审计时间线；强调重复请求复用同一工单，而不是生成第二条写入。
6. 解释两项自动化证据：PostgreSQL 行锁让并发审批只有一个原子胜者；API/MCP 重启后从业务表与 LangGraph checkpoint 恢复。
7. 展示 Mock/Real 分离证据：Mock Agent + 真实 FastEmbed/pgvector RAG 的 9/9 轨迹评测和 Compose 重启已通过；新 Agent 核心的 Real Kimi Tool Calling 代表 query 为 failed。说明低层 tool probe 与完整端到端兼容是两种证据，失败未回退 Mock，原文/token/费用没有被虚构记录。
8. 如面试官追问工程排障，从 `/engineering` 的事故复盘选择 1--2 个案例，按“观察—根因—修复—验证—限制”讲述，不逐项念页面。
9. 结束时明确边界：真实 Kimi 新 Agent 路径仍需兼容修复；生产 IAM/SSO、公开交互 HTTPS 后端、自动部署和 Release Tag 尚未完成，公开专题不提供可写服务。

录制视频时只保留浏览器业务区域，不展示本机用户名、文件路径、令牌、数据库连接或环境变量。只有实际完成上述流程的录屏才能放入公开专题；失败或未验证的运行不得剪辑成成功结果。
