import type { OperationalSignal } from "../api/contracts";

const typeLabels: Record<OperationalSignal["signal_type"], string> = {
  inventory_shortage: "库存短缺",
  equipment_attention: "设备异常",
  task_blocked: "任务阻塞"
};

const statusLabels: Record<OperationalSignal["status"], string> = {
  open: "待调查",
  investigating: "调查中",
  resolved: "已解决",
  attention_required: "需人工关注"
};

function factSummary(signal: OperationalSignal): string {
  if (signal.signal_type === "inventory_shortage") {
    return `可用库存 ${String(signal.facts.available_quantity)} < 补货点 ${String(signal.facts.reorder_point)}；建议补货 ${String(signal.facts.recommended_quantity)}`;
  }
  if (signal.signal_type === "equipment_attention") {
    return `状态 ${String(signal.facts.state)}；告警 ${String(signal.facts.alert_code)}；心跳滞后 ${String(signal.facts.heartbeat_age_seconds)} 秒；优先级 ${String(signal.facts.priority)}`;
  }
  return `状态 ${String(signal.facts.state)}；阻塞码 ${String(signal.facts.blocker_code)}；已重试 ${String(signal.facts.retry_count)} 次；建议 ${String(signal.facts.recovery_action)}`;
}

type SignalInboxProps = {
  signals: OperationalSignal[];
  disabled: boolean;
  onInvestigate: (signal: OperationalSignal) => void;
  onRetry: (signal: OperationalSignal) => void;
  onOpenOperation: (operationId: string) => void;
};

export function SignalInbox({
  signals,
  disabled,
  onInvestigate,
  onRetry,
  onOpenOperation
}: SignalInboxProps) {
  if (signals.length === 0) {
    return (
      <p className="signal-empty">
        尚未发现业务异常。先运行一次受控扫描，系统会读取三类业务事实并按确定性规则筛选。
      </p>
    );
  }

  return (
    <ul className="signal-list" aria-label="业务异常信号列表">
      {signals.map((signal) => {
        const hasSuccessor = signals.some(
          (candidate) => candidate.predecessor_signal_id === signal.id
        );
        return (
        <li key={signal.id} className={`signal-card signal-card--${signal.severity}`}>
          <div className="signal-card__heading">
            <span>{typeLabels[signal.signal_type]}</span>
            <strong>{statusLabels[signal.status]}</strong>
          </div>
          <p className="signal-card__object">{signal.object_id}</p>
          <dl>
            <div><dt>触发原因</dt><dd>{signal.reason_code}</dd></div>
            <div><dt>规则事实</dt><dd>{factSummary(signal)}</dd></div>
            <div><dt>事实来源</dt><dd>本地演示监控清单 · MCP 实时取证（{signal.source}）</dd></div>
          </dl>
          {signal.status === "open" ? (
            <button type="button" disabled={disabled} onClick={() => onInvestigate(signal)}>
              启动 Agent 调查
            </button>
          ) : signal.status === "attention_required" ? (
            <div className="signal-card__actions">
              {signal.operation_id === null ? null : (
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onOpenOperation(signal.operation_id as string)}
                >
                  查看原处置
                </button>
              )}
              {hasSuccessor ? (
                <span>后继调查已创建，请查看新的信号卡片。</span>
              ) : (
                <>
                  <button type="button" disabled={disabled} onClick={() => onRetry(signal)}>
                    重新调查
                  </button>
                  <span>新的处置会重新读取 MCP 事实并生成新的审批绑定。</span>
                </>
              )}
            </div>
          ) : signal.operation_id !== null ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onOpenOperation(signal.operation_id as string)}
            >
              查看关联处置
            </button>
          ) : null}
        </li>
        );
      })}
    </ul>
  );
}
