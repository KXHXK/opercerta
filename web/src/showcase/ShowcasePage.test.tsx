import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ShowcasePage } from "./ShowcasePage";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

it("gives recruiters the verified three-business story without network calls", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<ShowcasePage />);

  expect(
    screen.getByRole("heading", { name: /可审批、可恢复的运营工单/ }),
  ).toBeInTheDocument();
  expect(screen.getByText("3 条业务闭环")).toBeInTheDocument();
  expect(screen.getByText("42 条固定评测")).toBeInTheDocument();
  expect(screen.getByText("9 条真实模型路径")).toBeInTheDocument();
  for (const name of ["库存不足 → 补货", "设备告警 → 维修", "作业阻塞 → 恢复"]) {
    expect(screen.getByRole("heading", { name })).toBeInTheDocument();
  }
  expect(fetchMock).not.toHaveBeenCalled();
});

it("shows the implemented agent harness and cyclic decision architecture", () => {
  render(<ShowcasePage />);

  for (const label of [
    "Prompt Registry",
    "Context & Goal Encoder",
    "AgentHarness",
    "ToolPolicy",
    "Observation 校验",
    "Trace Recorder",
  ]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  expect(screen.getByRole("heading", { name: "感知 → 决策 → 行动 → 反馈的受控循环" })).toBeInTheDocument();
  expect(screen.getByText(/LangGraph 负责状态编排与恢复/)).toBeInTheDocument();
  expect(screen.getByText(/Redis 只缓存调查阶段的只读证据/)).toBeInTheDocument();
});

it("publishes exact reproducible evaluation results and honest limits", () => {
  render(<ShowcasePage />);

  for (const result of [
    "682 / 682",
    "60 / 60",
    "42 / 42",
    "3 / 3",
    "19.722 s",
    "31.333 s",
  ]) {
    expect(screen.getByText(result)).toBeInTheDocument();
  }
  expect(screen.getAllByText("9 / 9")).toHaveLength(2);
  expect(screen.getByText(/9 条固定本地合成路径/)).toBeInTheDocument();
  expect(screen.getByText(/不等同于生产准确率、SLA 或供应商基准/)).toBeInTheDocument();
});

it("does not present a generated template, tutorial, or public write action", () => {
  render(<ShowcasePage />);
  const text = document.body.textContent ?? "";
  for (const forbidden of [
    "AI 生成",
    "Codex 生成",
    "Built with Codex",
    "Mock 模型",
    "入门",
    "学习中",
    "在线运行",
    "创建工单",
  ]) {
    expect(text).not.toContain(forbidden);
  }
  expect(screen.getByText(/静态项目专题/)).toBeInTheDocument();
  expect(screen.getByText(/生产门禁.*CLOSED/)).toBeInTheDocument();
});

it("moves within the page without adding a location hash", () => {
  const scrollIntoView = vi.fn();
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  render(<ShowcasePage />);

  fireEvent.click(screen.getByRole("button", { name: "流程" }));

  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  expect(window.location.hash).toBe("");
});

it("labels both screenshots as local synthetic-data evidence", () => {
  render(<ShowcasePage />);

  expect(screen.getByAltText("本地控制台等待审批状态")).toBeInTheDocument();
  expect(screen.getByAltText("本地控制台审计事件回放")).toBeInTheDocument();
  expect(screen.getAllByText(/本地合成数据运行证据/)).toHaveLength(2);
});
