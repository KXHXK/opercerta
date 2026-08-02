# 真实模型质量评测证据

> 执行时间：2026-08-02。模型：Moonshot OpenAI-compatible `kimi-k2.6`。模式：`real`。

结构化脱敏报告：[`real-model-quality-evaluation-2026-08-02.json`](real-model-quality-evaluation-2026-08-02.json)。

## 结论

冻结数据集 `data/evals/opercerta-real-model-v1.json` 的 9 条本地真实模型路径全部通过：

| 指标 | 实测结果 |
| --- | ---: |
| 任务成功率 | 9/9（100%） |
| Goal 精确匹配率 | 100% |
| 工具选择 precision / recall | 100% / 100% |
| 证据完整率 | 100% |
| Citation 可解析率 | 100% |
| 提示注入抵抗率 | 3/3（100%） |
| 数据库副作用匹配率 | 100% |
| 未授权工具调用 | 0 |
| 审批绕过 | 0 |
| 重复工单 | 0 |
| 平均模型调用 / 路径 | 2.333333 |
| 平均工具调用 / 路径 | 3.0 |
| 端到端延迟 P50 / P95 | 19,722.102 ms / 31,332.976 ms |

9 条路径由库存、设备、任务三个场景各 3 条组成：正常只读调查、带提示注入的只读调查、人工批准后的幂等写入闭环。每条路径都核对类型化 Goal、实际 MCP 工具集合、SOP citation、Agent Trace、审批数、工单数和 PostgreSQL 最终事实。

## 运行方式

```bash
bash scripts/run_real_model_quality_evaluation.sh \
  tmp/evals/opercerta-real-model-v1-report.json
```

运行器会拉起隔离的 Compose project，迁移全新 PostgreSQL/pgvector 数据库，写入合成 SOP，检查真实模型配置，执行冻结用例，生成脱敏 JSON 报告，最后删除隔离容器和卷。国内网络阻断镜像依赖下载时，可先构建与当前锁文件一致的本地镜像，再显式设置 `OPERCERTA_EVAL_SKIP_BUILD=true`；默认路径仍执行完整构建。

## TDD 与故障收口记录

1. 首轮 0/9 暴露评测环境未写入 SOP。运行器增加知识摄取前置条件后，单例恢复通过；系统保持 fail closed，没有伪造引用。
2. 随后的 6/9 暴露真实模型复制 citation ID 的脆弱性。Graph 改为从已验证 Observation 确定性绑定权威 evidence refs；LLM 仍负责语义规划，但不能重写事实主键。
3. 首次整套复测为 8/9，唯一失败用例单独复跑通过。根因是评测器要求信号必须出现在“本次扫描变化”中，没有恢复已经存在的 active signal。验证器增加只读 `/api/v1/signals` 回退后，整套顺序复测 9/9。
4. Dockerfile 将锁定依赖层与源码层拆分，并使用 BuildKit uv cache；源码变化不再强制重新下载全部大依赖。

这些修复分别处理了评测前置条件、模型与权威证据的信任边界、用例状态隔离以及构建可恢复性，没有降低断言或跳过失败业务路径。

## 诚实边界

- 这是 9 条固定、本地、合成业务路径的小样本，不是生产准确率、真实流量或供应商横向基准。
- 延迟是包含 API、模型、多轮 MCP、数据库和 Trace 读取的端到端操作延迟，不是模型单次推理延迟，也不是 SLA。
- 当前 provider 响应链路没有向评测器提供可信 token/cost 字段，因此 token 用量和成本标记为 unavailable，不做估算。
- 报告不保存 API key、完整 Prompt、原始模型文本或原始异常消息。
- Product Release gate 仍为 `CLOSED`；本证据只支持“公开静态展示 + 本地可复现完整 Agent MVP”。

## 项目专题同步

- 公开专题：<https://opercerta-kxh.netlify.app/>
- 专题已经同步 Agent Harness 组成、循环架构、端到端业务链路、各技术实际职责和本页评测结果。
- 前端门禁为 62/62，生产构建产物为 `index-Cn61pK2g.js`；Netlify deploy `6a6f200da7560edee31e8739` 已发布并通过 HTTP 200、CSP 和关键评测内容检查。
- 公开页面仍是只读静态展示，不把本地 Agent MVP 描述为公网可写产品。
