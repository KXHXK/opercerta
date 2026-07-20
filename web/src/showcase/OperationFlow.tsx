const STEPS = [
  ["01", "请求与身份", "React 选择场景、角色和动作；FastAPI 校验 JWT/RBAC 与严格请求。"],
  ["02", "建立 Operation", "PostgreSQL 保存请求与第一条审计事实。"],
  ["03", "MCP 取证", "状态工具和 policy.list_constraints 返回类型化合成证据。"],
  ["04", "确定性评估", "领域代码决定风险、动作与参数；query 在这里直接完成。"],
  ["05", "受限模型解释", "create 路径的 Kimi 只返回 summary/rationale。"],
  ["06", "审批中断", "approval binding 与 checkpoint 持久化后 LangGraph interrupt。"],
  ["07", "批准后复核", "行锁决定审批胜者；恢复后绕过 Redis 重读 MCP 事实。"],
  ["08", "幂等写入与审计", "唯一键、写后读和 SSE 保证一张有效工单与可回放终态。"],
] as const;

export function OperationFlow() {
  return (
    <ol className="public-flow">
      {STEPS.map(([number, title, text]) => (
        <li key={number}>
          <span>{number}</span>
          <div>
            <h3>{title}</h3>
            <p>{text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
