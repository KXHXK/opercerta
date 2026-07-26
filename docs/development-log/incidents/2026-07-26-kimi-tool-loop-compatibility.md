# 真实 Kimi Tool Loop 兼容性事故复盘

> 日期：2026-07-26
> 类型：Provider compatibility / fail-closed
> 影响：代表性真实模型请求返回 503；未产生错误审批或工单

## 现象

Mock、单元、集成和 Compose 回归通过后，隔离真实模型门禁中的三业务请求仍在 Agent 图早期安全失败，API 返回固定 503。系统没有回退 Mock，operation 留下失败终态，数据库没有审批或工单副作用。

## 定位方法

不记录 API key、完整 prompt、模型原文或隐藏推理，仅使用 checkpoint 所处阶段、固定错误分类、容器健康与最小 provider probe 缩小范围。由此区分网络、MCP、模型首次 tool call、最终分析和批准后 Verifier 五个阶段。

## 根因

1. production factory 错把 `OPERCERTA_MCP_TIMEOUT_SECONDS=2` 同时用作 LLM timeout；MCP 与远程生成的延迟模型不同。
2. Moonshot `kimi-k2.6` 在强制原生 tool calling 下与默认 thinking mode 不兼容，首次 `model_decide` 返回 provider BadRequest。
3. provider 对通用 structured output 的返回形态有波动，最终分析和审批 Verifier 不能只依赖一次通用解析。

## 修复

- 新增独立 `OPERCERTA_MODEL_TIMEOUT_SECONDS`，默认 90 秒；MCP timeout 保持 2 秒，并用单元测试锁定两者不能再次耦合。
- 通用默认不变；Moonshot/Kimi 的运行配置显式使用 `OPERCERTA_MODEL_THINKING_MODE=disabled`，把供应商差异限制在 adapter/config 边界。
- 最终分析改为强制调用内部 `submit_final_analysis` 工具；Verifier 改为内部 `submit_verification_decision` 工具，再由本地严格 schema 校验参数。
- 新增真实验证脚本的 `query`、`approved_path` 与 provider failure 路径；批准路径支持 attention-required successor。

## 复验

三业务各一次真实只读路径通过；库存一次真实批准写入通过，并验证一条审批、一张工单、Trace/RAG/回读一致；无效 provider endpoint 返回 503，operation failed，审批与工单均为 0。真实证据与 Mock 报告分开保存。

## 工程教训

- OpenAI-compatible 只说明接口外形相近，不等于 Tool Calling、thinking extension 和 structured output 完全一致。
- Mock 能验证确定性合同，不能证明供应商协议兼容；真实代表调用仍是发布前必要门禁。
- 不同协议依赖必须有独立 timeout、retry 和错误分类。
- provider 差异应收敛在 adapter/config，不能渗入业务图和安全规则。
- 真实模型失败必须 fail closed；不得为了演示成功静默回退 Mock。

## 面试表达

“我遇到的不是业务规则 bug，而是 Mock 无法暴露的 provider compatibility 问题。我用阶段化安全信号定位，将 LLM/MCP timeout 解耦，把 Kimi thinking 配置留在 adapter 边界，并用原生内部提交工具稳定最终结构化结果。修复后同时验证成功路径和 provider 故障零写入，避免只证明 happy path。”
