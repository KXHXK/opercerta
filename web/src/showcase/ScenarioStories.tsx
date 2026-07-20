import { SCENARIOS } from "./project-facts";

export function ScenarioStories() {
  return (
    <div className="scenario-story-grid">
      {SCENARIOS.map((scenario, index) => (
        <article
          className={`scenario-story scenario-${scenario.accent}`}
          key={scenario.key}
        >
          <span className="story-index">0{index + 1}</span>
          <h3>{scenario.label}</h3>
          <p>{scenario.trigger}</p>
          <dl>
            <div>
              <dt>MCP</dt>
              <dd>
                <code>{scenario.statusTool}</code>
              </dd>
            </div>
            <div>
              <dt>规则</dt>
              <dd>{scenario.policySummary}</dd>
            </div>
            <div>
              <dt>工单</dt>
              <dd>
                <code>{scenario.workOrderKind}</code>
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}
