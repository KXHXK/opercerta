import { expect, it, vi } from "vitest";

import { DemoSession } from "./session";

it("keeps the demo token in memory and clears it when the role changes", async () => {
  const issueToken = vi.fn().mockResolvedValue("short-lived-token");
  const session = new DemoSession(issueToken);

  await session.selectRole("operator");
  expect(session.authorizationHeader()).toBe("Bearer short-lived-token");
  await session.selectRole("auditor");

  expect(issueToken).toHaveBeenCalledWith("operator");
  expect(issueToken).toHaveBeenCalledWith("auditor");
  expect(localStorage.length).toBe(0);
  expect(session.authorizationHeader()).toBe("Bearer short-lived-token");
});
