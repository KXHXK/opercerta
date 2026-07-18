import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { OperationControls } from "./OperationControls";

it("only enables creation for an authenticated operator", () => {
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

  expect(screen.getByRole("button", { name: "创建补货处置" })).toBeDisabled();

  rerender(
    <OperationControls
      role="operator"
      isAuthenticated
      onRoleChange={vi.fn()}
      onCreate={onCreate}
      onLoad={vi.fn()}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: "创建补货处置" }));

  expect(onCreate).toHaveBeenCalledWith("SKU-LOW-001");
});
