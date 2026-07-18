import { EVIDENCE, LIMITATIONS, STACK } from "./showcase-content";

export function ShowcasePage() {
  return (
    <main className="showcase-shell">
      <nav className="showcase-nav"><a href="/" className="showcase-logo">OPERCERTA</a><div><a href="#architecture">架构</a><a href="#evidence">证据</a><a href="/console">控制台</a></div></nav>
      <section className="showcase-hero">
        <p className="eyebrow">OPERATIONS AGENT / EVIDENCE-DRIVEN ENGINEERING</p>
        <h1>OperCerta</h1>
        <p className="showcase-lead">让高风险运营动作可解释、可审批、可恢复。</p>
        <p>从库存不足识别、审批绑定到幂等补货工单与审计回放的完整业务闭环。</p>
        <div className="showcase-actions"><a href="#evidence">查看工程证据</a><a href="/console">现场演示入口</a></div>
      </section>
      <section className="showcase-section"><p className="section-index">01 / WORKFLOW</p><h2>业务闭环</h2><p className="workflow-line">库存不足 → 证据与计划 → 绑定审批 → 幂等补货工单 → 审计验证</p></section>
      <section id="architecture" className="showcase-section"><p className="section-index">02 / ARCHITECTURE</p><h2>系统架构</h2><div className="stack-grid">{STACK.map((item) => <span key={item}>{item}</span>)}</div></section>
      <section id="evidence" className="showcase-section">
        <p className="section-index">03 / RELIABILITY</p><h2>工程证据</h2>
        <div className="evidence-grid">{EVIDENCE.map(([title, text]) => <article key={title}><h3>{title}</h3><p>{text}</p></article>)}</div>
      </section>
      <section className="showcase-section boundary-section"><p className="section-index">04 / BOUNDARY</p><h2>尚未完成</h2><p className="gate">OperCerta release gate: CLOSED</p><ul>{LIMITATIONS.map((item) => <li key={item}>{item}</li>)}</ul><p>源码与完整测试证据可在受控审查或面试中提供。</p></section>
      <footer className="showcase-footer">OPERATIONS SHOULD BE EXPLAINABLE, REVERSIBLE AND AUDITABLE.</footer>
    </main>
  );
}
