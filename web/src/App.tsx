import { useMemo, useState } from "react";

import { ApiClient, userFacingError } from "./api/client";
import type {
  AgentTraceSnapshot,
  OperationDetail as OperationDetailData,
  OperationalSignal,
  SignalCaseView
} from "./api/contracts";
import { AgentTrace } from "./agent/AgentTrace";
import { DecisionComparison } from "./agent/DecisionComparison";
import { EvidenceAndCitations } from "./agent/EvidenceAndCitations";
import { IntentCard } from "./agent/IntentCard";
import { NextRoleGuide } from "./agent/NextRoleGuide";
import { readAuditSnapshot, type AuditEvent } from "./audit-stream";
import { ApprovalPanel } from "./components/ApprovalPanel";
import { AuditTimeline } from "./components/AuditTimeline";
import { OperationControls } from "./components/OperationControls";
import { OperationDetail } from "./components/OperationDetail";
import { ProjectBoundary } from "./components/ProjectBoundary";
import { EngineeringWalkthrough } from "./engineering/EngineeringWalkthrough";
import { resolveConsoleApiBaseUrl } from "./runtime/console-runtime";
import { resolvePageKind } from "./runtime/page-runtime";
import { DemoSession, type DemoRole } from "./session";
import { ConsoleUnavailable } from "./showcase/ConsoleUnavailable";
import { ShowcasePage } from "./showcase/ShowcasePage";

function casesFromSignals(signals: OperationalSignal[]): SignalCaseView[] {
  const grouped = new Map<string, OperationalSignal[]>();
  for (const signal of signals) {
    const caseKey = `${signal.object_type}:${signal.object_id}`;
    grouped.set(caseKey, [...(grouped.get(caseKey) ?? []), signal]);
  }
  return [...grouped.entries()].map(([caseKey, lineage]) => {
    const ordered = [...lineage].sort((left, right) =>
      left.detected_at.localeCompare(right.detected_at)
    );
    const currentSignal = ordered[ordered.length - 1];
    return {
      case_key: caseKey,
      object_type: currentSignal.object_type,
      object_id: currentSignal.object_id,
      current_signal: currentSignal,
      current_operation: currentSignal.operation_id === null
        ? null
        : { operation_id: currentSignal.operation_id, status: currentSignal.status },
      history_count: ordered.length - 1,
      lineage: ordered
    };
  });
}

