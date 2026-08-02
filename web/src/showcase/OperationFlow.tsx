const STEPS = [
  ["01", "异常被发现", "只读扫描比较权威事实与阈值，产生库存短缺、设备告警或任务阻塞信号。"],
  ["02", "请求准入", "操作员从结构化表单选择信号与动作；FastAPI 校验 JWT/RBAC、Pydantic 契约。"],
  ["03", "目标编码", "受信场景与对象进入 Agent Context；Kimi 输出严格 GoalEncoding，Harness 防止目标漂移。"],
  ["04", "规划与工具循环", "模型在预算内选择白名单只读工具，Observation 返回后决定继续取证或结束。"],
  ["05", "MCP 与 RAG 取证", "FastMCP 读取 PostgreSQL 事实、策略约束与 pgvector SOP，返回结构化证据和 citation。"],
  ["06", "分析与确定性校验", "模型综合证据形成建议；领域规则独立计算动作、参数和风险并拒绝不一致。"],
  ["07", "HITL 审批中断", "证据、规则、计划与参数哈希写入 approval binding，LangGraph checkpoint 后 interrupt。"],
  ["08", "批准后验证", "PostgreSQL 行锁决定审批胜者；恢复后绕过 Redis 重取事实，模型与代码双重验证。"],
  ["09", "幂等写入", "稳定幂等键、唯一约束与写后读确保重试、重放或重启只产生一张有效工单。"],
  ["10", "反馈与恢复", "Trace、Audit、citation 经 SSE 回到界面；服务重启从 checkpoint 与业务表恢复到可解释终态。"],
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
