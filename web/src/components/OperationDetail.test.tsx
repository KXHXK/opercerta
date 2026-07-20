import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { OperationDetail } from "./OperationDetail";

it("shows the current operation state and server-issued identifier", () => {
  render(
    <OperationDetail
      detail={{
        operation_id: "operation-1",
        status: "awaiting_approval",
        request: { message: "为 SKU-LOW-001 创建库存补货工单", object_type: "inventory", object_id: "SKU-LOW-001" },
        evidence: [], assessment: null, plan: null, approval_binding: null, approval: null,
        work_order: null, result: null, error: null, last_audit_sequence: 2
      }}
    />
  );

  expect(screen.getByText("等待审批")).toBeInTheDocument();
  expect(screen.getByText("operation-1")).toBeInTheDocument();
  expect(screen.getByText("审计序列：2")).toBeInTheDocument();
});

it("shows the single backend work order after a completed operation", () => {
  render(
    <OperationDetail
      detail={{
        operation_id: "operation-1",
        status: "completed",
        request: { message: "为 SKU-LOW-001 创建库存补货工单", object_type: "inventory", object_id: "SKU-LOW-001" },
        evidence: [], assessment: null, plan: null, approval_binding: null,
        approval: { decision: "approved", reason: "approved in demo" },
        work_order: { id: "work-order-1", status: "created", payload: { quantity: 18 } },
        result: { outcome: "work_order_completed", work_order_id: "work-order-1" },
        error: null, last_audit_sequence: 10
      }}
    />
  );

  expect(screen.getByText("工单编号")).toBeInTheDocument();
  expect(screen.getByText("work-order-1")).toBeInTheDocument();
  expect(screen.getByText("created")).toBeInTheDocument();
});
