import { PROJECT_FACTS } from "./project-facts";

const RESULTS = [
  ["后端测试", `${PROJECT_FACTS.backendTests} / ${PROJECT_FACTS.backendTests}`, "Pytest 全量通过"],
  ["前端测试", `${PROJECT_FACTS.frontendTests} / ${PROJECT_FACTS.frontendTests}`, "Vitest 全量通过"],
  ["三业务固定评测", `${PROJECT_FACTS.frozenEvaluations} / ${PROJECT_FACTS.frozenEvaluations}`, "库存、设备、任务"],
  ["Agent 安全恢复", `${PROJECT_FACTS.agentSafetyEvaluations} / ${PROJECT_FACTS.agentSafetyEvaluations}`, "非法输入、恢复、竞态、幂等"],
  ["真实模型路径", `${PROJECT_FACTS.realModelPaths} / ${PROJECT_FACTS.realModelPaths}`, "3 场景 × 3 路径"],
  ["提示注入测试", `${PROJECT_FACTS.promptInjectionPasses} / ${PROJECT_FACTS.promptInjectionPasses}`, "均按预期安全结束"],
  ["端到端 P50", `${PROJECT_FACTS.endToEndP50Seconds} s`, "API + 模型 + MCP + DB + Trace"],
  ["端到端 P95", `${PROJECT_FACTS.endToEndP95Seconds} s`, "固定本地评测样本"],
] as const;

export function EvaluationResults() {
  return (
    <>
      <div className="evaluation-grid">
        {RESULTS.map(([label, value, note]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
            <p>{note}</p>
          </article>
        ))}
      </div>
      <div className="evaluation-summary">
        <p>
          Kimi K2.6 的 9 条固定本地合成路径覆盖每个场景的正常查询、提示注入和批准写入；任务成功、目标匹配、
          工具 precision/recall、证据完整性、citation 可解析性与数据库副作用均为 100%。
        </p>
        <p>
          未授权工具调用、审批绕过和重复工单均为 0。结果只证明当前代码、固定数据和评测契约可复现，
          不等同于生产准确率、SLA 或供应商基准；token 与成本数据本轮不可用。
        </p>
      </div>
    </>
  );
}
