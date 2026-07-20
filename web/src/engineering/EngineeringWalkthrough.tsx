import { ENGINEERING_STEPS } from "./engineering-content";
import { FlowStepDetail } from "./FlowStepDetail";
import { ScenarioMatrix } from "./ScenarioMatrix";
import { TechnologyMap } from "./TechnologyMap";

export function EngineeringWalkthrough() {
  return (
    <main className="engineering-shell">
      <header className="engineering-hero">
        <a href="/">← 返回项目专题</a>
        <p className="eyebrow">LOCAL ENGINEERING DOSSIER</p>
        <h1>OperCerta 工程拆解</h1>
        <p>
          沿一次真实 operation 的边界、状态与副作用，定位每项技术在源码、数据库和失败路径中的作用。
          本页只在 localhost 开发模式渲染。
        </p>
      </header>
      <FlowStepDetail steps={ENGINEERING_STEPS} />
      <ScenarioMatrix />
      <TechnologyMap />
    </main>
  );
}
