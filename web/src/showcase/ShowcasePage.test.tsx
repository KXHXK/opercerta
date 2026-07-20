import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ShowcasePage } from "./ShowcasePage";

afterEach(() => vi.unstubAllGlobals());

it("presents the complete evidence-backed project story without network calls", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  render(<ShowcasePage />);

  expect(screen.getByRole("heading", { name: "业务闭环" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "系统架构" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "工程证据" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "库存不足 · 补货" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "设备告警 · 维修" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "作业阻塞 · 恢复" })).toBeInTheDocument();
  for (const technology of ["React", "FastAPI", "LangGraph", "FastMCP", "PostgreSQL", "Docker Compose", "GitHub Actions"]) {
    expect(screen.getByText(technology)).toBeInTheDocument();
  }
  expect(fetchMock).not.toHaveBeenCalled();
});

it("states verified scope and unfinished boundaries with public source but no public writes", () => {
  render(<ShowcasePage />);

  expect(screen.getByRole("heading", { name: "尚未完成" })).toBeInTheDocument();
  expect(screen.getByText(/不提供公开可写服务/)).toBeInTheDocument();
  expect(screen.getByText(/release gate: CLOSED/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /GitHub 源码/i })).toHaveAttribute(
    "href",
    "https://github.com/KXHXK/opercerta"
  );
});

it("labels both screenshots as local synthetic-data evidence", () => {
  render(<ShowcasePage />);

  expect(screen.getByAltText(/本地合成数据.*审批流程/)).toBeInTheDocument();
  expect(screen.getByAltText(/本地合成数据.*审计流程/)).toBeInTheDocument();
});
