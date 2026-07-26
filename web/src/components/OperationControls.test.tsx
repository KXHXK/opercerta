import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { OperationControls } from "./OperationControls";

it("allows the initial operator to scan before a demo token has been issued", () => {
  const onScan = vi.fn();
  const { rerender } = render(
    <OperationControls
      role="operator"
      isAuthenticated={false}
      isBusy={false}
      signals={[]}
      scanSummary={null}
      onRoleChange={vi.fn()}
      onScan={onScan}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onLoad={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "扫描业务异常" }));
  expect(onScan).toHaveBeenCalledOnce();

  rerender(
    <OperationControls
      role="approver"
      isAuthenticated={false}
      isBusy={false}
      signals={[]}
      scanSummary={null}
      onRoleChange={vi.fn()}
      onScan={onScan}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onLoad={vi.fn()}
    />
  );
  expect(screen.getByRole("button", { name: "扫描业务异常" })).toBeDisabled();
});

it("keeps the business handoff limited to operator, approver, and auditor", () => {
  render(
    <OperationControls
      role="operator"
      isAuthenticated
      isBusy={false}
      signals={[]}
      scanSummary={null}
      onRoleChange={vi.fn()}
      onScan={vi.fn()}
      onInvestigate={vi.fn()}
      onRetry={vi.fn()}
      onLoad={vi.fn()}
    />
  );

  const roleSelector = screen.getByLabelText("演示角色");
  expect(roleSelector.querySelectorAll("option")).toHaveLength(3);
  expect(screen.queryByRole("option", { name: /demo-admin/ })).not.toBeInTheDocument();
  expect(screen.getByText(/每次点击实际调用 6 次只读 MCP/)).toBeInTheDocument();
});
