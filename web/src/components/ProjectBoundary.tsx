export function ProjectBoundary() {
  return (
    <footer className="boundary">
      <strong>发布门禁保持 CLOSED</strong>
      <p>这是本地合成数据演示：不包含生产 IAM、SSO、实时订阅或公开部署。</p>
      <p>审计事件为 PostgreSQL 持久化快照回放；演示 JWT 仅保存在浏览器内存。</p>
    </footer>
  );
}
