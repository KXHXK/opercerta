const evidence = ["非法输入", "状态恢复", "审批竞态", "幂等写入", "重启恢复"];

export function ShowcasePage() {
  return (
    <main className="showcase-shell">
      <section className="showcase-hero">
        <p className="eyebrow">OPERATIONS AGENT / EVIDENCE-DRIVEN ENGINEERING</p>
        <h1>OperCerta</h1>
        <p>从库存不足识别到审批绑定、幂等补货工单与审计回放的可恢复运营 Agent。</p>
        <a href="#evidence">查看工程证据</a>
        <a href="/console">现场演示入口</a>
      </section>
      <section id="evidence" className="showcase-section">
        <h2>可靠性内核</h2>
        <ul>{evidence.map((item) => <li key={item}>{item}：已具备本地与 CI 自动化证据。</li>)}</ul>
      </section>
      <section className="showcase-section">
        <h2>当前边界</h2>
        <p>OperCerta release gate: CLOSED</p>
        <p>Private GitHub；Mock 模型；未完成设备场景、生产 IAM/SSO、自动部署和完整浏览器 E2E；不提供公开可写服务。</p>
      </section>
    </main>
  );
}
