import type { AgentTraceEvent, AgentTraceSnapshot, TraceValue } from "../api/contracts";

const eventLabels: Record<AgentTraceEvent["event_type"], string> = {
  perception: "感知",
  model: "模型分析",
  tool: "MCP 工具",
  rag: "SOP 检索",
  rule: "确定性规则",
  human: "人工审批",
  execution: "受控执行",
  feedback: "结果反馈",
  guardrail: "安全护栏"
};

function summary(event: AgentTraceEvent): string {
  for (const key of ["summary", "recommendation", "safe_summary", "operation_status", "status"]) {
    const value: TraceValue | undefined = event.safe_output[key];
    if (typeof value === "string") return value;
  }
  if (event.error_code !== null) return `安全终止：${event.error_code}`;
  return `${event.actor_type} 已完成 ${event.node}`;
}

export function AgentTrace({ trace }: { trace: AgentTraceSnapshot | null }) {
  if (trace === null || trace.events.length === 0) {
    return (
      <section className="trace-board trace-board--empty" aria-label="Agent Trace">
        <p className="agent-empty">尚无 Agent Trace。从异常信号启动调查或读取处置后加载持久化轨迹。</p>
      </section>
    );
  }
  return (
    <section className="trace-board" aria-label="Agent Trace">
      <header className="trace-board__header">
        <div><p>Agent Trace</p><h3>感知 → 决策 → 行动 → 反馈</h3></div>
        <span>{trace.run.model_mode.toUpperCase()} · {trace.events.length} EVENTS</span>
      </header>
      <ol className="trace-list">
        {trace.events.map((event) => (
          <li key={event.id} className="trace-event" data-event-type={event.event_type}>
            <span className="trace-sequence">{String(event.sequence).padStart(2, "0")}</span>
            <div className="trace-event__body">
              <div className="trace-event__meta">
                <strong>{eventLabels[event.event_type]}</strong>
                <span>{event.node}</span>
                <span className={`trace-status trace-status--${event.status}`}>{event.status}</span>
              </div>
              <p>{summary(event)}</p>
              <div className="trace-refs">
                {event.prompt_ref !== null ? <code>{event.prompt_ref}</code> : null}
                {event.tool_ref !== null ? <code>{event.tool_ref}</code> : null}
                {event.citations.length > 0 ? <span>{event.citations.length} 条引用</span> : null}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
