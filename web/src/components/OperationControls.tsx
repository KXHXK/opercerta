import { useState } from "react";

import type { OperationalSignal, SignalCaseView } from "../api/contracts";
import type { DemoRole } from "../session";
import { SignalInbox } from "./SignalInbox";
import { SignalCaseInbox } from "./SignalCaseInbox";

type OperationControlsProps = {
  role: DemoRole;
  isAuthenticated: boolean;
  isBusy: boolean;
  signals?: OperationalSignal[];
  cases?: SignalCaseView[];
  selectedCaseKey?: string | null;
  busyCaseKey?: string | null;
  scanSummary: string | null;
  onRoleChange: (role: DemoRole) => void;
  onScan: () => void;
  onInvestigate: (signal: OperationalSignal) => void;
  onRetry: (signal: OperationalSignal) => void;
  onLoad: (operationId: string) => void;
  onSelectCase?: (caseKey: string) => void;
  onInvestigateCase?: (caseKey: string, signal: OperationalSignal) => void;
  onRetryCase?: (caseKey: string, signal: OperationalSignal) => void;
  onLoadCase?: (caseKey: string, operationId: string) => void;
};

export function OperationControls({
  role,
  isAuthenticated,
  isBusy,
  signals = [],
  cases,
  selectedCaseKey = null,
  busyCaseKey = null,
  scanSummary,
  onRoleChange,
  onScan,
  onInvestigate,
  onRetry,
  onLoad,
  onSelectCase,
  onInvestigateCase,
  onRetryCase,
  onLoadCase
}: OperationControlsProps) {
  const [operationId, setOperationId] = useState("");
  const canScan = !isBusy && role === "operator";
  const canOperate = !isBusy && isAuthenticated && role === "operator";

  return (
    <section aria-label="操作控制区">
      <label className="field-label" htmlFor="demo-role">演示角色</label>
      <select
        id="demo-role"
        value={role}
        onChange={(event) => onRoleChange(event.target.value as DemoRole)}
      >
        <option value="operator">operator｜发现异常与启动调查</option>
        <option value="approver">approver｜核对事实并审批</option>
        <option value="auditor">auditor｜只读审计</option>
      </select>

      <div className="signal-trigger">
        <div>
          <span>01 · DETECT</span>
          <strong>业务异常检测</strong>
          <p>首次点击会自动取得 operator 演示身份，再从 MCP 读取事实并执行确定性规则。</p>
        </div>
        <button type="button" disabled={!canScan} onClick={onScan}>
          扫描业务异常
        </button>
      </div>

      <div className="signal-detection-explainer" aria-label="异常检测方法">
        <p><strong>扫描范围</strong>：本地演示监控清单中的 3 个对象；每次点击实际调用 6 次只读 MCP（业务事实 + 对应策略）。</p>
        <ul>
          <li><strong>库存</strong>：可用库存 = 在库 − 预留；低于补货点才产生短缺信号。</li>
          <li><strong>设备</strong>：告警等级命中维修策略，或心跳超时，才产生设备信号。</li>
          <li><strong>任务</strong>：状态被阻塞或超过截止宽限期，且未超重试上限，才产生阻塞信号。</li>
        </ul>
      </div>

      {scanSummary === null ? null : <p className="signal-scan-summary">{scanSummary}</p>}

      {cases === undefined ? (
        <SignalInbox
          signals={signals}
          disabled={!canOperate}
          onInvestigate={onInvestigate}
          onRetry={onRetry}
          onOpenOperation={onLoad}
        />
      ) : (
        <SignalCaseInbox
          cases={cases}
          selectedCaseKey={selectedCaseKey}
          busyCaseKey={busyCaseKey}
          disabled={!isAuthenticated || role !== "operator"}
          onSelect={onSelectCase ?? (() => undefined)}
          onInvestigate={onInvestigateCase ?? (() => undefined)}
          onRetry={onRetryCase ?? (() => undefined)}
          onOpenOperation={onLoadCase ?? (() => undefined)}
        />
      )}

      <label className="field-label" htmlFor="operation-id">处置编号</label>
      <div className="inline-fields">
        <input
          id="operation-id"
          value={operationId}
          onChange={(event) => setOperationId(event.target.value)}
          placeholder="粘贴 operation_id"
        />
        <button
          type="button"
          disabled={!isAuthenticated || operationId.trim().length === 0}
          onClick={() => onLoad(operationId.trim())}
        >
          读取处置
        </button>
      </div>
      <p className="panel-note">
        演示 JWT 只用于本地角色隔离；令牌保存在当前页面内存中，刷新页面即失效。
      </p>
    </section>
  );
}
