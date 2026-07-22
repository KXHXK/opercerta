# Agent pgvector、中文 SOP RAG 与 Memory 边界证据

日期：2026-07-22（Asia/Shanghai）
范围：Agent 核心架构 Task 6
发布门禁：`CLOSED`

## 本阶段实现

- PostgreSQL 迁移 `0005_agent_knowledge` 启用 `vector` extension，新增版本化 `knowledge_documents`、`knowledge_chunks`、`vector(512)` 与 HNSW cosine 索引；迁移支持 upgrade、downgrade、re-upgrade。
- Compose PostgreSQL 固定为 `pgvector/pgvector:0.8.2-pg18-trixie`；Python 依赖固定为 `pgvector==0.5.0`、`fastembed==0.8.0`。
- 三份知识材料均为从零编写的中文合成 SOP，分别覆盖库存补货、设备维修和作业恢复。manifest 固定模型、维度、分块策略、场景、版本和源文件 SHA-256，不包含旧公司或真实客户材料。
- 入库按 `(scenario, slug, version)` 幂等；同版本内容变化失败关闭，并覆盖十路并发相同入库只创建一个文档、版本激活/废弃和跨场景隔离。
- FastMCP 新增 `knowledge.search_sop`。检索先按 scenario、active、version 过滤，再执行 cosine 排序；低于固定最小分数 0.5 的结果不返回，无合格结果为 `knowledge_insufficient`。
- LangGraph Planner 在启用知识能力时获得场景绑定的只读工具；Analyst 只能引用工具实际返回的 document/chunk/version/score/safe snippet。RAG 不掌握数量、优先级、审批或写入决策。
- 普通 operation 在 RAG 不可用时保留空引用并由结构化 MCP 事实与 Policy Guard 继续；明确要求 SOP 时立即失败关闭，稳定错误码进入 operation，且零工单。

## TDD 证据

1. 工作流首次 RED：`build_controlled_action_graph()` 不接受 `knowledge_enabled`，证明测试确实覆盖新接口。
2. 强制知识 RED：缺少 SOP 后图错误进入 replan，最终产生空计划 Pydantic 异常；修复为路由层立即失败并传播 `knowledge_insufficient`。
3. 最小相似度 RED：正交测试向量得分 0 仍被返回；修复为 MCP 在 0.5 阈值过滤后判定无合格引用。
4. 知识资产 RED：`scripts.ingest_knowledge` 不存在导致收集失败；随后实现 manifest、SHA-256、H2 固定分块与 `--check`。
5. runtime RED：MCP 未创建 embedding gateway、API 无知识开关、Compose 无模型缓存，3 条测试同时失败；接线后 3 条 GREEN。

## 新鲜自动化验证

- Task 6 聚焦测试：新建空 pgvector 数据卷并在 Docker 网络内执行，`75 passed in 36.33s`。
- 后端产品测试（容器内，排除必须读取真实 Git worktree 的 4 条仓库安全测试）：`535 passed in 148.57s`。
- WSL 原生仓库安全单测：`4 passed in 0.42s`；安全脚本：`repository safety checks passed`。
- Ruff：`All checks passed!`；格式：`173 files already formatted`；mypy：`Success: no issues found in 73 source files`。
- 锁文件：`uv lock --check` 解析 114 个包；`docker compose config --quiet` 与 release Compose config 均退出 0。
- 新镜像从锁文件安装 99 个生产包并构建 API、MCP、bootstrap 成功；该次启动观察到 PostgreSQL healthy、bootstrap 正常退出、MCP healthy、API started。

## 真实本地 embedding 与检索

- 固定模型：`BAAI/bge-small-zh-v1.5`；维度：512；FastEmbed：0.8.0。
- `scripts/ingest_knowledge.py --check`：3 个文档、12 个 chunk、三场景齐全。
- 首次真实入库：三场景各 1 个 v1.0.0 文档、4 个 chunk，`replayed=false`；相同输入第二次执行返回相同文档 ID，三者均 `replayed=true`。
- 真实代表查询只召回本场景 v1.0.0 文档：库存 top-3 分数为 0.641301、0.560725、0.540769；设备为 0.621887、0.585967、0.546363；作业为 0.620862、0.606399、0.588797。
- 上述分数只记录本次合成语料和三条查询的 cosine 结果，不是准确率、召回率、生产质量或性能承诺。

## 故障与边界

- 本机直连 `huggingface.co` 超时；临时使用 ignored `.env.compose` 中的 `HF_ENDPOINT=https://hf-mirror.com` 完成模型缓存，不把第三方镜像硬编码到产品 Compose。
- Hugging Face Xet 日志目录曾因一次性测试容器 HOME 权限产生警告，FastEmbed 随后从同一固定模型的备用源完成 54.6 MB 下载。缓存完成后以 `local_files_only=True` 验证 512 维向量并完成三场景查询。
- 提交前首次空卷门禁得到 `1 failed, 74 passed`：迁移往返测试错误依赖未迁移的 `database_url`，却直接执行 head→0004。修复测试前置条件为 `migrated_database_url` 后，单条迁移测试 `1 passed`，完整聚焦门禁 `75 passed`。该修复未改生产迁移。
- 一次错误的主机侧测试命令把 Compose 专用 DSN 用于 WSL，并在异常堆栈中回显本地开发凭据；该凭据已立即轮换，ignored 根环境文件已同步，代码、Git 与本证据均不保存旧值或新值。
- 额外执行完整 Compose smoke 时，当前 Codex 自动化 WSL 会话连续三次在约 43--49 秒收到外层 Docker service 停止；流程已走到数据库计数断言，失败信息均为 `service "postgres" is not running`。轮询、持续 events 和前台 Compose 管理三种维持方式均未改变结果，因此停止 workaround。Task 9 必须在稳定交互式 WSL 会话重跑完整 smoke 与 API/MCP restart recovery。
- Task 7 的 Agent Trace 持久化/API/SSE/RBAC 与 Task 8 前端 Agent 工作台尚未实施；Task 6 的引用目前存在于 LangGraph state，尚未作为产品级脱敏 Trace 向 UI 暴露。
- 公网可写后端、生产 IAM、限流、备份、多 Worker、远程当前 CI 和 Release Tag 均未完成，发布门禁保持 `CLOSED`。
