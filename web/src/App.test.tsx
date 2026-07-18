import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import App from "./App";

it("renders the OperCerta console shell", () => {
  render(<App />);

  expect(screen.getByText("OperCerta｜智能运营处置 Agent")).toBeInTheDocument();
  expect(screen.getByText("发布门禁：CLOSED")).toBeInTheDocument();
});
