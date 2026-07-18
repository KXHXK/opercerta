import { afterEach, expect, it, vi } from "vitest";

import { ApiClient } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("submits only the six approval binding fields with an in-memory authorization header", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ operation_id: "operation-1", status: "completed" }), {
      status: 202,
      headers: { "content-type": "application/json" }
    })
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new ApiClient(() => "Bearer memory-only");

  await client.submitApproval("operation-1", {
    inventory_evidence_id: "inventory-evidence",
    policy_evidence_id: "policy-evidence",
    rule_version: "rule-v1",
    decision_facts_hash: "facts-hash",
    plan_hash: "plan-hash",
    recommended_quantity: 18
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
      expected_inventory_evidence_id: "inventory-evidence",
      expected_policy_evidence_id: "policy-evidence",
      expected_rule_version: "rule-v1",
      expected_decision_facts_hash: "facts-hash",
      expected_plan_hash: "plan-hash",
      expected_recommended_quantity: 18
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
