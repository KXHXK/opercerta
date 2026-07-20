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
          OperCerta 用三条合成业务闭环展示受控 Agent 后端：模型负责解释，确定性代码决定动作，PostgreSQL
          约束批准与写入。
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
            <dd>{PROJECT_FACTS.realModelOperations} 次真实模型代表操作</dd>
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
        <p className="section-kicker">90 SECOND TRACE</p>
        <h2 id="flow-title">一次写路径如何变成可审计终态</h2>
        <OperationFlow />
      </section>

      <section
        id="architecture"
        className="showcase-section"
        aria-labelledby="architecture-title"
      >
        <p className="section-kicker">SYSTEM BOUNDARIES</p>
        <h2 id="architecture-title">模型不拥有业务副作用</h2>
        <p>
          React → FastAPI → OperationRunner → LangGraph → MCP/FastMCP、Kimi 与 PostgreSQL；FastAPI 再以
          SSE 回放有序审计事件。
        </p>
        <ul className="architecture-boundaries">
          <li>
            Kimi K2.6 只返回 <code>summary</code> 与 <code>rationale</code>。
          </li>
          <li>规则、动作、审批参数和幂等键由类型化领域代码决定。</li>
          <li>Redis 只缓存初次只读证据；批准后直接重读 MCP 事实。</li>
        </ul>
      </section>

      <section id="evidence" className="showcase-section" aria-labelledby="evidence-title">
        <p className="section-kicker">VERIFIED BEHAVIOR</p>
        <h2 id="evidence-title">可靠性结论都有可复核证据</h2>
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
          href={sourceHref("docs/release-evidence/real-model-representative-validation.md")}
          target="_blank"
          rel="noreferrer"
        >
          查看真实模型代表性验证
        </a>
      </section>

      <section
        id="boundary"
        className="showcase-section boundary-section"
        aria-labelledby="boundary-title"
      >
        <p className="section-kicker">HONEST BOUNDARY</p>
        <h2 id="boundary-title">当前是本地单节点发布候选</h2>
        <p>
          这是即时打开的静态项目专题，不连接可写后端；完整三业务演示在本地 WSL2 + Docker Compose
          运行。生产身份、托管数据库和公网写服务仍未建设。
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
