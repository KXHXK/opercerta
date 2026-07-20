import { describe, expect, it } from "vitest";

import { resolvePageKind } from "./page-runtime";

describe("resolvePageKind", () => {
  it("keeps the public showcase at root", () => {
    expect(resolvePageKind("/", "opercerta-kxh.netlify.app", false)).toBe("showcase");
  });

  it.each(["localhost", "127.0.0.1"])(
    "allows the engineering walkthrough on local development host %s",
    (hostname) => {
      expect(resolvePageKind("/engineering", hostname, true)).toBe("engineering");
    },
  );

  it("does not expose the engineering walkthrough in production", () => {
    expect(resolvePageKind("/engineering", "opercerta-kxh.netlify.app", false)).toBe(
      "not-found",
    );
  });

  it("preserves the real local console route", () => {
    expect(resolvePageKind("/console", "localhost", true)).toBe("console");
  });
});
