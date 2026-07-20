# OperCerta Zero-Cost Showcase and Engineering Walkthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This project uses inline execution; do not dispatch subagents.

**Goal:** Build a polished zero-cost public OperCerta showcase for recruiters and a localhost-only engineering walkthrough for project mastery, then publish the verified static artifacts without exposing a writable backend.

**Architecture:** The React/Vite app receives one typed project-facts manifest. `/` renders a production-safe recruiter narrative without network calls; `/engineering` renders the detailed walkthrough only in local development on loopback hosts. The existing `/console` remains the real local backend client. Netlify receives only the production static build, while GitHub holds the evidence and source links.

**Tech Stack:** React 19, TypeScript 7, Vite 8, Vitest/Testing Library, CSS, localStorage, Python repository-contract tests, GitHub Actions, Netlify CLI.

## Global Constraints

- Implement only OperCerta; do not create ForenTrail, SiteVerum, or Federune code.
- Use only public or repository synthetic data; never reuse former-company material.
- Public UI must not contain `AI 生成`, `由 AI 创建`, `Codex 生成`, `Built with Codex`, tutorial/beginner language, fake online actions, or an empty video player.
- `AI Agent` remains valid as the project/job-domain name.
- Public `/` performs no API fetch and exposes no writable backend, JWT, MCP, PostgreSQL, Redis, or metrics route.
- `/engineering` is available only when `development === true` and hostname is `localhost` or `127.0.0.1`.
- Do not use `position: fixed`, sticky content modules, scroll snap, horizontal drag carousels, autoplay media, infinite animations, parallax, or a new animation dependency.
- Motion uses short opacity/transform transitions and honors `prefers-reduced-motion`.
- All displayed numbers must come from committed evidence; record new actual counts after verification rather than predicting them.
- Do not edit or restage unrelated changes. The `.gitignore` commit `fe28490` is baseline and is not part of this feature.
- Production release gate remains `CLOSED`; no Release Tag is created in this plan.

---

## File Structure

### Shared runtime and facts

- Create `web/src/runtime/page-runtime.ts`: pure route/host decision function.
- Create `web/src/runtime/page-runtime.test.ts`: local/public route contract.
- Create `web/src/showcase/project-facts.ts`: typed, evidence-backed business and release facts.
- Create `web/src/showcase/project-facts.test.ts`: tool/scenario/count/boundary contract.

### Public showcase

- Replace `web/src/showcase/showcase-content.ts`: re-export or remove stale arrays after consumers move to `project-facts.ts`.
- Refactor `web/src/showcase/ShowcasePage.tsx`: recruiter-first page composition.
- Expand `web/src/showcase/ShowcasePage.test.tsx`: truthful public narrative and no-fetch contract.
- Create `web/src/showcase/SectionNav.tsx`: URL-preserving in-page navigation.
- Create `web/src/showcase/ScenarioStories.tsx`: three colored business cards.
- Create `web/src/showcase/OperationFlow.tsx`: eight-step public flow.
- Create `web/src/showcase/ReliabilityEvidence.tsx`: reliability/evidence/case-study summary.

### Local engineering walkthrough

- Create `web/src/engineering/engineering-content.ts`: ten flow steps, technology map, incidents, interview prompts.
- Create `web/src/engineering/EngineeringWalkthrough.tsx`: local engineering page composition.
- Create `web/src/engineering/EngineeringWalkthrough.test.tsx`: deep-content and source-link contract.
- Create `web/src/engineering/FlowStepDetail.tsx`: selectable request-chain details.
- Create `web/src/engineering/ScenarioMatrix.tsx`: typed business differences.
- Create `web/src/engineering/TechnologyMap.tsx`: technology-to-effect table.
- Create `web/src/engineering/IncidentReview.tsx`: observed root-cause stories.
- Create `web/src/engineering/MasteryChecklist.tsx`: local-only progress persistence.
- Create `web/src/engineering/MasteryChecklist.test.tsx`: localStorage and reset behavior.

### Routing, style, tests, documentation

- Modify `web/src/App.tsx`: route with `resolvePageKind`.
- Modify `web/src/App.test.tsx`: public/local/production route behavior.
- Rewrite showcase/engineering portions of `web/src/styles.css`: editorial visual system and responsive behavior.
- Modify `tests/unit/runtime/test_static_hosting_assets.py`: public-language and CSS safety contracts.
- Modify `README.md`, `DOCUMENT_INDEX.md`, `IMPLEMENTATION_HANDOFF.md`, `docs/development-log/current-state.md`, `docs/development-log/daily/2026-07-20.md`, `docs/development-log/interview-casebook.md`, and release evidence after observed execution.
- Modify `D:\CODEX\resume\portfolio\app\page.tsx` and `D:\CODEX\resume\portfolio\tests\rendered-html.test.mjs` only for the verified OperCerta summary; preserve all unrelated dirty-worktree content and do not commit that repository wholesale.

---

### Task 1: Typed Facts and Local-Only Route Contract

**Files:**
- Create: `web/src/runtime/page-runtime.ts`
- Create: `web/src/runtime/page-runtime.test.ts`
- Create: `web/src/showcase/project-facts.ts`
- Create: `web/src/showcase/project-facts.test.ts`

**Interfaces:**
- Produces: `PageKind`, `resolvePageKind(pathname, hostname, development)`.
- Produces: `PROJECT_FACTS`, `SCENARIOS`, `MCP_TOOLS`, `PUBLIC_LIMITATIONS`, `sourceHref(path)`.
- Consumed by: Tasks 2 and 4.

- [ ] **Step 1: Write failing route tests**

```ts
import { describe, expect, it } from "vitest";

import { resolvePageKind } from "./page-runtime";

describe("resolvePageKind", () => {
  it("keeps the public showcase at root", () => {
    expect(resolvePageKind("/", "opercerta-kxh.netlify.app", false)).toBe("showcase");
  });

  it.each(["localhost", "127.0.0.1"])(
    "allows the engineering walkthrough on local development host %s",
    (hostname) => {
      expect(resolvePageKind("/engineering", hostname, true)).toBe("engineering");
    }
  );

  it("does not expose the engineering walkthrough in production", () => {
    expect(resolvePageKind("/engineering", "opercerta-kxh.netlify.app", false)).toBe(
      "not-found"
    );
  });

  it("preserves the real local console route", () => {
    expect(resolvePageKind("/console", "localhost", true)).toBe("console");
  });
});
```

- [ ] **Step 2: Run the route tests and verify RED**

Run:

```powershell
Set-Location web
npm run test:run -- src/runtime/page-runtime.test.ts
```

Expected: FAIL because `page-runtime.ts` does not exist.

- [ ] **Step 3: Implement the pure route resolver**

```ts
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1"]);

export type PageKind = "showcase" | "engineering" | "console" | "not-found";

export function resolvePageKind(
  pathname: string,
  hostname: string,
  development = import.meta.env.DEV
): PageKind {
  if (pathname === "/") return "showcase";
  if (pathname === "/console") return "console";
  if (pathname === "/engineering" && development && LOOPBACK_HOSTS.has(hostname)) {
    return "engineering";
  }
  return "not-found";
}
```

- [ ] **Step 4: Write the failing facts contract**

```ts
import { expect, it } from "vitest";

import { MCP_TOOLS, PROJECT_FACTS, SCENARIOS } from "./project-facts";

it("keeps evidence-backed release facts and three typed scenarios", () => {
  expect(PROJECT_FACTS).toMatchObject({
    businessLoops: 3,
    frozenEvaluations: 42,
    realModelOperations: 6,
    realModelPaths: 3,
    backendTests: 429,
    releaseGate: "CLOSED",
  });
  expect(SCENARIOS.map((scenario) => scenario.workOrderKind)).toEqual([
    "replenishment",
    "repair",
    "task_recovery",
  ]);
  expect(MCP_TOOLS).toEqual([
    "inventory.get_snapshot",
    "equipment.get_status",
    "task.get_status",
    "policy.list_constraints",
    "work_order.create",
    "work_order.get",
  ]);
});
```

- [ ] **Step 5: Run the facts test and verify RED**

