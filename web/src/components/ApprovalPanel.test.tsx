import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { ApprovalPanel } from "./ApprovalPanel";

const binding = {
  scenario: "inventory" as const,
  subject_evidence_id: "inventory-evidence",
  policy_evidence_id: "policy-evidence",
  rule_version: "rule-v1",
  decision_facts_hash: "facts-hash",
  plan_hash: "plan-hash",
  parameters: { kind: "replenishment" as const, recommended_quantity: 18 }
};

it("shows approval only to approver and disables a second decision", async () => {
  const onDecision = vi.fn().mockResolvedValue(undefined);
  const { rerender } = render(
    <ApprovalPanel role="operator" binding={binding} onDecision={onDecision} />
  );

  expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();

  rerender(<ApprovalPanel role="approver" binding={binding} onDecision={onDecision} />);
  expect(screen.getByText("建议补货 18 件")).toBeInTheDocument();
  const approve = screen.getByRole("button", { name: "批准" });
  expect(approve).toBeEnabled();

  fireEvent.click(approve);

  expect(onDecision).toHaveBeenCalledWith("approved");
  expect(approve).toBeDisabled();
});

it("shows the actionable safe API error instead of swallowing an expired approval", async () => {
  const onDecision = vi.fn().mockRejectedValue(
    new ApiError(409, "approval_expired")
  );
  render(<ApprovalPanel role="approver" binding={binding} onDecision={onDecision} />);

  fireEvent.click(screen.getByRole("button", { name: "批准" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "审批已过期。请由 operator 创建新的处置后再审批。"
  );
});
