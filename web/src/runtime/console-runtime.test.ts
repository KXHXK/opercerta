import { describe, expect, it } from "vitest";

import { resolveConsoleApiBaseUrl } from "./console-runtime";

describe("resolveConsoleApiBaseUrl", () => {
  it("uses the local Vite proxy on localhost", () => {
    expect(resolveConsoleApiBaseUrl("localhost")).toBe("");
  });

  it("uses an explicit HTTPS API base URL", () => {
    expect(resolveConsoleApiBaseUrl("opercerta.netlify.app", "https://api.example.test/")).toBe(
      "https://api.example.test"
    );
  });

  it("disables the console on a public host without an API URL", () => {
    expect(resolveConsoleApiBaseUrl("opercerta.netlify.app")).toBeNull();
  });
});
