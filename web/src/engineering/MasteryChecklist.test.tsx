import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { MasteryChecklist } from "./MasteryChecklist";

afterEach(() => localStorage.clear());

it("persists only local mastery item ids", () => {
  render(<MasteryChecklist />);

  fireEvent.click(screen.getByRole("checkbox", { name: /画出完整请求链路/ }));

  expect(JSON.parse(localStorage.getItem("opercerta.engineering.mastery.v1") ?? "[]")).toEqual([
    "explain-flow",
  ]);
});

it("recovers from invalid local mastery state and can reset", () => {
  localStorage.setItem("opercerta.engineering.mastery.v1", "not-json");
  render(<MasteryChecklist />);

  expect(screen.getAllByRole("checkbox", { checked: false })).toHaveLength(4);
  fireEvent.click(screen.getByRole("button", { name: "重置本地进度" }));

  expect(localStorage.getItem("opercerta.engineering.mastery.v1")).toBeNull();
});

it("ignores unknown ids restored from local storage", () => {
  localStorage.setItem(
    "opercerta.engineering.mastery.v1",
    JSON.stringify(["unknown-item", "run-business"]),
  );
  render(<MasteryChecklist />);

  expect(screen.getAllByRole("checkbox", { checked: true })).toHaveLength(1);
  expect(screen.getByRole("checkbox", { name: /亲手完成 query/ })).toBeChecked();
});
