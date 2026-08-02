import { expect, it } from "vitest";

import { MCP_TOOLS, PROJECT_FACTS, SCENARIOS } from "./project-facts";

it("keeps evidence-backed release facts and three typed scenarios", () => {
  expect(PROJECT_FACTS).toMatchObject({
    businessLoops: 3,
    frozenEvaluations: 42,
    realModelPaths: 9,
    backendTests: 682,
    frontendTests: 60,
    agentSafetyEvaluations: 9,
    promptInjectionPasses: 3,
    endToEndP50Seconds: 19.722,
    endToEndP95Seconds: 31.333,
    releaseGate: "CLOSED",
  });
  expect(SCENARIOS.map((scenario) => scenario.workOrderKind)).toEqual([
    "replenishment",
    "repair",
    "task_recovery",
  ]);
  expect(MCP_TOOLS).toEqual([
    "inventory.get_snapshot",
    "equipment.get_status",
    "task.get_status",
    "policy.list_constraints",
    "work_order.create",
    "work_order.get",
  ]);
});
