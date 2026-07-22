import { afterEach, expect, it, vi } from "vitest";

import { ApiClient } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("submits the backend approval binding unchanged with an in-memory authorization header", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ operation_id: "operation-1", status: "completed" }), {
      status: 202,
      headers: { "content-type": "application/json" }
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "Bearer memory-only");

  await client.submitApproval("operation-1", {
    scenario: "equipment",
    subject_evidence_id: "equipment-evidence",
    policy_evidence_id: "policy-evidence",
    rule_version: "rule-v1",
    decision_facts_hash: "facts-hash",
    plan_hash: "plan-hash",
    parameters: { kind: "repair", alert_code: "MOTOR_OVERHEAT", priority: "urgent" }
  }, "approved");

  expect(fetchMock).toHaveBeenCalledWith("/api/v1/operations/operation-1/approval", {
    method: "POST",
    headers: {
      Authorization: "Bearer memory-only",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      decision: "approved",
      reason: "演示审批：approved",
      expected_binding: {
        scenario: "equipment",
        subject_evidence_id: "equipment-evidence",
        policy_evidence_id: "policy-evidence",
        rule_version: "rule-v1",
        decision_facts_hash: "facts-hash",
        plan_hash: "plan-hash",
        parameters: { kind: "repair", alert_code: "MOTOR_OVERHEAT", priority: "urgent" }
      }
    })
  });
  expect(localStorage.length).toBe(0);
});

it("issues a demo token without storing it", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ access_token: "short-lived-token", token_type: "bearer", expires_in: 300 }), {
      status: 200,
      headers: { "content-type": "application/json" }
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "Bearer unused");

  await expect(client.issueToken("operator")).resolves.toBe("short-lived-token");
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/auth/demo-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: "operator" })
  });
  expect(localStorage.length).toBe(0);
});

it("prefixes requests with an explicitly configured API base URL", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ access_token: "short-lived-token" }), { status: 200 })
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "", "http://127.0.0.1:8080");

  await client.issueToken("operator");

  expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8080/api/v1/auth/demo-token", expect.any(Object));
});

it("creates and reads an operation from the selected scenario contract", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ operation_id: "operation-1", status: "awaiting_approval", created_at: "2026-07-18T00:00:00Z" }),
        { status: 202, headers: { "content-type": "application/json" } }
      )
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          operation_id: "operation-1",
          status: "awaiting_approval",
          request: { message: "补货 SKU-LOW-001" },
          evidence: [],
          assessment: null,
          plan: null,
          approval_binding: null,
          approval: null,
          work_order: null,
          result: null,
          error: null,
          last_audit_sequence: 2
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "Bearer memory-only");

  await expect(client.createOperation({
    objectType: "equipment",
    objectId: "EQ-PUMP-001",
    label: "设备告警",
    message: "检查设备并在必要时创建维修工单",
    action: "create_work_order",
    explanation: "严重告警需要审批后创建维修工单"
  }, "query")).resolves.toMatchObject({ operation_id: "operation-1" });
  await expect(client.getOperation("operation-1")).resolves.toMatchObject({ last_audit_sequence: 2 });

  expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/operations", {
    method: "POST",
    headers: { Authorization: "Bearer memory-only", "Content-Type": "application/json" },
    body: JSON.stringify({
      message: "检查设备并在必要时创建维修工单",
      requested_action: "query",
      object_type: "equipment",
      object_id: "EQ-PUMP-001"
    })
  });
  expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/operations/operation-1", {
    headers: { Authorization: "Bearer memory-only" }
  });
});

it("loads the redacted Agent Trace snapshot with the current role token", async () => {
  const trace = { run: { id: "run-1" }, events: [] };
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(trace), {
      status: 200,
      headers: { "content-type": "application/json" }
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "Bearer memory-only");

  await expect(client.getAgentTrace("operation-1")).resolves.toEqual(trace);
  expect(fetchMock).toHaveBeenCalledWith("/api/v1/operations/operation-1/agent-trace", {
    headers: { Authorization: "Bearer memory-only" }
  });
});
