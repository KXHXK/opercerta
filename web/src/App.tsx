function App() {
  return (
    <main className="console-shell">
      <header className="console-header">
        <div>
          <p className="eyebrow">本地合成数据演示</p>
          <h1>OperCerta｜智能运营处置 Agent</h1>
        </div>
        <p className="gate">发布门禁：CLOSED</p>
      </header>
      <section className="console-grid" aria-label="运营控制台">
        <article className="panel">操作控制区</article>
        <article className="panel">业务事实区</article>
        <article className="panel">审计时间线</article>
      </section>
      <footer className="boundary">
        本地演示 JWT，不是生产 IAM；审计事件为持久化快照回放。
      </footer>
    </main>
  );
}

export default App;
