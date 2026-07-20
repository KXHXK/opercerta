import { EVIDENCE, LIMITATIONS, STACK, WORKFLOWS } from "./showcase-content";

export function ShowcasePage() {
  return (
    <main className="showcase-shell">
      <nav className="showcase-nav"><a href="/" className="showcase-logo">OPERCERTA</a><div><a href="#workflows">场景</a><a href="#architecture">架构</a><a href="#evidence">证据</a><a href="/console">控制台</a></div></nav>
      <section className="showcase-hero">
        <p className="eyebrow">OPERATIONS AGENT / EVIDENCE-DRIVEN ENGINEERING</p>
        <h1>OperCerta</h1>
        <p className="showcase-lead">让高风险运营动作可解释、可审批、可恢复。</p>
        <p>三类运营异常共享一套证据、审批、幂等写入与重启恢复内核。</p>
        <div className="showcase-actions"><a href="/console">进入三业务控制台</a><a href="https://github.com/KXHXK/opercerta" target="_blank" rel="noreferrer">GitHub 源码</a></div>
      </section>
      <section id="workflows" className="showcase-section"><p className="section-index">01 / WORKFLOWS</p><h2>业务闭环</h2><div className="workflow-grid">{WORKFLOWS.map(([index, title, path]) => <article key={title}><span>{index}</span><h3>{title}</h3><p>{path}</p></article>)}</div></section>
      <section id="architecture" className="showcase-section"><p className="section-index">02 / ARCHITECTURE</p><h2>系统架构</h2><div className="stack-grid">{STACK.map((item) => <span key={item}>{item}</span>)}</div></section>
      <section id="evidence" className="showcase-section">
        <p className="section-index">03 / RELIABILITY</p><h2>工程证据</h2>
        <div className="evidence-grid">{EVIDENCE.map(([title, text]) => <article key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
      </section>
      <section className="showcase-section">
        <p className="section-index">04 / LOCAL EVIDENCE</p><h2>真实流程截图</h2>
        <div className="showcase-proof-grid">
          <figure><img src="/evidence/console-approval-flow.png" alt="本地合成数据的绑定审批流程" /><figcaption>本地合成数据：等待审批、推荐数量与审批角色绑定。</figcaption></figure>
          <figure><img src="/evidence/console-audit-flow.png" alt="本地合成数据的持久化审计流程" /><figcaption>本地合成数据：审计序列回放至处置完成。</figcaption></figure>
        </div>
      </section>
      <section className="showcase-section boundary-section"><p className="section-index">05 / BOUNDARY</p><h2>尚未完成</h2><p className="gate">OperCerta release gate: CLOSED</p><ul>{LIMITATIONS.map((item) => <li key={item}>{item}</li>)}</ul><p>源码已公开；发布门禁关闭前，本页只陈述自动化验证过的能力。</p></section>
      <footer className="showcase-footer">OPERATIONS SHOULD BE EXPLAINABLE, REVERSIBLE AND AUDITABLE.</footer>
    </main>
  );
}