Run:

```powershell
npm run test:run -- src/showcase/project-facts.test.ts
```

Expected: FAIL because `project-facts.ts` does not exist.

- [ ] **Step 6: Implement the typed facts manifest**

```ts
export type ScenarioFact = {
  key: "inventory" | "equipment" | "task";
  label: string;
  trigger: string;
  statusTool: string;
  policySummary: string;
  workOrderKind: "replenishment" | "repair" | "task_recovery";
  accent: "teal" | "amber" | "violet";
};

export const PROJECT_FACTS = {
  businessLoops: 3,
  frozenEvaluations: 42,
  realModelOperations: 6,
  realModelPaths: 3,
  backendTests: 429,
  realModelProvider: "Moonshot AI",
  realModelName: "kimi-k2.6",
  releaseGate: "CLOSED",
} as const;

export const MCP_TOOLS = [
  "inventory.get_snapshot",
  "equipment.get_status",
  "task.get_status",
  "policy.list_constraints",
  "work_order.create",
  "work_order.get",
] as const;

export const SCENARIOS: readonly ScenarioFact[] = [
  {
    key: "inventory",
    label: "库存不足 → 补货",
    trigger: "可用库存低于补货点",
    statusTool: "inventory.get_snapshot",
    policySummary: "目标差额受最小/最大订货量约束",
    workOrderKind: "replenishment",
    accent: "teal",
  },
  {
    key: "equipment",
    label: "设备告警 → 维修",
    trigger: "心跳过期、设备状态或允许告警触发",
    statusTool: "equipment.get_status",
    policySummary: "维护规则映射优先级",
    workOrderKind: "repair",
    accent: "amber",
  },
  {
    key: "task",
    label: "作业阻塞 → 恢复",
    trigger: "blocked/overdue 与重试次数触发",
    statusTool: "task.get_status",
    policySummary: "恢复策略约束动作",
    workOrderKind: "task_recovery",
    accent: "violet",
  },
] as const;

export const PUBLIC_LIMITATIONS = [
  "生产 IAM/SSO",
  "公开可写 HTTPS 后端",
  "限流、防滥用与高可用",
  "Release Tag",
] as const;

export function sourceHref(path: string): string {
  return `https://github.com/KXHXK/opercerta/blob/main/${path}`;
}
```

- [ ] **Step 7: Verify GREEN and commit**

Run:

```powershell
npm run test:run -- src/runtime/page-runtime.test.ts src/showcase/project-facts.test.ts
Set-Location ..
git add web/src/runtime/page-runtime.ts web/src/runtime/page-runtime.test.ts web/src/showcase/project-facts.ts web/src/showcase/project-facts.test.ts
git commit -m "feat: define showcase facts and local route boundary"
```

Expected: both focused test files PASS; commit contains only four files.

---

### Task 2: Recruiter-First Public Narrative

**Files:**
- Create: `web/src/showcase/SectionNav.tsx`
- Create: `web/src/showcase/ScenarioStories.tsx`
- Create: `web/src/showcase/OperationFlow.tsx`
- Create: `web/src/showcase/ReliabilityEvidence.tsx`
- Modify: `web/src/showcase/ShowcasePage.tsx`
- Modify: `web/src/showcase/ShowcasePage.test.tsx`
- Modify: `web/src/showcase/showcase-content.ts`

**Interfaces:**
- Consumes: `PROJECT_FACTS`, `SCENARIOS`, `PUBLIC_LIMITATIONS`, `sourceHref`.
- Produces: semantic sections with IDs `business`, `flow`, `architecture`, `evidence`, `boundary`.
- Produces: `SectionNav` buttons that call `scrollIntoView` without changing location hash.

- [ ] **Step 1: Replace public showcase tests with the new failing contract**

```tsx
it("gives recruiters the verified three-business story without network calls", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<ShowcasePage />);

  expect(screen.getByRole("heading", { name: /可审批、可恢复的运营工单/ })).toBeInTheDocument();
  expect(screen.getByText("3 条业务闭环")).toBeInTheDocument();
  expect(screen.getByText("42 条固定评测")).toBeInTheDocument();
  expect(screen.getByText("6 次真实模型代表操作")).toBeInTheDocument();
  for (const name of ["库存不足 → 补货", "设备告警 → 维修", "作业阻塞 → 恢复"]) {
    expect(screen.getByRole("heading", { name })).toBeInTheDocument();
  }
  expect(fetchMock).not.toHaveBeenCalled();
});

