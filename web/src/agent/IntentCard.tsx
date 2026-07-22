import type { AgentTraceSnapshot, OperationDetail, TraceValue } from "../api/contracts";

type IntentCardProps = {
  detail: OperationDetail | null;
  trace: AgentTraceSnapshot | null;
};

function display(value: TraceValue | undefined): string | null {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

export function IntentCard({ detail, trace }: IntentCardProps) {
  if (detail === null) {
    return <p className="agent-empty">提交有限业务表单后，系统会在此展示编码后的 Goal。</p>;
  }
  const goal = trace?.events.find((event) => event.node === "encode_goal");
  const encodedAction = display(goal?.safe_output.goal) ?? detail.request.requested_action;
  const successCondition = display(goal?.safe_output.success_condition);

  return (
    <section className="agent-card intent-card" aria-label="意图与目标">
      <div className="agent-card__heading">
        <span className="agent-step">01</span>
        <div><p>Perception</p><h3>结构化 Goal</h3></div>
      </div>
      <p className="goal-statement">{detail.request.message}</p>
      <dl className="compact-facts">
        <div><dt>场景</dt><dd>{detail.request.object_type}</dd></div>
        <div><dt>对象</dt><dd className="mono-value">{detail.request.object_id}</dd></div>
        <div><dt>动作</dt><dd>{encodedAction === "query"
          ? "查询与评估"
          : "受控工单申请"}</dd></div>
        {successCondition !== null ? <div><dt>成功条件</dt><dd>{successCondition}</dd></div> : null}
      </dl>
      <p className="agent-boundary-note">输入来自固定场景与对象选择，不接受开放聊天指令。</p>
    </section>
  );
}
