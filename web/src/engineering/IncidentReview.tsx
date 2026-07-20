import { INCIDENTS } from "./engineering-content";

export function IncidentReview() {
  return (
    <section className="engineering-section" aria-labelledby="incident-review-title">
      <p className="section-kicker">INCIDENT REVIEW</p>
      <h2 id="incident-review-title">真实故障复盘</h2>
      <p className="incident-intro">
        每个案例都保留观察、根因、修复、验证、限制和面试表达；不包含秘密值、原始模型输出或 traceback。
      </p>
      <div className="incident-list">
        {INCIDENTS.map((incident, index) => (
          <details key={incident.id}>
            <summary>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {incident.title}
            </summary>
            <dl>
              <div>
                <dt>观察</dt>
                <dd>{incident.observation}</dd>
              </div>
              <div>
                <dt>根因</dt>
                <dd>{incident.rootCause}</dd>
              </div>
              <div>
                <dt>修复</dt>
                <dd>{incident.fix}</dd>
              </div>
              <div>
                <dt>验证</dt>
                <dd>{incident.verification}</dd>
              </div>
              <div>
                <dt>限制</dt>
                <dd>{incident.limitation}</dd>
              </div>
              <div>
                <dt>面试表达</dt>
                <dd>{incident.interviewLine}</dd>
              </div>
            </dl>
          </details>
        ))}
      </div>
    </section>
  );
}
