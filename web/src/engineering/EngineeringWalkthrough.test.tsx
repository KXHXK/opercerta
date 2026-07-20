import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { EngineeringWalkthrough } from "./EngineeringWalkthrough";

it("maps every engineering step to source, evidence, failure behavior and an interview prompt", () => {
  render(<EngineeringWalkthrough />);

  expect(screen.getAllByRole("button", { name: /查看步骤/ })).toHaveLength(10);
  for (const label of [
    "React",
    "FastAPI",
    "LangGraph",
    "FastMCP",
    "PostgreSQL",
    "Redis",
    "Kimi K2.6",
    "Docker Compose",
    "OpenTelemetry",
    "GitHub Actions",
  ]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  expect(screen.getByText("inventory.get_snapshot")).toBeInTheDocument();
  expect(screen.getByText("equipment.get_status")).toBeInTheDocument();
  expect(screen.getByText("task.get_status")).toBeInTheDocument();
});

it("links selected steps to inspectable source and automated evidence", () => {
  render(<EngineeringWalkthrough />);

  expect(screen.getByRole("link", { name: "web/src/components/OperationControls.tsx" })).toHaveAttribute(
    "href",
    "https://github.com/KXHXK/opercerta/blob/main/web/src/components/OperationControls.tsx",
  );
  expect(screen.getByText("为什么前端不能提交 approver identity？")).toBeInTheDocument();
  expect(screen.getByText(/身份或 API 不可用时显示固定安全提示/)).toBeInTheDocument();
});

it("turns real incidents into local interview review material", () => {
  render(<EngineeringWalkthrough />);

  expect(screen.getByRole("heading", { name: "真实故障复盘" })).toBeInTheDocument();
  expect(screen.getAllByText("面试表达")).toHaveLength(10);
  expect(screen.getByText("WSL2 功能启用后被 Windows 回滚")).toBeInTheDocument();
  expect(screen.getByText("OpenAI-compatible 不等于参数完全兼容")).toBeInTheDocument();
  expect(screen.getByText("本地 Compose 配置误回显后立即轮换")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "掌握检查" })).toBeInTheDocument();
});
