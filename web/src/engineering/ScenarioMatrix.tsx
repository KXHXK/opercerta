import { MCP_TOOLS, SCENARIOS } from "../showcase/project-facts";

const STATUS_TOOLS = new Set(SCENARIOS.map((scenario) => scenario.statusTool));
const SHARED_TOOLS = MCP_TOOLS.filter((tool) => !STATUS_TOOLS.has(tool));

export function ScenarioMatrix() {
  return (
    <section className="engineering-section" aria-labelledby="scenario-matrix-title">
      <p className="section-kicker">TYPED VARIATION</p>
      <h2 id="scenario-matrix-title">三业务差异矩阵</h2>
      <div className="table-scroll" role="region" aria-label="三业务差异表" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th>业务</th>
              <th>触发事实</th>
              <th>状态工具</th>
              <th>规则约束</th>
              <th>工单类型</th>
            </tr>
          </thead>
          <tbody>
            {SCENARIOS.map((scenario) => (
              <tr key={scenario.key}>
                <th>{scenario.label}</th>
                <td>{scenario.trigger}</td>
                <td>
                  <code>{scenario.statusTool}</code>
                </td>
                <td>{scenario.policySummary}</td>
                <td>
                  <code>{scenario.workOrderKind}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="tool-allowlist" aria-label="六个 MCP 工具白名单中的共享工具">
        {SHARED_TOOLS.map((tool) => (
          <code key={tool}>{tool}</code>
        ))}
      </div>
    </section>
  );
}
