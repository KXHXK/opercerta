import type { AgentTraceSnapshot } from "../api/contracts";

export function EvidenceAndCitations({ trace }: { trace: AgentTraceSnapshot | null }) {
  const observations = trace?.events.filter(
    (event) => event.event_type === "tool" || event.event_type === "rag"
  ) ?? [];
  if (observations.length === 0) {
    return <p className="agent-empty">工具事实和 SOP 引用将在调查完成后出现。</p>;
  }
  return (
    <section className="evidence-stack" aria-label="工具事实与引用">
      {observations.map((event) => {
        const safeSummary = event.safe_output.safe_summary;
        return (
          <article key={event.id} className="evidence-card">
            <div className="evidence-card__header">
              <span>{event.event_type === "rag" ? "RAG" : "MCP"}</span>
              <code>{event.tool_ref ?? event.node}</code>
            </div>
            <p>{typeof safeSummary === "string" ? safeSummary : "工具返回已通过类型与安全边界校验。"}</p>
            {event.citations.length > 0 ? (
              <ul className="citation-list">
                {event.citations.map((citation) => (
                  <li key={citation.id}>
                    <span className="mono-value">{citation.document_id} · {citation.chunk_id}</span>
                    <span>v{citation.version} · {(citation.score * 100).toFixed(1)}%</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