function normalizeCases(value: SignalCaseView[] | OperationalSignal[]): SignalCaseView[] {
  if (value.length === 0 || "case_key" in value[0]) return value as SignalCaseView[];
  return casesFromSignals(value as OperationalSignal[]);
}

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
  const [trace, setTrace] = useState<AgentTraceSnapshot | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [cases, setCases] = useState<SignalCaseView[]>([]);
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [busyCaseKey, setBusyCaseKey] = useState<string | null>(null);
  const [scanSummary, setScanSummary] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [message, setMessage] = useState("点击“扫描业务异常”即可开始；首次点击会自动签发本地 operator 演示 JWT。");

  async function loadOperation(operationId: string): Promise<string | null> {
    const nextDetail = await client.getOperation(operationId);
    setDetail(nextDetail);
    let traceWarning: string | null = null;
    try {
      setTrace(await client.getAgentTrace(operationId));
    } catch (error) {
      setTrace((current) => current?.run.operation_id === operationId ? current : null);
      traceWarning = userFacingError(
        error,
        "Agent Trace 暂时不可读，请稍后重试或切换 auditor。"
      );
    }
    const snapshot = await readAuditSnapshot(operationId, 0, session.authorizationHeader());
    setEvents(snapshot);
    return traceWarning;
  }

  async function selectRole(nextRole: DemoRole) {
    setRole(nextRole);
    setIsAuthenticated(false);
    setMessage("正在获取演示身份…");
    try {
      await session.selectRole(nextRole);
      setIsAuthenticated(true);
      setMessage(`已切换为 ${nextRole}；令牌仅保存在当前页面内存。`);
      if (detail !== null) {
        try {
          setTrace(await client.getAgentTrace(detail.operation_id));
        } catch (error) {
          setTrace((current) => current?.run.operation_id === detail.operation_id ? current : null);
          setMessage(
            `已切换为 ${nextRole}；${userFacingError(
              error,
              "Agent Trace 暂时不可读，请稍后重试或切换 auditor。"
            )}`
          );
        }
      }
    } catch (error) {
      setMessage(userFacingError(error, "演示身份获取失败，请确认本地 API 已启动后重试。"));
    }
  }

  async function scanSignals() {
    setIsBusy(true);
    setMessage("正在读取业务事实并执行确定性异常检测…");
    try {
      if (!isAuthenticated) {
        await session.selectRole("operator");
        setRole("operator");
        setIsAuthenticated(true);
      }
      const result = await client.scanSignals();
      let activeCases = result.affected_cases ?? casesFromSignals(result.signals);
      try {
        activeCases = normalizeCases(await client.listSignalCases());
      } catch {
        // The affected cases from this scan remain useful if the list refresh fails.
      }
      setCases(activeCases);
      setScanSummary(
        `本次扫描 ${result.scanned_at}：检查 ${result.scanned_count} 个对象，命中 ${result.signals.length} 条异常；相同事实会复用 PostgreSQL 中的既有信号。`
      );
      setMessage(
        result.issues.length === 0
          ? `扫描完成：检查 ${result.scanned_count} 个对象，发现 ${result.signals.length} 条异常信号。`
          : `扫描完成：发现 ${result.signals.length} 条异常，另有 ${result.issues.length} 个数据源需要检查。`
      );
    } catch (error) {
      setMessage(userFacingError(error, "异常扫描失败，请检查 API、MCP 与数据库状态。"));
    } finally {
      setIsBusy(false);
    }
  }

  async function investigateSignal(caseKey: string, signal: OperationalSignal) {
    setIsBusy(true);
    setBusyCaseKey(caseKey);
    setSelectedCaseKey(caseKey);
    setMessage(`正在让 Agent 调查 ${signal.object_id} 的已检测异常…`);
    try {
      const accepted = await client.investigateSignal(signal.id);
      setCases(normalizeCases(await client.listSignalCases()));
      const warning = await loadOperation(accepted.operation_id);
      setMessage(
        warning === null
          ? `Agent 已接手异常并生成可审计处置：${accepted.operation_id}`
          : `Agent 已接手异常；${warning}`
      );
    } catch (error) {
      setMessage(userFacingError(error, "未能启动 Agent 调查，请读取最新信号状态后重试。"));
    } finally {
      setBusyCaseKey(null);
      setIsBusy(false);
    }
  }

  async function retrySignal(caseKey: string, signal: OperationalSignal) {
    setIsBusy(true);
    setBusyCaseKey(caseKey);
    setSelectedCaseKey(caseKey);
    setMessage(`正在为 ${signal.object_id} 创建带审计 lineage 的后继调查…`);
    try {
      const accepted = await client.retrySignal(signal.id);
      setCases(normalizeCases(await client.listSignalCases()));
      const warning = await loadOperation(accepted.operation_id);
      setMessage(
        warning === null
          ? `后继 Agent 调查已启动，新处置：${accepted.operation_id}`
          : `后继 Agent 调查已启动；${warning}`
      );
    } catch (error) {
      try {
        setCases(normalizeCases(await client.listSignalCases()));
      } catch {
        // Preserve the original actionable retry error.
      }
      setMessage(userFacingError(error, "未能创建后继调查，请读取最新信号状态后重试。"));
    } finally {
      setBusyCaseKey(null);
      setIsBusy(false);
    }
  }

  async function readOperation(operationId: string, caseKey?: string) {
    setIsBusy(true);
    if (caseKey !== undefined) {
      setSelectedCaseKey(caseKey);
      setBusyCaseKey(caseKey);
    }
    setMessage("正在读取处置与审计快照…");
    try {
      const warning = await loadOperation(operationId);
      setMessage(
        warning === null ? `已读取处置：${operationId}` : `已读取业务详情；${warning}`
      );
    } catch (error) {
      setMessage(
        userFacingError(error, "未能读取处置，请检查编号、角色权限或本地服务状态。")
      );
    } finally {
      if (caseKey !== undefined) setBusyCaseKey(null);
      setIsBusy(false);
    }
  }

  async function submitDecision(decision: "approved" | "rejected") {
    if (detail === null || detail.approval_binding === null) return;
    await client.submitApproval(detail.operation_id, detail.approval_binding, decision);
    try {
      const warning = await loadOperation(detail.operation_id);
      setMessage(
        warning === null
          ? `审批已提交并读取最新处置：${detail.operation_id}`
          : `审批已提交并读取业务详情；${warning}`
      );
    } catch (error) {
      setMessage(
        `审批已提交，但未能读取最新处置；${userFacingError(
          error,
          "请切换 auditor 或稍后读取。"
        )}`
      );
    }
  }

  return (
    <main className="console-shell">
      <header className="console-header">
        <div>
          <p className="eyebrow">CONTROLLED AGENT WORKSPACE · 本地合成数据</p>
          <h1>OperCerta｜智能运营处置 Agent</h1>
          <p className="console-subtitle">业务系统先发现异常，Agent 再通过 LangGraph、MCP 与 SOP 调查；人工审批后验证并幂等写入。</p>
        </div>
        <div className="console-runtime-state">
          <span>{trace === null ? "MODEL PENDING" : `${trace.run.model_mode.toUpperCase()} MODEL`}</span>
          <p className="gate">发布门禁：CLOSED</p>
        </div>
      </header>
      <p className="console-message" role="status">{isBusy ? "处理中：" : ""}{message}</p>
      <ol className="agent-flow-strip" aria-label="Agent 业务链路">
        {["异常信号", "Goal", "Tool / RAG", "规则", "审批", "Verifier", "工单"].map((step, index) => (
          <li key={step} className={trace !== null && index < 4 ? "is-active" : undefined}>
            <span>{String(index + 1).padStart(2, "0")}</span>{step}
          </li>
        ))}
      </ol>
      <section className="agent-workspace" aria-label="运营控制台">
        <aside className="workspace-sidebar">
          <article className="panel control-panel" aria-label="操作控制区">
            <div className="panel-heading"><span>CONTROL</span><h2>操作控制区</h2></div>
            <OperationControls
              role={role}
              isAuthenticated={isAuthenticated}
              isBusy={isBusy}
              cases={cases}
              selectedCaseKey={selectedCaseKey}
              busyCaseKey={busyCaseKey}
              scanSummary={scanSummary}
              onRoleChange={(nextRole) => void selectRole(nextRole)}
              onScan={() => void scanSignals()}
              onInvestigate={() => undefined}
              onRetry={() => undefined}
              onSelectCase={setSelectedCaseKey}
              onInvestigateCase={(caseKey, signal) => void investigateSignal(caseKey, signal)}
              onRetryCase={(caseKey, signal) => void retrySignal(caseKey, signal)}
              onLoadCase={(caseKey, operationId) => void readOperation(operationId, caseKey)}
              onLoad={(operationId) => void readOperation(operationId)}
            />
          </article>
          <NextRoleGuide
            role={role}
            status={detail?.status ?? null}
            hasWorkOrder={detail?.work_order !== null && detail?.work_order !== undefined}
          />
        </aside>
        <div className="workspace-main">
          <div className="workspace-summary-grid">
            <IntentCard detail={detail} trace={trace} />
            <article className="panel fact-panel" aria-label="业务事实区">
              <div className="panel-heading"><span>BUSINESS STATE</span><h2>业务事实区</h2></div>
              <OperationDetail detail={detail} />
            </article>
          </div>
          <AgentTrace trace={trace} />
          <div className="workspace-analysis-grid">
            <section className="panel" aria-label="工具事实与引用面板">
              <div className="panel-heading"><span>OBSERVATIONS</span><h2>工具事实与 SOP 引用</h2></div>
              <EvidenceAndCitations trace={trace} />
            </section>
            <section className="panel" aria-label="决策对照面板">
              <div className="panel-heading"><span>DECISION</span><h2>建议与确定性边界</h2></div>
              <DecisionComparison detail={detail} trace={trace} />
            </section>
          </div>
          <div className="workspace-outcome-grid">
            <article className="panel approval-panel" aria-label="审批与绑定">
              <div className="panel-heading"><span>HUMAN IN THE LOOP</span><h2>审批与绑定</h2></div>
              <ApprovalPanel
                role={role}
                binding={detail?.approval_binding ?? null}
                onDecision={submitDecision}
              />
            </article>
            <article className="panel audit-panel" aria-label="审计时间线">
              <div className="panel-heading"><span>AUDIT</span><h2>业务审计时间线</h2></div>
              <AuditTimeline events={events} />
            </article>
          </div>
        </div>
      </section>
      <ProjectBoundary />
    </main>
  );
}

type AppProps = {
  development?: boolean;
  hostname?: string;
};

export default function App({
  development = import.meta.env.DEV,
  hostname = window.location.hostname,
}: AppProps = {}) {
  const page = resolvePageKind(window.location.pathname, hostname, development);
  if (page === "showcase") return <ShowcasePage />;
  if (page === "engineering") return <EngineeringWalkthrough />;
  if (page === "console") {
    const apiBaseUrl = resolveConsoleApiBaseUrl(hostname);
    return apiBaseUrl === null ? <ConsoleUnavailable /> : <ConsoleApp apiBaseUrl={apiBaseUrl} />;
  }
  return (
    <main className="not-found">
      <h1>页面不存在</h1>
      <a href="/">返回项目专题</a>
    </main>
  );
}
