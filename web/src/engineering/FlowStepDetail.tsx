import { useState } from "react";

import { sourceHref } from "../showcase/project-facts";
import type { EngineeringStep } from "./engineering-content";

export function FlowStepDetail({ steps }: { steps: readonly EngineeringStep[] }) {
  const [selectedId, setSelectedId] = useState(steps[0].id);
  const selected = steps.find((step) => step.id === selectedId) ?? steps[0];

  return (
    <section className="engineering-section" aria-labelledby="flow-detail-title">
      <p className="section-kicker">REQUEST CHAIN</p>
      <h2 id="flow-detail-title">完整请求链路</h2>
      <div className="engineering-step-layout">
        <ol className="engineering-step-list">
          {steps.map((step, index) => (
            <li key={step.id}>
              <button
                type="button"
                aria-pressed={step.id === selected.id}
                onClick={() => setSelectedId(step.id)}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                {step.title}
                <span className="sr-only">查看步骤</span>
              </button>
            </li>
          ))}
        </ol>
        <article className="engineering-step-detail" aria-live="polite">
          <p className="step-purpose">{selected.purpose}</p>
          <dl>
            <div>
              <dt>源码</dt>
              <dd>
                {selected.source.map((path) => (
                  <a key={path} href={sourceHref(path)} target="_blank" rel="noreferrer">
                    {path}
                  </a>
                ))}
              </dd>
            </div>
            <div>
              <dt>输入 / 输出</dt>
              <dd>{selected.inputOutput}</dd>
            </div>
            <div>
              <dt>数据库效果</dt>
              <dd>{selected.databaseEffect}</dd>
            </div>
            <div>
              <dt>失败行为</dt>
              <dd>{selected.failureBehavior}</dd>
            </div>
            <div>
              <dt>自动化证据</dt>
              <dd>
                <a href={sourceHref(selected.evidence)} target="_blank" rel="noreferrer">
                  {selected.evidence}
                </a>
              </dd>
            </div>
            <div>
              <dt>面试追问</dt>
              <dd>{selected.interviewPrompt}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>
  );
}
