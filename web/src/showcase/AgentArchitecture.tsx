const LOOP = [
  ["01", "感知", "React 表单与异常信号进入 FastAPI；JWT/RBAC、Pydantic 先完成身份与输入准入。"],
  ["02", "理解与计划", "Kimi K2.6 在版本化 Prompt 和类型化 Context 中编码目标，提出调查计划或工具调用。"],
  ["03", "行动", "ToolPolicy 只放行与场景、对象绑定的只读工具；FastMCP 执行事实与 SOP 检索。"],
  ["04", "观察与修正", "工具结果被校验为 Observation 回到模型；证据不足时继续调用，充分时形成分析。"],
  ["05", "审批与执行", "LangGraph 持久化 checkpoint 并 interrupt；批准后重取事实、验证并幂等写工单。"],
  ["06", "记忆与反馈", "PostgreSQL 保存状态、审计与 Trace，SSE 回放到界面；重启后从 checkpoint 继续。"],
] as const;

const HARNESS = [
  ["Prompt Registry", "Planner、Tool Loop、Analyst、Verifier、Reporter 分版本加载，并记录内容哈希。"],
  ["Context & Goal Encoder", "只把受信场景、对象、角色和历史 Observation 组装进类型化上下文。"],
  ["AgentHarness", "校验目标一致性、计划一致性及模型调用、工具调用、replan 预算。"],
  ["ToolPolicy", "按场景生成最小工具白名单，绑定对象与参数，拒绝越权、重复和超预算调用。"],
  ["Observation 校验", "ToolExecutor 对参数和结构化证据做校验，错误转为安全 Observation，不把异常堆栈交给模型。"],
  ["Trace Recorder", "记录目标、计划、工具、证据引用、模型结论、审批与终态，敏感字段先脱敏。"],
] as const;

const TECHNOLOGY_ROLES = [
  ["LangGraph", "LangGraph 负责状态编排与恢复，而不是普通业务节点：控制循环、条件路由、HITL interrupt 与 checkpoint。"],
  ["LangChain", "作为模型适配层连接 OpenAI-compatible Kimi，完成 Structured Output 与原生 Tool Calling。"],
  ["FastMCP / MCP", "MCP 定义模型工具协议；FastMCP 实现独立工具服务，把业务 API/数据库能力收敛成类型化工具。"],
  ["PostgreSQL + pgvector", "保存权威业务事实、审批绑定、工单、审计、checkpoint 与向量化 SOP/citation。"],
  ["Redis", "Redis 只缓存调查阶段的只读证据；审批后复核强制 bypass，避免旧缓存授权写入。"],
  ["OpenTelemetry + SSE", "前者观测 API/Graph/MCP 跨服务链路，后者向前端有序回放 Agent Trace 与审计事件。"],
] as const;

export function AgentArchitecture() {
  return (
    <>
      <div className="agent-cycle" aria-label="受控 Agent 循环架构">
        <div className="cycle-core">
          <strong>LANGGRAPH</strong>
          <span>state · route · interrupt · resume</span>
        </div>
        <ol>
          {LOOP.map(([number, title, text]) => (
            <li key={number}>
              <span>{number}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </li>
          ))}
        </ol>
      </div>

      <h3 className="subsection-title">Agent Harness：把概率模型约束成工程系统</h3>
      <div className="harness-grid">
        {HARNESS.map(([title, text]) => (
          <article key={title}>
            <h4>{title}</h4>
            <p>{text}</p>
          </article>
        ))}
      </div>

      <h3 className="subsection-title">每条技术在运行链路中的实际作用</h3>
      <div className="technology-role-grid">
        {TECHNOLOGY_ROLES.map(([title, text]) => (
          <article key={title}>
            <h4>{title}</h4>
            <p>{text}</p>
          </article>
        ))}
      </div>
      <p className="control-boundary">
        <strong>控制边界：</strong>Kimi 负责目标理解、计划/工具选择、证据综合、批准时验证建议和最终报告；
        RBAC、工具白名单、业务规则、审批绑定、最终写入与幂等性始终由确定性代码和数据库约束裁决。
      </p>
    </>
  );
}
