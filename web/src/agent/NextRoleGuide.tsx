import type { DemoRole } from "../session";

type NextRoleGuideProps = {
  role: DemoRole;
  status: string | null;
  hasWorkOrder: boolean;
};

export function NextRoleGuide({ role, status, hasWorkOrder }: NextRoleGuideProps) {
  let title = "先以 operator 提交业务表单";
  let detail = "选择三种合成场景之一，执行查询或申请工单。";
  if (status === "awaiting_approval" || status === "needs_reapproval") {
    if (role === "approver") {
      title = status === "needs_reapproval" ? "核对变化后再次审批" : "核对绑定事实并决定";
      detail = "批准后 Verifier 会绕过缓存重新取证；事实漂移不会直接写工单。";
    } else {
      title = "下一步：切换为 approver";
      detail = "operation 会保留；审批者只能处理当前待审批或待复审任务。";
    }
  } else if (status === "completed") {
    title = role === "auditor" ? "核验 Trace 与业务审计" : "下一步：切换为 auditor";
    detail = hasWorkOrder
      ? "检查唯一工单回读、执行反馈与审计终态。"
      : "该查询路径零审批、零工单；检查事实、规则与 Trace。";
  } else if (status === "failed") {
    title = "由 auditor 检查安全终止";
    detail = "沿 guardrail、error code 与审计记录定位失败，不绕过规则重试写入。";
  }
  return (
    <aside className="next-role-guide" aria-label="下一角色引导">
      <span>ROLE HANDOFF</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </aside>
  );
}
