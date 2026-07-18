import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { AuditTimeline } from "./AuditTimeline";

it("renders audit events in sequence order with readable status labels", () => {
  render(
    <AuditTimeline
      events={[
        { sequence: 4, type: "operation_completed", data: {} },
        { sequence: 3, type: "approval_requested", data: { request: "approved" } }
      ]}
    />
  );

  const entries = screen.getAllByRole("listitem");
  expect(entries).toHaveLength(2);
  expect(entries[0]).toHaveTextContent("#3");
  expect(entries[0]).toHaveTextContent("等待审批");
  expect(entries[1]).toHaveTextContent("#4");
  expect(entries[1]).toHaveTextContent("处置完成");
});

it("explains the empty audit state", () => {
  render(<AuditTimeline events={[]} />);

  expect(screen.getByText("暂无可回放的审计事件")).toBeInTheDocument();
});