it("does not present a generated template, tutorial, or public write action", () => {
  render(<ShowcasePage />);
  const text = document.body.textContent ?? "";
  for (const forbidden of [
    "AI 生成",
    "Codex 生成",
    "Built with Codex",
    "Mock 模型",
    "入门",
    "学习中",
    "在线运行",
    "创建工单",
  ]) {
    expect(text).not.toContain(forbidden);
  }
  expect(screen.getByText(/静态项目专题/)).toBeInTheDocument();
  expect(screen.getByText(/生产门禁.*CLOSED/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
Set-Location web
npm run test:run -- src/showcase/ShowcasePage.test.tsx
```

Expected: FAIL because the existing hero, stale limitations, and section structure do not match.

- [ ] **Step 3: Implement URL-preserving section navigation**

```tsx
const ITEMS = [
  ["business", "业务"],
  ["flow", "流程"],
  ["architecture", "架构"],
  ["evidence", "证据"],
] as const;

export function SectionNav() {
  function moveTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <nav className="section-nav" aria-label="项目专题目录">
      <a className="showcase-logo" href="/">OPERCERTA</a>
      <div>{ITEMS.map(([id, label]) => <button key={id} onClick={() => moveTo(id)}>{label}</button>)}</div>
    </nav>
  );
}
```

- [ ] **Step 4: Implement the three scenario stories**

```tsx
import { SCENARIOS } from "./project-facts";

export function ScenarioStories() {
  return (
    <div className="scenario-story-grid">
      {SCENARIOS.map((scenario, index) => (
        <article className={`scenario-story scenario-${scenario.accent}`} key={scenario.key}>
          <span className="story-index">0{index + 1}</span>
          <h3>{scenario.label}</h3>
          <p>{scenario.trigger}</p>
          <dl>
            <div><dt>MCP</dt><dd><code>{scenario.statusTool}</code></dd></div>
            <div><dt>规则</dt><dd>{scenario.policySummary}</dd></div>
            <div><dt>工单</dt><dd><code>{scenario.workOrderKind}</code></dd></div>
          </dl>
        </article>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Implement the eight-step public flow**

```tsx
const STEPS = [
  ["01", "请求与身份", "React 选择场景、角色和动作；FastAPI 校验 JWT/RBAC 与严格请求。"],
  ["02", "创建 Operation", "PostgreSQL 保存请求与第一条审计事实。"],
  ["03", "MCP 取证", "状态工具和 policy.list_constraints 返回类型化合成证据。"],
  ["04", "确定性评估", "领域代码决定风险、动作与参数；query 在这里直接完成。"],
  ["05", "受限模型解释", "create 路径的 Kimi 只返回 summary/rationale。"],
  ["06", "审批中断", "approval binding 与 checkpoint 持久化后 LangGraph interrupt。"],
  ["07", "批准后复核", "行锁决定审批胜者；恢复后绕过 Redis 重读 MCP 事实。"],
  ["08", "幂等写入与审计", "唯一键、写后读和 SSE 保证一张有效工单与可回放终态。"],
] as const;

export function OperationFlow() {
  return <ol className="public-flow">{STEPS.map(([number, title, text]) => (
    <li key={number}><span>{number}</span><div><h3>{title}</h3><p>{text}</p></div></li>
  ))}</ol>;
}
```

- [ ] **Step 6: Implement reliability evidence and compose the page**

Use these exact evidence cards in `ReliabilityEvidence.tsx`:

```tsx
const RELIABILITY = [
  ["审批绑定", "证据 ID、规则版本、事实哈希、计划哈希和类型化参数共同绑定批准内容。"],
  ["原子竞态", "PostgreSQL 行锁让并发审批只有一个胜者，失败者得到稳定冲突。"],
  ["幂等写入", "operation 派生幂等键与唯一约束，使 LangGraph 重放不产生第二张工单。"],
  ["重启恢复", "业务表定位非终态 operation，checkpoint 恢复执行位置，事实不一致时安全失败。"],
] as const;
```

Compose `ShowcasePage.tsx` in this order:

```tsx
<main className="showcase-shell">
  <SectionNav />
  <section className="showcase-hero" aria-labelledby="showcase-title">
    <p className="eyebrow">OPERATIONS CONTROL AGENT · LOCAL RELEASE CANDIDATE</p>
    <h1 id="showcase-title">把建议、审批与副作用放进一条可恢复的证据链</h1>
    <p className="hero-summary">OperCerta 用三条合成业务闭环展示受控 Agent 后端：模型负责解释，确定性代码决定动作，PostgreSQL 约束批准与写入。</p>
    <dl className="fact-strip">
      <div><dt>业务闭环</dt><dd>{PROJECT_FACTS.businessLoops}</dd></div>
      <div><dt>固定评测</dt><dd>{PROJECT_FACTS.frozenEvaluations}</dd></div>
      <div><dt>真实模型路径</dt><dd>{PROJECT_FACTS.realModelPaths}</dd></div>
      <div><dt>产品门禁</dt><dd>{PROJECT_FACTS.gate}</dd></div>
    </dl>
  </section>
  <section id="business" className="showcase-section" aria-labelledby="business-title">
    <p className="section-kicker">THREE CONTROLLED LOOPS</p>
    <h2 id="business-title">三种业务，共享一套可靠性内核</h2>
    <ScenarioStories />
  </section>
  <section id="flow" className="showcase-section" aria-labelledby="flow-title">
    <p className="section-kicker">90 SECOND TRACE</p>
    <h2 id="flow-title">一次写路径如何变成可审计终态</h2>
    <OperationFlow />
  </section>
  <section id="architecture" className="showcase-section" aria-labelledby="architecture-title">
    <p className="section-kicker">SYSTEM BOUNDARIES</p>
    <h2 id="architecture-title">模型不拥有业务副作用</h2>
    <p>React → FastAPI → OperationRunner → LangGraph → MCP/FastMCP、Kimi 与 PostgreSQL；FastAPI 再以 SSE 回放有序审计事件。</p>
    <ul className="architecture-boundaries">
      <li>Kimi K2.6 只返回 <code>summary</code> 与 <code>rationale</code>。</li>
      <li>规则、动作、审批参数和幂等键由类型化领域代码决定。</li>
      <li>Redis 只缓存初次只读证据；批准后直接重读 MCP 事实。</li>
    </ul>
  </section>
  <section id="evidence" className="showcase-section" aria-labelledby="evidence-title">
    <p className="section-kicker">VERIFIED BEHAVIOR</p>
    <h2 id="evidence-title">可靠性结论都有可复核证据</h2>
    <ReliabilityEvidence />
    <div className="evidence-gallery">
      <figure><img src="/evidence/console-approval-flow.png" alt="本地控制台等待审批状态" /><figcaption>本地合成数据运行证据：等待审批</figcaption></figure>
      <figure><img src="/evidence/console-audit-flow.png" alt="本地控制台审计事件回放" /><figcaption>本地合成数据运行证据：审计回放</figcaption></figure>
    </div>
    <a href={sourceHref("docs/release-evidence/real-model-representative-validation.md")}>查看真实模型代表性验证</a>
  </section>
  <section id="boundary" className="showcase-section boundary-section" aria-labelledby="boundary-title">
    <p className="section-kicker">HONEST BOUNDARY</p>
    <h2 id="boundary-title">当前是本地单节点发布候选</h2>
    <p>公开站点只展示静态、已验证事实，不连接可写后端；完整三业务演示在本地 WSL2 + Docker Compose 运行。生产身份、托管数据库和公网写服务仍未建设，产品门禁保持 CLOSED。</p>
    <a href="https://github.com/KXHXK/opercerta">查看公开源码与测试</a>
  </section>
  <footer className="showcase-footer">EXPLAINABLE · REVERSIBLE · AUDITABLE</footer>
</main>
```

The hero renders values from `PROJECT_FACTS`; every repository evidence link uses an explicit call such as `sourceHref("docs/release-evidence/approval-atomicity.md")`. The two existing images remain labelled “本地合成数据运行证据”. Remove stale `LIMITATIONS`/`STACK` exports once no consumer imports them.

- [ ] **Step 7: Verify GREEN and commit**

Run:

```powershell
npm run test:run -- src/showcase/ShowcasePage.test.tsx src/showcase/project-facts.test.ts
Set-Location ..
git add web/src/showcase
git commit -m "feat: tell the verified three-business showcase story"
```

Expected: focused tests PASS; public component test observes zero fetch calls.

---

### Task 3: Human-Crafted Visual System and Motion Safety

**Files:**
- Modify: `web/src/styles.css`
- Modify: `tests/unit/runtime/test_static_hosting_assets.py`
- Test: `web/src/showcase/ShowcasePage.test.tsx`

**Interfaces:**
- Consumes: semantic class names from Task 2.
- Produces: responsive editorial tokens, scenario accents, focus states, reduced-motion behavior.

- [ ] **Step 1: Write failing CSS safety tests**

```python
def test_showcase_visual_contract_avoids_scroll_traps_and_heavy_generated_treatments() -> None:
    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")

    for forbidden in (
        "position: fixed",
        "position: sticky",
        "scroll-snap-type",
        "animation-iteration-count: infinite",
    ):
        assert forbidden not in css
    assert "prefers-reduced-motion" in css
    assert "--scenario-inventory" in css
    assert "--scenario-equipment" in css
    assert "--scenario-task" in css
```

- [ ] **Step 2: Run the CSS contract and verify RED**

Run:

```powershell
uv run python -m pytest tests/unit/runtime/test_static_hosting_assets.py::test_showcase_visual_contract_avoids_scroll_traps_and_heavy_generated_treatments -q
```

Expected: FAIL because the new scenario tokens and reduced-motion contract do not yet exist.

- [ ] **Step 3: Replace the public visual tokens and layout rules**

Start `web/src/styles.css` with these shared tokens and preserve console component rules under their existing selectors:

```css
:root {
  --paper: #f5f3ed;
  --surface: #fffdf8;
  --ink: #17201d;
  --muted: #66716c;
  --line: #d9ddd7;
  --accent: #236b55;
  --scenario-inventory: #197768;
  --scenario-equipment: #a86620;
  --scenario-task: #6656a8;
  --risk: #995b48;
  --content-width: 1180px;
  color: var(--ink);
  background: var(--paper);
  font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
}

html { scroll-behavior: smooth; }
body { margin: 0; min-width: 320px; background: var(--paper); }
.showcase-shell { min-height: 100vh; overflow-x: clip; }
.section-nav,
.showcase-hero,
.showcase-section,
.showcase-footer { width: min(calc(100% - 40px), var(--content-width)); margin-inline: auto; }
.section-nav { display: flex; justify-content: space-between; align-items: center; padding: 22px 0; border-bottom: 1px solid var(--line); }
.section-nav div { display: flex; flex-wrap: wrap; gap: 6px; }
.section-nav button { margin: 0; min-height: 36px; border: 0; background: transparent; color: var(--muted); }
.showcase-hero { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr); gap: clamp(32px, 7vw, 88px); padding-block: clamp(64px, 9vw, 108px); }
.showcase-hero h1 { max-width: 17ch; font-size: clamp(2.25rem, 4.5vw, 3rem); line-height: 1.08; letter-spacing: -.045em; }
.showcase-section { border-top: 1px solid var(--line); padding-block: clamp(58px, 8vw, 92px); }
.scenario-story-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.scenario-story { background: var(--surface); border: 1px solid var(--line); padding: 24px; transition: transform 180ms ease, border-color 180ms ease; }
.scenario-story:hover { transform: translateY(-3px); }
.scenario-teal { border-top: 4px solid var(--scenario-inventory); }
.scenario-amber { border-top: 4px solid var(--scenario-equipment); }
.scenario-violet { border-top: 4px solid var(--scenario-task); }
.public-flow { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; list-style: none; padding: 0; background: var(--line); }
.public-flow li { display: grid; grid-template-columns: 42px 1fr; gap: 16px; background: var(--surface); padding: 22px; }
.showcase-proof-grid img { width: 100%; height: auto; max-height: 42rem; object-fit: contain; background: #e9ece8; }

@media (max-width: 760px) {
  .section-nav, .showcase-hero, .showcase-section, .showcase-footer { width: min(calc(100% - 28px), var(--content-width)); }
  .section-nav { align-items: flex-start; gap: 14px; flex-direction: column; }
  .showcase-hero, .scenario-story-grid, .public-flow, .showcase-proof-grid { grid-template-columns: 1fr; }
  .showcase-hero h1 { font-size: clamp(2rem, 10vw, 2.65rem); }
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition: none !important; }
}
```

Use only normal document flow. Do not add a fixed/sticky sidebar, carousel, parallax, observer-driven hidden content, or animation dependency.

- [ ] **Step 4: Verify CSS contract and frontend tests**

Run:

```powershell
uv run python -m pytest tests/unit/runtime/test_static_hosting_assets.py -q
Set-Location web
npm run test:run -- src/showcase/ShowcasePage.test.tsx
npm run build
```

Expected: Python asset tests PASS, showcase tests PASS, TypeScript/Vite build exits 0.

- [ ] **Step 5: Perform desktop/mobile visual check before commit**

Run local Vite and inspect `/` at widths 1440, 768, and 390. Verify:

```text
no horizontal overflow
no fixed or immovable overlay
headline stays below the specified visual scale
scenario colors remain distinguishable
keyboard focus is visible
reduced-motion mode keeps all content visible
console has no warning/error
```

Record screenshots only after these observations are true.

- [ ] **Step 6: Commit**

```powershell
Set-Location ..
git add web/src/styles.css tests/unit/runtime/test_static_hosting_assets.py
git commit -m "feat: add editorial showcase visual system"
```

Expected: commit contains CSS and its safety contract only.

---

### Task 4: Local Engineering Walkthrough and Exact Technology Mapping

**Files:**
- Create: `web/src/engineering/engineering-content.ts`
- Create: `web/src/engineering/EngineeringWalkthrough.tsx`
- Create: `web/src/engineering/EngineeringWalkthrough.test.tsx`
- Create: `web/src/engineering/FlowStepDetail.tsx`
- Create: `web/src/engineering/ScenarioMatrix.tsx`
- Create: `web/src/engineering/TechnologyMap.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: `resolvePageKind`, `SCENARIOS`, `MCP_TOOLS`, `sourceHref`.
- Produces: `ENGINEERING_STEPS: readonly EngineeringStep[]`, `TECHNOLOGIES`.
- Produces: local-only `/engineering` route and production-safe `not-found` result.

- [ ] **Step 1: Write failing route rendering tests**

```tsx
it("renders the engineering walkthrough only on local development", () => {
  window.history.pushState({}, "", "/engineering");
  render(<App development hostname="localhost" />);
  expect(screen.getByRole("heading", { name: "OperCerta 工程拆解" })).toBeInTheDocument();
});

it("does not expose the engineering walkthrough on the public host", () => {
  window.history.pushState({}, "", "/engineering");
  render(<App development={false} hostname="opercerta-kxh.netlify.app" />);
  expect(screen.getByRole("heading", { name: "页面不存在" })).toBeInTheDocument();
  expect(screen.queryByText("掌握检查")).not.toBeInTheDocument();
});
```

Refactor `App` to accept optional testable props:

```ts
type AppProps = {
  development?: boolean;
  hostname?: string;
};
```

- [ ] **Step 2: Run route rendering tests and verify RED**

Run:

```powershell
Set-Location web
npm run test:run -- src/App.test.tsx
```

Expected: FAIL because `App` does not accept the props and the engineering component does not exist.

- [ ] **Step 3: Define the ten-step engineering content contract**

```ts
export type EngineeringStep = {
  id: string;
  title: string;
  purpose: string;
  source: readonly string[];
  inputOutput: string;
  databaseEffect: string;
  failureBehavior: string;
  evidence: string;
  interviewPrompt: string;
};

export const ENGINEERING_STEPS: readonly EngineeringStep[] = [
  {
    id: "react-request",
    title: "React 选择场景、角色和动作",
    purpose: "把用户意图约束为三种对象和 query/create_work_order 两种动作。",
    source: ["web/src/components/OperationControls.tsx", "web/src/scenarios.ts"],
    inputOutput: "ScenarioDefinition + OperationAction → POST /api/v1/operations",
    databaseEffect: "无；浏览器不直接接触数据库。",
    failureBehavior: "身份或 API 不可用时显示固定安全提示，不伪造结果。",
    evidence: "web/src/components/OperationControls.test.tsx",
    interviewPrompt: "为什么前端不能提交 approver identity？",
  },
  {
    id: "api-boundary",
    title: "FastAPI JWT/RBAC 与严格输入",
    purpose: "在 HTTP 边界拒绝非法对象、动作和伪造身份。",
    source: ["src/opercerta/api/app.py", "src/opercerta/api/auth.py"],
    inputOutput: "OperationRequest + JWT → OperationAccepted 或固定 ErrorResponse",
    databaseEffect: "非法输入不创建 operation。",
    failureBehavior: "422/401/403 使用安全 envelope，不返回 traceback。",
    evidence: "tests/integration/api/test_operations_api.py",
    interviewPrompt: "Pydantic 校验与业务规则校验为什么分层？",
  },
  {
    id: "operation-create",
    title: "PostgreSQL 创建 Operation 与审计",
    purpose: "在执行图前建立可查询、可恢复的业务事实。",
    source: ["src/opercerta/application/operation_runner.py", "src/opercerta/infrastructure/db/operation_repository.py"],
    inputOutput: "Validated request → operation UUID + operation_created event",
    databaseEffect: "插入 operation 与有序审计记录。",
    failureBehavior: "事务失败不返回虚假 accepted。",
    evidence: "tests/integration/db/test_operation_state_repository.py",
    interviewPrompt: "为什么不能只依赖 LangGraph checkpoint？",
  },
  {
    id: "graph-dispatch",
    title: "LangGraph 场景分派",
    purpose: "共享可靠性入口，同时保持三业务证据和计划类型隔离。",
    source: ["src/opercerta/workflow/controlled_action_graph.py", "src/opercerta/application/scenario_registry.py"],
    inputOutput: "Operation state → inventory/equipment/task graph",
    databaseEffect: "保存图状态和节点审计。",
    failureBehavior: "未知场景安全失败，不自由选择工具。",
    evidence: "tests/integration/workflow/test_controlled_action_graph.py",
    interviewPrompt: "为什么没有使用开放式 ReAct 自由路由？",
  },
  {
    id: "evidence-tools",
    title: "Redis 与六个 MCP 工具取证",
    purpose: "用协议边界读取状态、规则和工单；缓存仅优化初次只读证据。",
    source: ["src/opercerta/infrastructure/cache.py", "src/opercerta/infrastructure/mcp_gateway.py", "src/opercerta/tools/server.py"],
    inputOutput: "Typed tool arguments → validated evidence models",
    databaseEffect: "证据快照写入 evidence 表；Redis 不是事实源。",
    failureBehavior: "缓存错误旁路 MCP；未知工具被 allowlist 拒绝。",
    evidence: "tests/integration/mcp/test_gateway.py",
    interviewPrompt: "为什么批准后必须绕过 Redis？",
  },
  {
    id: "assessment-model",
    title: "确定性评估与受限模型解释",
    purpose: "代码决定动作参数，Kimi 只解释 summary/rationale。",
    source: ["src/opercerta/domain/replenishment.py", "src/opercerta/domain/maintenance.py", "src/opercerta/domain/task_recovery.py", "src/opercerta/infrastructure/model_gateway.py"],
    inputOutput: "Evidence bundle → assessment + typed plan + optional explanation",
    databaseEffect: "保存 assessment/plan；query 在此 completed。",
    failureBehavior: "真实模型失败不回退 Mock 后继续写。",
    evidence: "tests/unit/infrastructure/test_model_gateway.py",
    interviewPrompt: "哪些字段永远不能由模型决定？",
  },
  {
    id: "interrupt-binding",
    title: "审批绑定、Checkpoint 与 Interrupt",
    purpose: "把批准对象绑定到证据、规则、事实和计划。",
    source: ["src/opercerta/domain/approvals.py", "src/opercerta/workflow/controlled_action_graph.py"],
    inputOutput: "Plan → ApprovalBinding + awaiting_approval",
    databaseEffect: "保存 binding、状态和 LangGraph checkpoint。",
    failureBehavior: "缺少 checkpoint 或业务状态不一致时不猜测成功。",
    evidence: "tests/integration/workflow/test_restart_recovery.py",
    interviewPrompt: "审批为什么不能只是 approved=true？",
  },
  {
    id: "atomic-approval",
    title: "PostgreSQL 行锁原子审批",
    purpose: "让并发批准/拒绝只有一个数据库胜者。",
    source: ["src/opercerta/infrastructure/db/approval_repository.py"],
    inputOutput: "BoundApprovalCommand → stored decision or conflict",
    databaseEffect: "同一事务锁 operation、插入一条 approval、追加审计。",
    failureBehavior: "其余竞态请求返回稳定 409。",
    evidence: "tests/integration/db/test_approval_race.py",
    interviewPrompt: "为什么 Python Lock 不能代替数据库锁？",
  },
  {
    id: "revalidate-resume",
    title: "恢复后无缓存复核",
    purpose: "批准后重新读取真实事实并比较 binding。",
    source: ["src/opercerta/workflow/controlled_action_recovery.py", "src/opercerta/workflow/recovery_coordinator.py"],
    inputOutput: "Checkpoint + fresh MCP evidence → continue or snapshot mismatch",
    databaseEffect: "保存 refresh evidence；不覆盖原批准计划。",
    failureBehavior: "任何关键哈希变化都零工单失败。",
    evidence: "tests/integration/workflow/test_restart_recovery.py",
    interviewPrompt: "为什么审批后还要重新取证？",
  },
  {
    id: "idempotent-write",
    title: "幂等工单、写后读、终态审计与 SSE",
    purpose: "把可能重放的图节点约束为一张有效业务工单。",
    source: ["src/opercerta/infrastructure/db/work_order_repository.py", "src/opercerta/tools/server.py", "src/opercerta/api/app.py"],
    inputOutput: "Typed work-order command → unique work order + completed result",
    databaseEffect: "唯一键写入工单，读取验证后原子保存终态审计。",
    failureBehavior: "相同 idempotency key 返回同一工单；冲突 payload 安全失败。",
    evidence: "tests/integration/db/test_work_order_idempotency.py",
    interviewPrompt: "为什么只能称 effectively-once，而不是端到端 exactly-once？",
  },
];

export type TechnologyFact = {
  name: string;
  responsibility: string;
  verifiedEffect: string;
};

export const TECHNOLOGIES: readonly TechnologyFact[] = [
  { name: "React", responsibility: "场景、角色、详情、审批和审计 UI", verifiedEffect: "三业务同页、公开页零 API、移动布局" },
  { name: "FastAPI", responsibility: "HTTP、JWT/RBAC、严格输入、错误 envelope 与 lifespan", verifiedEffect: "非法输入零 operation，调用者不能伪造审批身份" },
  { name: "LangGraph", responsibility: "状态机、interrupt、checkpoint 与恢复", verifiedEffect: "API/MCP 重启后仍保持等待审批并继续执行" },
  { name: "FastMCP", responsibility: "六个白名单工具与结构化协议边界", verifiedEffect: "独立服务、输入输出双向校验、写后读" },
  { name: "PostgreSQL", responsibility: "业务真相、行锁、唯一约束和有序审计", verifiedEffect: "审批竞态一个胜者，一个 operation 最多一张工单" },
  { name: "Redis", responsibility: "初次取证和 query 的短 TTL 只读缓存", verifiedEffect: "缓存失败旁路，批准后复核强制绕过缓存" },
  { name: "Kimi K2.6", responsibility: "只生成受限的 summary/rationale 解释字段", verifiedEffect: "三业务 3 条真实模型写路径，无权决定动作参数" },
  { name: "Docker Compose", responsibility: "PostgreSQL、Redis、bootstrap、MCP、API 与 Caddy 的本地编排", verifiedEffect: "只暴露 Caddy，服务重启后恢复业务" },
  { name: "OpenTelemetry", responsibility: "关联 API、Graph、MCP、Redis 与 SQL 观测跨度", verifiedEffect: "属性 allowlist，不记录 token、Prompt 或 SQL 参数" },
  { name: "GitHub Actions", responsibility: "锁文件、静态质量、测试与 Compose 远程门禁", verifiedEffect: "PR 快速检查与 main release smoke 分层" },
];
```

- [ ] **Step 4: Write and run failing engineering content tests**

```tsx
it("maps every engineering step to source, evidence, failure behavior and an interview prompt", () => {
  render(<EngineeringWalkthrough />);
  expect(screen.getAllByRole("button", { name: /查看步骤/ })).toHaveLength(10);
  for (const label of ["React", "FastAPI", "LangGraph", "FastMCP", "PostgreSQL", "Redis", "Kimi K2.6", "Docker Compose", "OpenTelemetry", "GitHub Actions"]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  expect(screen.getByText("inventory.get_snapshot")).toBeInTheDocument();
  expect(screen.getByText("equipment.get_status")).toBeInTheDocument();
  expect(screen.getByText("task.get_status")).toBeInTheDocument();
});
```

Run:

```powershell
npm run test:run -- src/engineering/EngineeringWalkthrough.test.tsx
```

Expected: FAIL because the engineering components do not exist.

- [ ] **Step 5: Implement the walkthrough components**

`FlowStepDetail` uses real buttons, not clickable divs:

```tsx
export function FlowStepDetail({ steps }: { steps: readonly EngineeringStep[] }) {
  const [selectedId, setSelectedId] = useState(steps[0].id);
  const selected = steps.find((step) => step.id === selectedId) ?? steps[0];
  return (
    <section aria-labelledby="flow-detail-title">
      <h2 id="flow-detail-title">完整请求链路</h2>
      <div className="engineering-step-list">
        {steps.map((step, index) => (
          <button aria-pressed={step.id === selectedId} key={step.id} onClick={() => setSelectedId(step.id)}>
            <span>{String(index + 1).padStart(2, "0")}</span>{step.title}<span className="sr-only">查看步骤</span>
          </button>
        ))}
      </div>
      <article className="engineering-step-detail">
        <h3>{selected.title}</h3><p>{selected.purpose}</p>
        <dl>
          <div><dt>源码</dt><dd>{selected.source.map((path) => <a key={path} href={sourceHref(path)}>{path}</a>)}</dd></div>
          <div><dt>输入输出</dt><dd>{selected.inputOutput}</dd></div>
          <div><dt>数据库变化</dt><dd>{selected.databaseEffect}</dd></div>
          <div><dt>失败行为</dt><dd>{selected.failureBehavior}</dd></div>
          <div><dt>自动化证据</dt><dd><a href={sourceHref(selected.evidence)}>{selected.evidence}</a></dd></div>
          <div><dt>面试追问</dt><dd>{selected.interviewPrompt}</dd></div>
        </dl>
      </article>
    </section>
  );
}
```

`ScenarioMatrix` consumes `SCENARIOS`; `TechnologyMap` renders the ten rows specified in design section 6.3. `EngineeringWalkthrough` renders a normal-flow table of contents, `FlowStepDetail`, `ScenarioMatrix`, and `TechnologyMap` without fixed/sticky layout.

- [ ] **Step 6: Wire `App` through the pure route resolver**

```tsx
export default function App({
  development = import.meta.env.DEV,
  hostname = window.location.hostname,
}: AppProps = {}) {
  const page = resolvePageKind(window.location.pathname, hostname, development);
  if (page === "showcase") return <ShowcasePage />;
  if (page === "engineering") return <EngineeringWalkthrough />;
  if (page === "console") {
    const apiBaseUrl = resolveConsoleApiBaseUrl(hostname);
    return apiBaseUrl === null ? <ConsoleUnavailable /> : <ConsoleApp apiBaseUrl={apiBaseUrl} />;
  }
  return <main className="not-found"><h1>页面不存在</h1><a href="/">返回项目专题</a></main>;
}
```

- [ ] **Step 7: Verify GREEN and commit**

Run:

```powershell
npm run test:run -- src/App.test.tsx src/engineering/EngineeringWalkthrough.test.tsx src/runtime/page-runtime.test.ts
npm run build
Set-Location ..
git add web/src/App.tsx web/src/App.test.tsx web/src/engineering web/src/styles.css
git commit -m "feat: add localhost engineering walkthrough"
```

Expected: local engineering route PASS, production isolation PASS, build exits 0.

---

### Task 5: Incident Reviews and Local Mastery State

**Files:**
- Modify: `web/src/engineering/engineering-content.ts`
- Create: `web/src/engineering/IncidentReview.tsx`
- Create: `web/src/engineering/MasteryChecklist.tsx`
- Create: `web/src/engineering/MasteryChecklist.test.tsx`
- Modify: `web/src/engineering/EngineeringWalkthrough.tsx`
- Modify: `web/src/engineering/EngineeringWalkthrough.test.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Produces: `INCIDENTS`, `MASTERY_ITEMS`.
- Produces: `MasteryChecklist` using storage key `opercerta.engineering.mastery.v1`.
- No network access and no public render path.

- [ ] **Step 1: Write failing localStorage behavior tests**

```tsx
it("persists only local mastery item ids", () => {
  render(<MasteryChecklist />);
  fireEvent.click(screen.getByRole("checkbox", { name: /画出完整请求链路/ }));
  expect(JSON.parse(localStorage.getItem("opercerta.engineering.mastery.v1") ?? "[]")).toEqual([
    "explain-flow",
  ]);
});

it("recovers from invalid local mastery state and can reset", () => {
  localStorage.setItem("opercerta.engineering.mastery.v1", "not-json");
  render(<MasteryChecklist />);
  expect(screen.getAllByRole("checkbox", { checked: false })).toHaveLength(4);
  fireEvent.click(screen.getByRole("button", { name: "重置本地进度" }));
  expect(localStorage.getItem("opercerta.engineering.mastery.v1")).toBeNull();
});
```

- [ ] **Step 2: Run mastery tests and verify RED**

Run:

```powershell
Set-Location web
npm run test:run -- src/engineering/MasteryChecklist.test.tsx
```

Expected: FAIL because `MasteryChecklist` does not exist.

- [ ] **Step 3: Implement bounded local mastery persistence**

```tsx
const STORAGE_KEY = "opercerta.engineering.mastery.v1";
export const MASTERY_ITEMS = [
  ["explain-flow", "不看稿画出完整请求链路并说明三业务差异"],
  ["run-business", "亲手完成 query、创建、审批和终态查看"],
  ["diagnose-failure", "制造 MCP 故障或事实变化并解释为什么零工单"],
  ["change-rule", "按 TDD 修改一条合成规则并解释影响范围"],
] as const;

function readCompleted(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function MasteryChecklist() {
  const [completed, setCompleted] = useState(readCompleted);
  function toggle(id: string) {
    const next = completed.includes(id) ? completed.filter((item) => item !== id) : [...completed, id];
    setCompleted(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }
  function reset() {
    localStorage.removeItem(STORAGE_KEY);
    setCompleted([]);
  }
  return <section aria-labelledby="mastery-title"><h2 id="mastery-title">掌握检查</h2>{MASTERY_ITEMS.map(([id, label]) => (
    <label key={id}><input type="checkbox" checked={completed.includes(id)} onChange={() => toggle(id)} />{label}</label>
  ))}<button onClick={reset}>重置本地进度</button></section>;
}
```

- [ ] **Step 4: Add the exact incident set and rendering**

`INCIDENTS` contains the following ten sanitized records. Do not copy any credential, raw model output, traceback, or local secret into the implementation:

```ts
export type IncidentFact = {
  id: string;
  title: string;
  observation: string;
  rootCause: string;
  fix: string;
  verification: string;
  limitation: string;
  interviewLine: string;
};

export const INCIDENTS: readonly IncidentFact[] = [
  {
    id: "wsl-component-source",
    title: "WSL2 功能启用后被 Windows 回滚",
    observation: "DISM 显示启用成功，但重启提示功能未完成并撤销；组件修复最初返回 0x800f081f。",
    rootCause: "Windows 组件存储损坏，原始 LTSC 2021 ISO 的版本又低于主机 19044.5011，不能充当匹配修复源。",
    fix: "挂载版本与内部构建均为 19044.5011 的 LTSC 源，依次完成 DISM RestoreHealth、SFC 修复，再重新启用 WSL 与虚拟机平台。",
    verification: "DISM CheckHealth 无损坏、SFC 无完整性冲突，Ubuntu 在 WSL2 初始化，Docker 显示 WSL2 内核与 cgroup v2。",
    limitation: "这是本机开发环境修复，不是应用部署能力；匹配安装源也必须验证来源与哈希。",
    interviewLine: "我先区分功能开关失败和组件源不匹配，用同构建源修复系统，再验证 WSL2 与容器运行时，而不是反复执行安装命令。",
  },
  {
    id: "postgres-secret-traceback",
    title: "PostgreSQL 密码进入 traceback",
    observation: "数据库连接失败的异常文本曾包含测试角色密码。",
    rootCause: "含密码的完整 DSN 被底层异常格式化；仓库未提交并不意味着旧凭据仍然安全。",
    fix: "立即轮换数据库角色密码，并改用无密码 DSN、临时 PGPASSWORD、SecretStr 与安全错误映射。",
    verification: "以不回显方式重新连接，checkpointer 与完整回归通过，Git 跟踪文件不含新值。",
    limitation: "应用层脱敏不能替代终端历史、日志平台与主机权限治理。",
    interviewLine: "我把事故拆成旧秘密处置和未来泄露面治理：前者靠轮换，后者靠连接与错误边界重构。",
  },
  {
    id: "fastmcp-host-421",
    title: "FastMCP readiness 正常但业务调用 421",
    observation: "MCP 健康检查为 200，API 的真实 Streamable HTTP 调用却返回 dependency_unavailable。",
    rootCause: "DNS rebinding 防护拒绝 Compose 服务名 Host: mcp:8001；loopback 健康检查没有覆盖业务 Host。",
    fix: "先添加真实会话 RED 测试，再为监听地址、loopback 与 mcp[:8001] 配置最小 allowed-hosts 白名单。",
    verification: "MCP 集成回归与 Compose 的创建、审批、工单、审计闭环通过。",
    limitation: "部署域名或服务拓扑变化时必须重新审查 Host 白名单。",
    interviewLine: "readiness 只证明服务在线，不证明业务协议路径可用，所以我把服务发现 Host 纳入集成契约。",
  },
  {
    id: "failed-test-data-leak",
    title: "失败测试污染共享集成库",
    observation: "恢复测试捞到六条旧 operation，预期空结果变成多条恢复记录。",
    rootCause: "测试 harness 只在收到 HTTP 202 后登记清理 ID；503 之前数据库已落行，清理列表却没有记录。",
    fix: "确认目标为专用测试库后精确清理，并在 repository 创建成功时立即追踪 operation ID。",
    verification: "API/恢复聚焦测试与完整后端回归通过，开发和演示数据库未被清理。",
    limitation: "共享集成库仍要求测试数据命名、所有权与 finally 清理契约。",
    interviewLine: "业务失败也可能留下合法持久化痕迹；测试清理必须绑定数据库创建时刻，不能依赖最终 HTTP 响应。",
  },
  {
    id: "stale-compose-image",
    title: "旧 Compose 镜像制造指标矛盾",
    observation: "业务请求成功且 Redis hit 正常，但新增 MCP 调用指标始终为零。",
    rootCause: "Compose 复用了含缓存指标但不含新 MCP 指标的旧镜像，源码、镜像与实例版本不一致。",
    fix: "让验证脚本强制 docker compose up --build -d，并用资产测试锁定重建行为。",
    verification: "禁用缓存时每场景 10 次 MCP；启用时 2 次 MCP 加 8 次 hit，60/60 终态 completed。",
    limitation: "本地重建不等于生产镜像供应链；线上还需不可变 digest 与 commit 关联。",
    interviewLine: "我没有因 HTTP 成功接受矛盾指标，而是沿源码、镜像、实例版本链证明运行物过期。",
  },
  {
    id: "time-derived-approval-hash",
    title: "时间派生字段破坏审批哈希",
    observation: "设备事实和规则未变，只因创建与批准跨过一秒就出现 approval_snapshot_mismatch。",
    rootCause: "decision_facts_hash 纳入每秒变化的 heartbeat_age_seconds，而它只是展示派生值。",
    fix: "以 RED 测试固定 60/61 秒分类不变时哈希稳定，并改为绑定 source version、heartbeat、severity、state、stale 分类等稳定事实。",
    verification: "维护、设备工作流、重启、API 回归和三业务 release Compose 通过。",
    limitation: "跨过 stale 阈值会改变分类和哈希，这是应有的安全行为。",
    interviewLine: "审批哈希绑定可审计决策事实，不绑定每次读取都变化的 UI 展示值。",
  },
  {
    id: "caddy-route-order",
    title: "Caddy 路由顺序与故障响应边界",
    observation: "API 容器 readiness 为 200，但经 Caddy 得到 React HTML；重启窗口还可能返回空正文 502。",
    rootCause: "SPA catch-all 吞掉 API 路径，且诊断器错误假设代理错误也一定符合应用 JSON envelope。",
    fix: "用互斥 handle @api 与静态 handle 固定优先级；readiness 轮询容忍暂态非 JSON，业务终态仍严格校验。",
    verification: "caddy fmt、validate、资产测试和一键重启恢复 smoke 通过，内部 metrics/MCP/数据库未暴露。",
    limitation: "本地 HTTP 验证不包含真实域名 DNS、自动 HTTPS 与公网入站端口。",
    interviewLine: "我比较代理前后响应类型，把路由错误和业务错误分层；只放宽启动窗口解析，不放宽业务完成条件。",
  },
  {
    id: "kimi-compatibility",
    title: "OpenAI-compatible 不等于参数完全兼容",
    observation: "模型列表与认证有效，但 Kimi K2.6 首次 chat 请求仍返回 400；默认 thinking 又让严格 JSON content 为空。",
    rootCause: "适配器强制 temperature=0，且未显式处理供应商 thinking 扩展和响应位置。",
    fix: "不再强制 temperature，增加显式 thinking 配置并关闭该模式，只接受 summary/rationale 两字段。",
    verification: "三业务各一条真实模型写路径与唯一工单通过，随后 Mock release Compose 再次通过。",
    limitation: "只证明当前供应商与模型的代表性兼容，其他兼容服务仍需契约测试。",
    interviewLine: "兼容协议复用 endpoint 和消息形状，不代表采样参数、扩展字段和响应位置相同。",
  },
  {
    id: "layered-timeout-inversion",
    title: "外层 10 秒早于内层 30 秒超时",
    observation: "模型服务端预算为 30 秒，验证客户端却在 10 秒先断开。",
    rootCause: "只调了 adapter timeout，没有审查浏览器、验证器、反向代理与服务端的完整 deadline 链。",
    fix: "将验证客户端 timeout 做成 1–120 秒有界配置，并用 75 秒包住模型 30 秒预算；重试最多两次。",
    verification: "三业务六个代表 operation 完成，报告只记录实测总时长与请求范围，不把单样本当 SLA。",
    limitation: "端到端时间包含网络、编排和存储，不等于供应商纯模型延迟。",
    interviewLine: "外层 deadline 必须覆盖内层最坏预算，否则内层的安全错误处理没有机会返回。",
  },
  {
    id: "compose-credential-rotation",
    title: "本地 Compose 配置误回显后立即轮换",
    observation: "一次本地诊断命令误回显被忽略配置中的数据库连接行；模型密钥未回显。",
    rootCause: "诊断方式输出整行配置，依赖事后替换来脱敏，泄露边界不可靠。",
    fix: "把该数据库凭据视为已暴露，同步轮换密码与连接 URL，后续只输出 SET/UNSET、长度或布尔一致性。",
    verification: "以不回显方式确认配置一致，代码、Git 与证据文档不保存旧值或新值。",
    limitation: "删除消息或日志不能证明秘密恢复安全；还要按外部系统留存策略处理。",
    interviewLine: "秘密进入可持久化输出后不能靠撤回，我会先轮换，再把诊断接口改成只暴露状态。",
  },
];
```

`IncidentReview` renders these six fields with semantic `<details>` elements so all content remains in normal document flow.

- [ ] **Step 5: Verify local-only content and commit**

Run:

```powershell
npm run test:run -- src/engineering/MasteryChecklist.test.tsx src/engineering/EngineeringWalkthrough.test.tsx src/App.test.tsx
npm run build
Set-Location ..
git add web/src/engineering web/src/styles.css
git commit -m "feat: add engineering incidents and mastery checks"
```

Expected: localStorage tests PASS; production-route test proves mastery content is absent; build exits 0.

---

### Task 6: Local Release Gate, Browser Evidence, and Documentation

**Files:**
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Modify: `docs/demo-script.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/daily/2026-07-20.md`
- Modify: `docs/development-log/interview-casebook.md`
- Create after execution: `docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md`
- Test: all backend/frontend/runtime tests.

**Interfaces:**
- Consumes: verified build/test/browser facts from Tasks 1–5.
- Produces: truthful local release evidence and updated handoff.

- [ ] **Step 1: Run the complete frontend gate**

```powershell
Set-Location web
npm ci
npm run test:run
npm run build
Set-Location ..
```

Expected: exit 0 for install, all Vitest files PASS, TypeScript/Vite build exits 0. Record actual test-file/test counts and generated asset sizes; do not predict them.

- [ ] **Step 2: Run the complete backend and repository gate**

```powershell
uv sync --frozen --all-groups
uv run python -m pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/verify_repository_safety.py
```

Expected: every command exits 0. Record actual pytest count, formatted-file count, mypy source count, and locked package count.

- [ ] **Step 3: Run fresh Mock release Compose smoke**

```powershell
wsl -d Ubuntu -- bash -lc "cd /mnt/d/CODEX/agent-portfolio/opercerta && ./scripts/verify_release_compose.sh"
```

Expected: exits 0 after Caddy/static/API/MCP/database/restart checks and automatic volume cleanup. This does not call the real model again.

- [ ] **Step 4: Browser-verify both modes**

Run Vite locally and inspect:

```text
http://127.0.0.1:5173/
http://127.0.0.1:5173/engineering
http://127.0.0.1:5173/console
```

At 1440×900, 768×1024, and 390×844 verify public/engineering pages have no horizontal overflow, fixed module, scroll trap, obscured focus, console error, or missing content. Verify a production-host test cannot render `/engineering`. Capture images only after the content is verified and ensure no local path/token/credential is visible.

- [ ] **Step 5: Write evidence from observed facts**

The evidence file must contain:

```markdown
# OperCerta 零成本展示与工程拆解证据

## Verified commit
## Public/local route boundary
## Frontend gate with actual counts and asset sizes
## Backend/repository gate with actual counts
## Browser desktop/mobile observations
## Mock release Compose result
## Content/privacy scan
## Remaining public-production boundary
```

Update README/current state/handoff/index/daily log/interview casebook with actual results and the unchanged `CLOSED` production gate.

- [ ] **Step 6: Run documentation and safety checks**

```powershell
uv run python -m pytest tests/unit/runtime/test_release_assets.py tests/unit/runtime/test_static_hosting_assets.py tests/unit/scripts/test_verify_repository_safety.py -q
uv run python scripts/verify_repository_safety.py
git diff --check
```

Expected: all focused tests and safety checks PASS; diff check emits no output.

- [ ] **Step 7: Commit evidence separately**

```powershell
git add README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/demo-script.md docs/development-log docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md
git commit -m "docs: record zero-cost showcase evidence"
```

Expected: no generated secret, raw model output, `.env`, `.netlify`, or unrelated user file is staged.

---

### Task 7: GitHub PR and Current Remote CI Evidence

**Files:**
- Modify after real run: `docs/release-evidence/github-actions-ci.md`
- Modify after real run: `docs/development-log/current-state.md`
- Modify after real run: `IMPLEMENTATION_HANDOFF.md`

**Interfaces:**
- Consumes: complete local feature commits and all-green Task 6 gate.
- Produces: remote feature branch/PR, five-job main evidence after merge.

- [ ] **Step 1: Audit outgoing commit range**

```powershell
git status --short --branch
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Expected: only OperCerta commits are ahead; worktree is clean; diff check emits no output.

- [ ] **Step 2: Publish through a feature branch and draft PR**

Use `github:yeet` with branch `feat/zero-cost-showcase-walkthrough`. The PR body must state:

```markdown
## Scope
- recruiter-first static showcase
- localhost-only engineering walkthrough
- no public writable backend

## Evidence
- frontend/backend gates
- release Compose smoke
- production route isolation

## Boundary
OperCerta production release gate remains CLOSED. No other project is started.
```

Expected: remote branch exists and a draft PR URL is returned; no force push.

- [ ] **Step 3: Wait for and inspect all PR checks**

Expected quick jobs: repository safety, Python quality, backend tests, frontend. `compose-smoke` may remain skipped on PR according to current workflow. Any failure is diagnosed with `github:gh-fix-ci`; do not merge by ignoring a check.

- [ ] **Step 4: Merge only after checks are green, then verify main**

After user-approved normal merge or the existing repository policy, wait for the main workflow and verify all five jobs, including `compose-smoke`, succeed. Record PR number, run IDs, commit SHA, job conclusions, and timestamps.

- [ ] **Step 5: Update and commit remote evidence**

```powershell
git add docs/release-evidence/github-actions-ci.md docs/development-log/current-state.md IMPLEMENTATION_HANDOFF.md
git commit -m "docs: record showcase remote gate"
```

Expected: documentation contains observed IDs only and still states Release Tag/production gate are closed.

---

### Task 8: Netlify Preview, Production Deploy, and Portfolio Synchronization

**Files:**
- Modify: `D:\CODEX\resume\portfolio\tests\rendered-html.test.mjs`
- Modify: `D:\CODEX\resume\portfolio\app\page.tsx`
- Modify after real deploy: `docs/release-evidence/zero-cost-showcase-engineering-walkthrough.md`
- Modify after real deploy: `docs/development-log/current-state.md`
- Modify after real deploy: `DOCUMENT_INDEX.md`

**Interfaces:**
- Consumes: fixed all-green Git commit from Task 7.
- Produces: verified OperCerta Netlify preview/production and updated portfolio production page.

- [ ] **Step 1: Verify Netlify authentication and existing site link**

```powershell
npx netlify status
```

Expected: authenticated account and OperCerta site `opercerta-kxh`; if authentication is absent, stop and ask the user to complete browser login rather than creating another site.

- [ ] **Step 2: Build the fixed commit and deploy preview**

```powershell
Set-Location web
npm ci
npm run test:run
npm run build
Set-Location ..
npx netlify deploy --dir=web/dist --no-build
```

Expected: a unique draft deploy URL and site dashboard URL. Do not use `--prod` yet.

- [ ] **Step 3: Verify preview truthfulness and isolation**

Check with HTTP and browser:

```text
GET / -> 200 text/html and new OperCerta title/content
GET /engineering -> production not-found/public-safe content, no mastery checklist
GET /console -> static local-demo guidance, no fake API
GET /api/v1/auth/demo-token -> 200 text/html static fallback, not JSON
two evidence PNGs -> 200 image/png
no AI/Codex generation attribution or beginner language
no console error at desktop/mobile widths
```

Expected: every condition holds; otherwise fix source and repeat preview.

- [ ] **Step 4: Deploy the verified preview artifact to production**

```powershell
npx netlify deploy --prod --dir=web/dist --no-build
```

Expected: production URL remains `https://opercerta-kxh.netlify.app`; record deploy ID, production fingerprint, and dashboard log URL.

- [ ] **Step 5: Write the failing portfolio status test**

In `D:\CODEX\resume\portfolio\tests\rendered-html.test.mjs`:

```js
assert.match(html, /三业务与真实模型已验证 · 静态专题/);
assert.match(html, /库存补货、设备维修与作业恢复/);
assert.doesNotMatch(html, /下一阶段.*生产发布能力/);
```

Run the existing portfolio test command using the already verified shell configuration. Expected: FAIL because the current page still says only inventory and “下一阶段：生产发布能力”.

- [ ] **Step 6: Update only OperCerta portfolio copy**

Change the OperCerta project entry and focus card to these exact facts:

```ts
status: "三业务与真实模型已验证 · 静态专题",
description:
  "以库存补货、设备维修与作业恢复三条闭环展示可恢复 Agent 工程：证据取用、审批绑定、原子竞态、幂等写入、重启恢复与真实模型受限解释均有自动化证据。",
```

Focus card values:

```text
当前范围：三业务闭环
公开展示：静态专题已上线
产品门禁：CLOSED
```

Do not change the other three projects, contact information, global visual design, or unrelated dirty files.

- [ ] **Step 7: Verify and deploy the portfolio static mirror**

Run the portfolio build/test, verify the rendered HTML contract, then deploy preview before production using its existing Netlify site linkage. Verify `https://kxh-agent-portfolio.netlify.app` keeps one continuous page, project order, contact links, OperCerta URL, and three honest unstarted project states.

Expected: preview and production return 200; no hash navigation is introduced; only OperCerta copy changes.

- [ ] **Step 8: Record deploy evidence and final boundary**

Update the OperCerta evidence/current-state/index with both deploy IDs, URLs, fingerprints, HTTP results, browser observations, rollback targets, and the unchanged boundary:

```text
zero-cost recruiter showcase: VERIFIED
public writable OperCerta backend: NOT DEPLOYED
production release gate: CLOSED
user mastery: IN PROGRESS until manually completed
ForenTrail: NOT STARTED
```

Run documentation tests and repository safety once more, then commit only OperCerta documentation. Do not commit the dirty portfolio repository as a whole.

---

## Plan Self-Review

- **Spec coverage:** Task 1 covers shared facts and local route isolation; Tasks 2–3 cover recruiter content, human-crafted visual language, motion and no fixed modules; Tasks 4–5 cover detailed engineering flow, three businesses, technology effects, incidents and mastery; Task 6 covers local gates and evidence; Task 7 covers GitHub remote evidence; Task 8 covers Netlify production and portfolio synchronization.
- **Public boundary:** No task deploys FastAPI, MCP, PostgreSQL, Redis, JWT issuance, metrics or model keys to Netlify. `/engineering` remains local-development-only and `/console` remains local guidance on public hosts.
- **Content integrity:** The typed manifest owns current counts, provider/model and scenario/tool contracts. Docs are updated only after observed commands.
- **Visual integrity:** No fixed/sticky content modules, scroll snap, carousel, heavy animation library, autoplay media, empty video or generation attribution is introduced.
- **Type consistency:** `PageKind`, `resolvePageKind`, `ScenarioFact`, `PROJECT_FACTS`, `SCENARIOS`, `EngineeringStep`, `ENGINEERING_STEPS`, `INCIDENTS`, and the storage key are defined before use with identical names.
- **Scope:** The plan changes only OperCerta and the existing OperCerta card in the portfolio. Other project code remains unstarted.
- **Execution:** User previously selected inline execution and asked not to use subagents. Use `superpowers:executing-plans` with checkpoints after Tasks 3, 6, and 8.
