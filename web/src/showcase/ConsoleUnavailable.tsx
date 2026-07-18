export function ConsoleUnavailable() {
  return <main className="console-unavailable"><h1>现场本地演示入口</h1><p>公开专题不提供公开可写服务。请先在本机启动 Docker Compose。</p><code>docker compose up --build</code><p>然后打开 http://localhost:5173/console。</p></main>;
}
