import { useState } from "react";

import type { OperationalSignal, SignalCaseView } from "../api/contracts";

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

type SignalCaseInboxProps = {
  cases: SignalCaseView[];
  selectedCaseKey: string | null;
  busyCaseKey: string | null;
  disabled: boolean;
  onSelect: (caseKey: string) => void;
  onInvestigate: (caseKey: string, signal: OperationalSignal) => void;
  onRetry: (caseKey: string, signal: OperationalSignal) => void;
  onOpenOperation: (caseKey: string, operationId: string) => void;
};

export function SignalCaseInbox({
  cases,
  selectedCaseKey,
  busyCaseKey,
  disabled,
  onSelect,
  onInvestigate,
  onRetry,
  onOpenOperation
}: SignalCaseInboxProps) {
  const [expandedCases, setExpandedCases] = useState<Set<string>>(new Set());

  if (cases.length === 0) {
    return (
      <p className="signal-empty">
        尚未发现业务异常。运行一次受控扫描后，每个业务对象只显示一张主卡片。
      </p>
    );
  }

  function toggleHistory(caseKey: string) {
    setExpandedCases((current) => {
      const next = new Set(current);
      if (next.has(caseKey)) next.delete(caseKey);
      else next.add(caseKey);
      return next;
    });
  }

  return (
    <ul className="signal-list signal-case-list" aria-label="业务异常 case 列表">
      {cases.map((signalCase) => {
        const signal = signalCase.current_signal;
        const expanded = expandedCases.has(signalCase.case_key);
        const selected = selectedCaseKey === signalCase.case_key;
        const busy = busyCaseKey === signalCase.case_key;
        return (
          <li
            key={signalCase.case_key}
            data-testid="signal-case-card"
            className={`signal-card signal-card--${signal.severity}${selected ? " is-selected" : ""}`}
            aria-busy={busy}
            onClick={() => onSelect(signalCase.case_key)}
          >
            <div className="signal-card__heading">
              <span>{typeLabels[signal.signal_type]}</span>
              <strong>{statusLabels[signal.status]}</strong>
            </div>
            <p className="signal-card__object">{signalCase.object_id}</p>
            <dl>
              <div><dt>当前原因</dt><dd>{signal.reason_code}</dd></div>
              <div><dt>当前处置</dt><dd>{signalCase.current_operation?.status ?? "尚未创建"}</dd></div>
              <div><dt>事实来源</dt><dd>{signal.source}</dd></div>
            </dl>
            <div className="signal-card__actions">
              {signal.status === "open" ? (
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(signalCase.case_key);
                    onInvestigate(signalCase.case_key, signal);
                  }}
                >
                  启动 Agent 调查
                </button>
              ) : signal.status === "attention_required" ? (
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(signalCase.case_key);
                    onRetry(signalCase.case_key, signal);
                  }}
                >
                  重新调查
                </button>
              ) : signalCase.current_operation !== null ? (
                <button
                  type="button"
                  disabled={disabled || busy}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(signalCase.case_key);
                    onOpenOperation(
                      signalCase.case_key,
                      signalCase.current_operation?.operation_id as string
                    );
                  }}
                >
                  查看关联处置
                </button>
              ) : null}
              {signalCase.history_count > 0 ? (
                <button
                  type="button"
                  className="button-link"
                  onClick={(event) => {
                    event.stopPropagation();
                    toggleHistory(signalCase.case_key);
                  }}
                >
                  {expanded ? "收起历史" : `展开历史（${signalCase.history_count}）`}
                </button>
              ) : null}
            </div>
            {expanded ? (
              <ol className="signal-lineage" aria-label={`${signalCase.object_id} 调查历史`}>
                {signalCase.lineage.map((item) => (
                  <li key={item.id}>
                    <code>{item.id}</code>
                    <span>{statusLabels[item.status]}</span>
                    <time dateTime={item.detected_at}>{item.detected_at}</time>
                  </li>
                ))}
              </ol>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
