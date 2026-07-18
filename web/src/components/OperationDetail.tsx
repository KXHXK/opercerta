import type { OperationDetail as OperationDetailData } from "../api/contracts";

const statusLabels: Record<string, string> = {
  awaiting_approval: "等待审批",
  completed: "处置完成",
  failed: "处置失败",
  running: "执行中"
};

type OperationDetailProps = {
  detail: OperationDetailData | null;
};

export function OperationDetail({ detail }: OperationDetailProps) {
  if (detail === null) {
    return <p className="timeline-empty">创建或读取处置后，在此查看后端返回的业务事实。</p>;
  }

  return (
    <section aria-label="业务事实区">
      <p className="status-label">{statusLabels[detail.status] ?? "处置状态已更新"}</p>
      <dl className="fact-list">
        <div><dt>处置编号</dt><dd className="mono-value">{detail.operation_id}</dd></div>
        <div><dt>请求内容</dt><dd>{detail.request.message}</dd></div>
        <div><dt>审计序列</dt><dd>审计序列：{detail.last_audit_sequence}</dd></div>
        {detail.approval !== null ? <div><dt>审批结果</dt><dd>{detail.approval.decision}</dd></div> : null}
        {detail.work_order !== null ? <div><dt>工单编号</dt><dd className="mono-value">{detail.work_order.id}</dd></div> : null}
        {detail.work_order !== null ? <div><dt>工单状态</dt><dd>{detail.work_order.status}</dd></div> : null}
      </dl>
      {detail.error !== null ? <p role="alert">后端返回：{detail.error.message}</p> : null}
    </section>
  );
}
