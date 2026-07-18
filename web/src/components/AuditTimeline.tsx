import type { AuditEvent } from "../audit-stream";

const eventLabels: Record<string, string> = {
  approval_requested: "等待审批",
  operation_completed: "处置完成"
};

type AuditTimelineProps = {
  events: AuditEvent[];
};

export function AuditTimeline({ events }: AuditTimelineProps) {
  const orderedEvents = [...events].sort((left, right) => left.sequence - right.sequence);

  if (orderedEvents.length === 0) {
    return <p className="timeline-empty">暂无可回放的审计事件</p>;
  }

  return (
    <ol className="audit-timeline" aria-label="审计时间线">
      {orderedEvents.map((event) => (
        <li key={event.sequence} className="audit-timeline__entry">
          <span aria-hidden="true" className="audit-timeline__marker" />
          <div>
            <strong>{eventLabels[event.type] ?? "审计事件"}</strong>
            <span className="audit-timeline__sequence">#{event.sequence}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
