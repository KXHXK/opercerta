import { useMemo, useState } from "react";

import { ApiClient } from "./api/client";
import type { OperationDetail as OperationDetailData } from "./api/contracts";
import { readAuditSnapshot, type AuditEvent } from "./audit-stream";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { AuditTimeline } from "./components/AuditTimeline";
import { OperationControls } from "./components/OperationControls";
import { OperationDetail } from "./components/OperationDetail";
import { ProjectBoundary } from "./components/ProjectBoundary";
import { resolveConsoleApiBaseUrl } from "./runtime/console-runtime";
import { DemoSession, type DemoRole } from "./session";
import { ConsoleUnavailable } from "./showcase/ConsoleUnavailable";
import { ShowcasePage } from "./showcase/ShowcasePage";

function ConsoleApp({ apiBaseUrl }: { apiBaseUrl: string }) {
  const tokenClient = useMemo(() => new ApiClient(() => "", apiBaseUrl), [apiBaseUrl]);
  const session = useMemo(
    () => new DemoSession((role) => tokenClient.issueToken(role)),
    [tokenClient]
  );
  const client = useMemo(() => new ApiClient(() => session.authorizationHeader(), apiBaseUrl), [apiBaseUrl, session]);
  const [role, setRole] = useState<DemoRole>("operator");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [detail, setDetail] = useState<OperationDetailData | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState("请选择演示角色以获取内存 JWT。");

  async function loadOperation(operationId: string) {
    const nextDetail = await client.getOperation(operationId);
    setDetail(nextDetail);
    const snapshot = await readAuditSnapshot(operationId, 0, session.authorizationHeader());
    setEvents(snapshot);
  }

  async function selectRole(nextRole: DemoRole) {
    setRole(nextRole);
    setIsAuthenticated(false);
    setMessage("正在获取演示身份…");
    try {
      await session.selectRole(nextRole);
      setIsAuthenticated(true);
      setMessage(`已切换为 ${nextRole}；令牌仅保存在当前页面内存。`);
    } catch {
      setMessage("演示身份获取失败，请确认本地 API 已启动后重试。");
    }
  }

  async function createOperation(sku: string) {
    setIsBusy(true);
    setMessage("正在创建补货处置…");
    try {
      const accepted = await client.createOperation(sku);
      await loadOperation(accepted.operation_id);
      setMessage(`已读取后端创建的处置：${accepted.operation_id}`);
    } catch {
      setMessage("处置创建或审计回放失败，请检查本地服务状态后重试。");
    } finally {
      setIsBusy(false);
    }
  }

  async function readOperation(operationId: string) {
    setIsBusy(true);
    setMessage("正在读取处置与审计快照…");
    try {
      await loadOperation(operationId);
      setMessage(`已读取处置：${operationId}`);
    } catch {
      setMessage("未能读取处置，请检查编号、角色权限或本地服务状态。");
    } finally {
      setIsBusy(false);
    }
  }

  async function submitDecision(decision: "approved" | "rejected") {
    if (detail === null || detail.approval_binding === null) return;
    await client.submitApproval(detail.operation_id, detail.approval_binding, decision);
    await loadOperation(detail.operation_id);
  }

  return (
    <main className="console-shell">
      <header className="console-header">
        <div>
          <p className="eyebrow">本地合成数据演示</p>
          <h1>OperCerta｜智能运营处置 Agent</h1>
        </div>
        <p className="gate">发布门禁：CLOSED</p>
      </header>
      <p className="console-message" role="status">{isBusy ? "处理中：" : ""}{message}</p>
      <section className="console-grid" aria-label="运营控制台">
        <article className="panel" aria-label="操作控制区">
          <h2>操作控制区</h2>
          <OperationControls
            role={role}
            isAuthenticated={isAuthenticated && !isBusy}
            onRoleChange={(nextRole) => void selectRole(nextRole)}
            onCreate={(sku) => void createOperation(sku)}
            onLoad={(operationId) => void readOperation(operationId)}
          />
        </article>
        <article className="panel" aria-label="业务事实区">
          <h2>业务事实区</h2>
          <OperationDetail detail={detail} />
          <h2>审批与绑定</h2>
          <ApprovalPanel
            role={role}
            binding={detail?.approval_binding ?? null}
            onDecision={submitDecision}
          />
        </article>
        <article className="panel" aria-label="审计时间线">
          <h2>审计时间线</h2>
          <AuditTimeline events={events} />
        </article>
      </section>
      <ProjectBoundary />
    </main>
  );
}

export default function App() {
  if (window.location.pathname === "/") return <ShowcasePage />;
  if (window.location.pathname === "/console") {
    const apiBaseUrl = resolveConsoleApiBaseUrl(window.location.hostname);
    return apiBaseUrl === null ? <ConsoleUnavailable /> : <ConsoleApp apiBaseUrl={apiBaseUrl} />;
  }
  return <main className="console-unavailable"><h1>页面不存在</h1><a href="/">返回项目专题</a></main>;
}
