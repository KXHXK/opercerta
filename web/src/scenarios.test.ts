import { expect, it } from "vitest";

import { operationScenarios } from "./scenarios";

it("publishes exactly the three implemented business scenarios", () => {
  expect(operationScenarios.map((scenario) => scenario.objectType)).toEqual([
    "inventory",
    "equipment",
    "task"
  ]);
  expect(operationScenarios.every((scenario) => scenario.action === "create_work_order")).toBe(true);
});
