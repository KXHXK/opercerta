import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { OperationControls } from "./OperationControls";
import { operationScenarios } from "../scenarios";

it("offers real query and creation actions only to an authenticated operator", () => {
  const onCreate = vi.fn();
  const { rerender } = render(
    <OperationControls
      role="approver"
      isAuthenticated
      onRoleChange={vi.fn()}
      onCreate={onCreate}
      onLoad={vi.fn()}
    />
  );

  expect(screen.getByRole("button", { name: "创建处置" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "查询状态" })).toBeDisabled();

  rerender(
    <OperationControls
      role="operator"
      isAuthenticated
      onRoleChange={vi.fn()}
      onCreate={onCreate}
      onLoad={vi.fn()}
    />
  );
  fireEvent.change(screen.getByLabelText("业务场景"), { target: { value: "equipment" } });
  fireEvent.click(screen.getByRole("button", { name: "查询状态" }));
  fireEvent.click(screen.getByRole("button", { name: "创建处置" }));

  expect(onCreate).toHaveBeenNthCalledWith(1, operationScenarios[1], "query");
  expect(onCreate).toHaveBeenNthCalledWith(2, operationScenarios[1], "create_work_order");
});

it("keeps the business handoff limited to operator, approver, and auditor", () => {
  render(
    <OperationControls
      role="operator"
      isAuthenticated
      onRoleChange={vi.fn()}
      onCreate={vi.fn()}
      onLoad={vi.fn()}
    />
  );

  const roleSelector = screen.getByLabelText("演示角色");
  expect(roleSelector.querySelectorAll("option")).toHaveLength(3);
  expect(screen.queryByRole("option", { name: /demo-admin/ })).not.toBeInTheDocument();
});
