import type { AgentTraceSnapshot, OperationDetail } from "../api/contracts";

export function DecisionComparison({
  detail,
  trace
}: {
  detail: OperationDetail | null;
  trace: AgentTraceSnapshot | null;
}) {
  const analysis = trace?.events.find((event) => event.node === "analyze_observations");
  const recommendation = analysis?.safe_output.recommendation;
  return (
    <section className="decision-comparison" aria-label="建议与计划对照">
      <article>
        <p className="decision-kicker">Core LLM</p>
        <h3>模型建议</h3>
        <p>{typeof recommendation === "string" ? recommendation : "等待模型完成受约束分析。"}</p>
        <span>提供解释，不拥有写权限</span>
      </article>
      <article>
        <p className="decision-kicker">Policy Guard</p>
        <h3>确定性执行计划</h3>
        <p className="decision-json">{detail?.plan === null || detail === null
          ? "等待规则计算"
          : JSON.stringify(detail.plan)}</p>
        <span>参数、审批与写入由代码控制</span>
      </article>
    </section>
  );
}
