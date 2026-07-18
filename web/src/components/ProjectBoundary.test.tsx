import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { ProjectBoundary } from "./ProjectBoundary";

it("states the local-demo boundary and closed release gate", () => {
  render(<ProjectBoundary />);

  expect(screen.getByText("发布门禁保持 CLOSED")).toBeInTheDocument();
  expect(screen.getByText(/不包含生产 IAM、SSO、实时订阅或公开部署/)).toBeInTheDocument();
});
