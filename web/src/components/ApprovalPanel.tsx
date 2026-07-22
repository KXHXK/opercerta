import { useEffect, useState } from "react";

import type { ApprovalBinding } from "../api/client";
import type { DemoRole } from "../session";

type ApprovalPanelProps = {
  role: DemoRole;
  binding: ApprovalBinding | null;
  onDecision: (decision: "approved" | "rejected") => Promise<void>;
};

export function ApprovalPanel({ role, binding, onDecision }: ApprovalPanelProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasDecided, setHasDecided] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setHasDecided(false);
    setError(null);
  }, [binding?.plan_hash]);

  if (role !== "approver") {
    return <p className="panel-note">仅 approver 演示角色可提交审批决定。</p>;
  }

  if (binding === null) {
    return <p className="panel-note">当前处置尚未生成可绑定的审批事实。</p>;
  }

  async function decide(decision: "approved" | "rejected") {
    setIsSubmitting(true);
    setError(null);
    try {
      await onDecision(decision);
      setHasDecided(true);
    } catch {
      setError("审批未提交，请读取最新处置状态后重试。");
    } finally {
      setIsSubmitting(false);
    }
  }

  const disabled = isSubmitting || hasDecided;
  const bindingSummary = binding.parameters.kind === "replenishment"
    ? `建议补货 ${binding.parameters.recommended_quantity} 件`
    : binding.parameters.kind === "repair"
      ? `${binding.parameters.alert_code} · ${binding.parameters.priority} 优先级`
      : `恢复动作 · ${binding.parameters.recovery_action}`;
  return (
    <section aria-label="审批操作">
      <p className="binding-kind">{binding.scenario}</p>
      <p className="panel-note">{bindingSummary}</p>
      <dl className="binding-facts">
        <div><dt>规则版本</dt><dd>{binding.rule_version}</dd></div>
        <div><dt>事实哈希</dt><dd className="mono-value">{binding.decision_facts_hash.slice(0, 12)}…</dd></div>
        <div><dt>计划哈希</dt><dd className="mono-value">{binding.plan_hash.slice(0, 12)}…</dd></div>
      </dl>
      <p className="verifier-note">批准后 Verifier 将绕过缓存重新取证；事实变化会进入复审，不直接写工单。</p>
      <div className="decision-actions">
        <button type="button" disabled={disabled} onClick={() => decide("approved")}>批准</button>
        <button type="button" disabled={disabled} onClick={() => decide("rejected")}>驳回</button>
      </div>
      {error !== null ? <p role="alert">{error}</p> : null}
    </section>
  );
}
