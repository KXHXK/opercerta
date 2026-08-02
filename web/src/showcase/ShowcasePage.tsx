import { AgentArchitecture } from "./AgentArchitecture";
import { EvaluationResults } from "./EvaluationResults";
import { OperationFlow } from "./OperationFlow";
import { PROJECT_FACTS, PUBLIC_LIMITATIONS, sourceHref } from "./project-facts";
import { ReliabilityEvidence } from "./ReliabilityEvidence";
import { ScenarioStories } from "./ScenarioStories";
import { SectionNav } from "./SectionNav";

export function ShowcasePage() {
  return (
    <main className="showcase-shell">
      <SectionNav />
      <section className="showcase-hero" aria-labelledby="showcase-title">
        <p className="eyebrow">OPERATIONS CONTROL AGENT · LOCAL RELEASE CANDIDATE</p>
        <h1 id="showcase-title">可审批、可恢复的运营工单 Agent</h1>
        <p className="hero-summary">
          OperCerta 把 LLM 的目标理解、规划、工具调用与证据综合接入三条运营处置闭环；
          Agent Harness、LangGraph、HITL 和 PostgreSQL 共同约束高风险写入，使每一步可验证、可恢复、可审计。
        </p>
        <dl className="fact-strip">
          <div>
            <dt>业务范围</dt>
            <dd>{PROJECT_FACTS.businessLoops} 条业务闭环</dd>
          </div>
          <div>
            <dt>回归基线</dt>
            <dd>{PROJECT_FACTS.frozenEvaluations} 条固定评测</dd>
          </div>
          <div>
            <dt>真实模型</dt>
            <dd>{PROJECT_FACTS.realModelPaths} 条真实模型路径</dd>
          </div>
          <div>
            <dt>产品状态</dt>
            <dd>{PROJECT_FACTS.releaseGate}</dd>
          </div>
        </dl>
      </section>

      <section id="business" className="showcase-section" aria-labelledby="business-title">
        <p className="section-kicker">THREE CONTROLLED LOOPS</p>
        <h2 id="business-title">三种业务，共享一套可靠性内核</h2>
        <ScenarioStories />
      </section>

      <section id="flow" className="showcase-section" aria-labelledby="flow-title">
        <p className="section-kicker">END-TO-END OPERATION</p>
        <h2 id="flow-title">从异常信号到工单终态的完整运行过程</h2>
        <OperationFlow />
      </section>

      <section
        id="architecture"
        className="showcase-section"
        aria-labelledby="architecture-title"
      >
        <p className="section-kicker">AGENT ARCHITECTURE & HARNESS</p>
        <h2 id="architecture-title">感知 → 决策 → 行动 → 反馈的受控循环</h2>
        <p>
          FastAPI 是可信准入边界，LangGraph 是单根 Agent 的状态机与恢复骨架，Kimi 是受契约约束的认知层，
          MCP、RAG 与数据库提供可追溯事实；写操作必须经过人类批准和确定性终审。
        </p>
        <AgentArchitecture />
      </section>

      <section id="evidence" className="showcase-section" aria-labelledby="evidence-title">
        <p className="section-kicker">VERIFIED BEHAVIOR</p>
        <h2 id="evidence-title">测试、评测与真实模型结果</h2>
        <EvaluationResults />
        <h3 className="subsection-title">可靠性内核</h3>
        <ReliabilityEvidence />
        <div className="evidence-gallery">
          <figure>
            <img src="/evidence/console-approval-flow.png" alt="本地控制台等待审批状态" />
            <figcaption>本地合成数据运行证据：等待审批</figcaption>
          </figure>
          <figure>
            <img src="/evidence/console-audit-flow.png" alt="本地控制台审计事件回放" />
            <figcaption>本地合成数据运行证据：审计回放</figcaption>
          </figure>
        </div>
        <a
          href={sourceHref("docs/release-evidence/real-model-quality-evaluation.md")}
          target="_blank"
          rel="noreferrer"
        >
          查看真实模型质量评测证据
        </a>
      </section>

      <section
        id="boundary"
        className="showcase-section boundary-section"
        aria-labelledby="boundary-title"
      >
        <p className="section-kicker">HONEST BOUNDARY</p>
        <h2 id="boundary-title">公开静态展示 + 本地可复现 Agent MVP</h2>
        <p>
          当前网站是即时打开的静态项目专题，不连接可写后端；完整三业务 Agent、真实模型调用与审批写入在本地
          WSL2 + Docker Compose 复现，并以源码、自动化结果和录屏展示。它不是公网交互产品；生产身份、
          托管数据库和公网写服务仍未建设。
        </p>
        <p className="gate">生产门禁：{PROJECT_FACTS.releaseGate}</p>
        <ul>
          {PUBLIC_LIMITATIONS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <a href="https://github.com/KXHXK/opercerta" target="_blank" rel="noreferrer">
          查看公开源码与测试
        </a>
      </section>
      <footer className="showcase-footer">EXPLAINABLE · REVERSIBLE · AUDITABLE</footer>
    </main>
  );
}
