# OperCerta Public Portfolio Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a zero-cost, static OperCerta project showcase for HR and a separate, honest localhost console path for interviews, then add its verified URL to the existing personal portfolio.

**Architecture:** The existing Vite application becomes a tiny pathname router. `/` renders a backend-independent evidence showcase; `/console` renders the existing console only when a local or explicitly configured API base URL is available. Netlify serves only the Vite static output; the existing personal portfolio receives one outbound OperCerta card only after that static URL has been verified.

**Tech Stack:** React 19, TypeScript, Vite 8, Vitest, Netlify static hosting, existing Cloudflare/Vinext personal portfolio.

## Global Constraints

- Implement only OperCerta and its entry in `D:\CODEX\resume\portfolio`; do not start another project.
- Preserve every existing uncommitted change in `D:\CODEX\resume\portfolio`; stage and commit no user-owned hunk.
- Public content is static and uses only public or synthetic data; it never calls API, MCP, PostgreSQL, or LangGraph.
- The public page says `OperCerta release gate: CLOSED` and does not claim production IAM/SSO, automatic deployment, equipment scenario, complete E2E, real-model evaluation, or public write access.
- Do not show unmeasured metrics or link HR to the Private GitHub repository as if source were public.
- Keep `/console` as the existing real local demo. If no API base URL is available, render a clear local-start instruction and make no fetch request.
- Preserve existing frontend test, build, backend test, formatting, type-checking, CI, and Compose-smoke gates.

---

## File Structure

- `web/src/App.tsx` — pathname dispatcher for the static showcase, local console, and not-found state.
- `web/src/console/ConsoleApp.tsx` — extracted existing interactive console, parameterized by API base URL.
- `web/src/runtime/console-runtime.ts` — deterministic API-base resolution; no UI state.
- `web/src/runtime/console-runtime.test.ts` — API-base resolution boundary tests.
- `web/src/showcase/ShowcasePage.tsx` — factual, static project showcase content.
- `web/src/showcase/ShowcasePage.test.tsx` — public-content and no-network regression tests.
- `web/src/showcase/showcase-content.ts` — typed, centralized factual copy and evidence cards.
- `web/src/showcase/ConsoleUnavailable.tsx` — explicit no-API state for `/console`.
- `web/src/styles.css` — scoped showcase, console-unavailable, responsive, focus-visible styles.
- `web/index.html` — title and description matching the public showcase.
- `netlify.toml` — Vite build directory and SPA rewrite for `/console`.
- `docs/demo-script.md` — reproducible 3--5 minute interview walkthrough with only verified claims.
- `docs/development-log/daily/2026-07-18.md`, `docs/development-log/current-state.md`, `DOCUMENT_INDEX.md`, `IMPLEMENTATION_HANDOFF.md` — factual implementation and deployment state.
- `D:\CODEX\resume\portfolio\app/page.tsx` — one OperCerta entry only, added after a real showcase URL exists.

### Task 1: Isolate static showcase routing from the real console

**Files:**
- Create: `web/src/runtime/console-runtime.ts`
- Create: `web/src/runtime/console-runtime.test.ts`
- Create: `web/src/console/ConsoleApp.tsx`
- Create: `web/src/showcase/ConsoleUnavailable.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Test: `web/src/runtime/console-runtime.test.ts`, `web/src/App.test.tsx`

**Interfaces:**
- Produces `resolveConsoleApiBaseUrl(hostname: string, configuredBaseUrl?: string): string | null`.
- Produces `ConsoleApp({ apiBaseUrl }: { apiBaseUrl: string })`.
- Consumes the existing `ApiClient`, `DemoSession`, control, detail, approval, audit, and boundary components without changing their API contracts.

- [ ] **Step 1: Write the failing API-base resolution tests**

```ts
import { describe, expect, it } from "vitest";
import { resolveConsoleApiBaseUrl } from "./console-runtime";

describe("resolveConsoleApiBaseUrl", () => {
  it("uses the local Vite proxy on localhost", () => {
    expect(resolveConsoleApiBaseUrl("localhost")).toBe("");
  });

  it("uses an explicit HTTPS API base URL", () => {
    expect(resolveConsoleApiBaseUrl("opercerta.netlify.app", "https://api.example.test/")).toBe("https://api.example.test");
  });

  it("disables the console on a public host without an API URL", () => {
    expect(resolveConsoleApiBaseUrl("opercerta.netlify.app")).toBeNull();
  });
});
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `npm run test:run -- --run src/runtime/console-runtime.test.ts` from `web/`.

Expected: FAIL because `console-runtime` does not exist.

- [ ] **Step 3: Implement deterministic API-base resolution**

```ts
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

export function resolveConsoleApiBaseUrl(
  hostname: string,
  configuredBaseUrl = import.meta.env.VITE_API_BASE_URL,
): string | null {
  const normalized = configuredBaseUrl?.trim().replace(/\/$/, "");
  if (normalized) return normalized;
  return LOCAL_HOSTS.has(hostname) ? "" : null;
}
```

- [ ] **Step 4: Extract the existing console into `ConsoleApp`**

Move the current `App` console body into `ConsoleApp`. Construct both clients with the resolved base URL:

```ts
const tokenClient = useMemo(() => new ApiClient(() => "", apiBaseUrl), [apiBaseUrl]);
const client = useMemo(
  () => new ApiClient(() => session.authorizationHeader(), apiBaseUrl),
  [apiBaseUrl, session],
);
```

Add `ConsoleUnavailable` with a heading, the exact statement that the public showcase has no public write service, and the local command sequence `docker compose up --build` followed by opening `http://localhost:5173/console`. Do not embed credentials or a public API URL.

- [ ] **Step 5: Make `App` a pathname dispatcher and write UI RED tests**

Set the JSDOM path using `window.history.pushState({}, "", "/")` before rendering. Add tests asserting:

```tsx
it("renders the static showcase at the root without calling fetch", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  window.history.pushState({}, "", "/");
  render(<App />);
  expect(screen.getByRole("heading", { name: /OperCerta/i })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("renders the local-start instruction for /console on a public host", () => {
  window.history.pushState({}, "", "/console");
  render(<App />);
  expect(screen.getByText(/docker compose up --build/i)).toBeInTheDocument();
});
```

The dispatcher shape is:

```tsx
export default function App() {
  const apiBaseUrl = resolveConsoleApiBaseUrl(window.location.hostname);
  if (window.location.pathname === "/") return <ShowcasePage />;
  if (window.location.pathname === "/console") {
    return apiBaseUrl === null ? <ConsoleUnavailable /> : <ConsoleApp apiBaseUrl={apiBaseUrl} />;
  }
  return <main className="not-found"><h1>页面不存在</h1><a href="/">返回项目专题</a></main>;
}
```

- [ ] **Step 6: Update `ApiClient` for the injected base URL**

Change the constructor and path creation without changing request bodies or authorization behavior:

```ts
export class ApiClient {
  constructor(
    private readonly authorizationHeader: () => string,
    private readonly apiBaseUrl = "",
  ) {}

  private endpoint(path: string): string {
    return `${this.apiBaseUrl}${path}`;
  }
}
```

Replace every `fetch("/api/...`)` with `fetch(this.endpoint("/api/..."))`. Extend `client.test.ts` with one assertion that `new ApiClient(() => "", "https://api.example.test")` calls `https://api.example.test/api/v1/auth/demo-token`.

- [ ] **Step 7: Run focused tests to verify GREEN**

Run: `npm run test:run -- --run src/runtime/console-runtime.test.ts src/App.test.tsx src/api/client.test.ts` from `web/`.

Expected: all focused tests pass; the existing in-memory token and six-field approval assertions remain unchanged.

- [ ] **Step 8: Commit the isolated routing boundary**

```bash
git add web/src/App.tsx web/src/App.test.tsx web/src/api/client.ts web/src/api/client.test.ts web/src/console web/src/runtime web/src/showcase/ConsoleUnavailable.tsx
git commit -m "feat: separate public showcase from local console"
```

### Task 2: Build the factual static OperCerta showcase

**Files:**
- Create: `web/src/showcase/showcase-content.ts`
- Create: `web/src/showcase/ShowcasePage.tsx`
- Create: `web/src/showcase/ShowcasePage.test.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/index.html`
- Test: `web/src/showcase/ShowcasePage.test.tsx`

**Interfaces:**
- `SHOWCASE_EVIDENCE` is a readonly list of `{ title: string; claim: string; scope: string }`.
- `ShowcasePage()` is network-free and only renders the typed local content.

- [ ] **Step 1: Write failing static-content tests**

```tsx
it("renders the inventory-to-work-order loop and closed gate", () => {
  render(<ShowcasePage />);
  expect(screen.getByText(/库存不足.*补货工单/)).toBeInTheDocument();
  expect(screen.getByText(/release gate: CLOSED/i)).toBeInTheDocument();
});

it("states the limits instead of presenting an online write service", () => {
  render(<ShowcasePage />);
  expect(screen.getByText(/不提供公开可写服务/)).toBeInTheDocument();
  expect(screen.getByText(/Private GitHub/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the showcase test to verify RED**

Run: `npm run test:run -- --run src/showcase/ShowcasePage.test.tsx` from `web/`.

Expected: FAIL because `ShowcasePage` does not exist.

- [ ] **Step 3: Define only evidence-backed showcase content**

Create `showcase-content.ts` with facts already in repository evidence, including the exact categories `非法输入`, `状态恢复`, `审批竞态`, `幂等写入`, `重启恢复`, and their evidence scope. Use factual wording such as `已具备本地与 CI 自动化证据` rather than performance claims. Add one `LIMITATIONS` list containing `Mock 模型`, `Private GitHub`, `未完成设备场景`, `生产 IAM/SSO`, `自动部署`, `完整浏览器 E2E`, and `不提供公开可写服务`.

- [ ] **Step 4: Implement the static page**

Use semantic sections and static anchors:

```tsx
export function ShowcasePage() {
  return (
    <main className="showcase-shell">
      <section className="showcase-hero" aria-labelledby="showcase-title">
        <p className="showcase-kicker">OPERATIONS AGENT / EVIDENCE-DRIVEN ENGINEERING</p>
        <h1 id="showcase-title">OperCerta</h1>
        <p>从库存不足识别到审批绑定、幂等补货工单与审计回放的可恢复运营 Agent。</p>
        <a href="#evidence">查看工程证据</a>
        <a href="/console">现场演示入口</a>
      </section>
      <section id="evidence" aria-labelledby="evidence-title">{/* SHOWCASE_EVIDENCE cards */}</section>
      <section aria-labelledby="boundary-title">{/* LIMITATIONS and CLOSED gate */}</section>
    </main>
  );
}
```

Render the architecture as HTML/CSS nodes and arrows with accessible text, not an image or invented logo. The source code section must say that the repository is Private and that code/test evidence is available in a controlled review or interview; do not render a GitHub URL.

- [ ] **Step 5: Add scoped responsive and accessible styles**

Append `.showcase-*`, `.console-unavailable`, and `.not-found` selectors. Reuse the existing dark palette (`#111827`, `#79d9cf`, `#ffcb85`) so `/console` remains visually coherent. Provide visible focus outlines, a one-column layout below `900px`, and no auto-playing media.

- [ ] **Step 6: Update static document metadata**

In `web/index.html`, set the title to `OperCerta | 可恢复运营 Agent` and add:

```html
<meta name="description" content="OperCerta：以审批绑定、原子竞态控制和幂等工单为核心的可恢复运营 Agent 项目专题。" />
```

- [ ] **Step 7: Run focused tests and the frontend build to verify GREEN**

Run: `npm run test:run -- --run src/showcase/ShowcasePage.test.tsx src/App.test.tsx` from `web/`.

Run: `npm run build` from `web/`.

Expected: showcase assertions pass and Vite emits `dist/` with exit code 0.

- [ ] **Step 8: Commit the static showcase**

```bash
git add web/src/showcase web/src/styles.css web/index.html
git commit -m "feat: add evidence-backed OperCerta showcase"
```

### Task 3: Package the static site and prepare honest interview material

**Files:**
- Create: `netlify.toml`
- Create: `docs/demo-script.md`
- Modify: `README.md`
- Modify: `DOCUMENT_INDEX.md`
- Modify: `docs/development-log/daily/2026-07-18.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`
- Create: `tests/unit/runtime/test_static_hosting_assets.py`
- Test: `tests/unit/runtime/test_static_hosting_assets.py`

**Interfaces:**
- Netlify builds from `web/`, publishes `web/dist/`, and rewrites `/console` to Vite `index.html`.
- `docs/demo-script.md` is the sole script for a 3--5 minute live demo and contains no credentials.

- [ ] **Step 1: Write a failing static-hosting asset test**

Create `tests/unit/runtime/test_static_hosting_assets.py` with a focused test that reads `netlify.toml` and asserts:

```python
assert 'base = "web"' in content
assert 'command = "npm run build"' in content
assert 'publish = "dist"' in content
assert 'from = "/*"' in content
assert 'to = "/index.html"' in content
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `uv run pytest tests/unit/runtime/test_static_hosting_assets.py -q` from the repository root.

Expected: FAIL because `netlify.toml` does not exist or does not satisfy the assertions.

- [ ] **Step 3: Add the Netlify static-only configuration**

Create exactly:

```toml
[build]
  base = "web"
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

- [ ] **Step 4: Create the interview script and evidence capture checklist**

`docs/demo-script.md` must specify this order: show static project page; explain the closed gate; start or confirm local Compose health; open `/console`; create a low-inventory operation; bind and approve as the appropriate demo role; show a single work order and audit sequence; explain one approval race test and one restart-recovery test; finish with the known limitations. It must instruct the presenter to record only a successful run actually visible in the browser and to omit any unverified statement.

- [ ] **Step 5: Record factual documentation state**

Update the four repository documents to distinguish:

- static showcase implemented and locally verified;
- static public URL pending deployment until externally authorized;
- current release gate still `CLOSED`;
- Linux/Docker Compose has already been verified locally, while production high availability has not.

Correct the stale handoff phrase saying Linux/Docker is unverified.

- [ ] **Step 6: Run the hosting test, full frontend gate, and repository safety gate**

Run:

```bash
uv run pytest tests/unit/runtime/test_static_hosting_assets.py -q
cd web && npm run test:run && npm run build
cd .. && uv run python scripts/verify_repository_safety.py
```

Expected: all commands exit 0. The safety scan must find no tracked secrets, unpinned Actions, or unauthorized write permissions.

- [ ] **Step 7: Commit packaging and documentation**

```bash
git add netlify.toml docs/demo-script.md README.md DOCUMENT_INDEX.md IMPLEMENTATION_HANDOFF.md docs/development-log tests/unit/runtime/test_static_hosting_assets.py
git commit -m "docs: prepare OperCerta public showcase"
```

### Task 4: Validate real local material and publish only the static showcase

**Files:**
- Create: `web/public/evidence/console-approval-flow.png`
- Create: `web/public/evidence/console-audit-flow.png`
- Modify: `web/src/showcase/ShowcasePage.tsx`
- Modify: `web/src/showcase/ShowcasePage.test.tsx`
- Modify: `docs/release-evidence/public-portfolio-showcase.md`
- Modify: `docs/development-log/daily/2026-07-18.md`

**Interfaces:**
- Screenshot assets come from a real local OperCerta run with synthetic data only.
- The public page displays screenshots only after their source run is recorded in release evidence.

- [ ] **Step 1: Write a failing screenshot-alt-text test**

```tsx
it("labels both screenshots as local synthetic-data evidence", () => {
  render(<ShowcasePage />);
  expect(screen.getByAltText(/本地合成数据.*审批流程/)).toBeInTheDocument();
  expect(screen.getByAltText(/本地合成数据.*审计流程/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the screenshot test to verify RED**

Run: `npm run test:run -- --run src/showcase/ShowcasePage.test.tsx` from `web/`.

Expected: FAIL because no evidence screenshots are rendered.

- [ ] **Step 3: Produce screenshots from a real local run**

Start the existing Compose stack using the existing ignored `.env.compose`; wait for API and MCP health checks; use `/console` to complete the documented low-inventory approval flow. Capture only the browser regions needed to show approval binding and audit timeline, remove any local path, username, token, or database value from the frame, and save the two PNG files at the exact paths above. Do not stage an image unless its matching operation and audit facts are recorded.

- [ ] **Step 4: Add the two labeled images and write release evidence**

Render images with fixed, truthful captions. `docs/release-evidence/public-portfolio-showcase.md` must record date, command, exact observed operation state, the screenshot filenames, the fact that the source was local synthetic data, and the statement that it is not an online production demonstration.

- [ ] **Step 5: Run focused and full frontend verification**

Run: `npm run test:run -- --run src/showcase/ShowcasePage.test.tsx` and then `npm run test:run && npm run build` from `web/`.

Expected: all tests and build pass; screenshots are loaded from local static assets.

- [ ] **Step 6: Commit real evidence**

```bash
git add web/public/evidence web/src/showcase/ShowcasePage.tsx web/src/showcase/ShowcasePage.test.tsx docs/release-evidence/public-portfolio-showcase.md docs/development-log/daily/2026-07-18.md
git commit -m "docs: add verified showcase evidence"
```

- [ ] **Step 7: Request explicit deployment authorization and deploy**

Before external deployment, request confirmation that the user authorizes a Netlify account/site connection and production static deploy. Then use the Netlify deployment workflow to deploy the current commit, visit both `/` and `/console` over HTTPS, verify that `/` makes no API request and `/console` shows the local-start instruction, and record the real URL plus deployment commit in the release-evidence document. Do not deploy API, MCP, PostgreSQL, Redis, or a public write route.

### Task 5: Add the verified OperCerta URL to the personal portfolio without absorbing user changes

**Files:**
- Modify: `D:\CODEX\resume\portfolio\app/page.tsx`
- Modify: `D:\CODEX\resume\portfolio\README.md` only if its user-owned deployment documentation already has a project-links section
- Test: `npm run build` in `D:\CODEX\resume\portfolio`

**Interfaces:**
- Consumes the exact HTTPS URL verified in Task 4.
- Produces one `OperCerta` project card with `target="_blank"` and `rel="noreferrer"`.

- [ ] **Step 1: Establish a portfolio baseline without mutation**

Run `git status --short --branch` and `git diff -- app/page.tsx` in `D:\CODEX\resume\portfolio`. Record that all pre-existing dirty hunks are user-owned. Run `npm run build`; if it fails before the OperCerta entry is added, stop and report the baseline failure instead of attributing it to this work.

- [ ] **Step 2: Add a single OperCerta card using the verified URL**

Extend the existing project data with this factual content, preserving the surrounding user design:

```ts
["04", "OperCerta", "面向库存异常的可恢复运营 Agent：审批绑定、原子竞态控制、幂等补货工单与可审计恢复。", "LANGGRAPH / FASTAPI / MCP / POSTGRESQL"]
```

Render the row link with:

```tsx
<a href={opercertaUrl} target="_blank" rel="noreferrer" aria-label="打开 OperCerta 项目专题">↗</a>
```

Use the verified URL literal received from Task 4; do not add any link before that value exists.

- [ ] **Step 3: Verify only the portfolio build**

Run: `npm run build` from `D:\CODEX\resume\portfolio`.

Expected: exit code 0. If it fails, compare the failure against the Step 1 baseline before changing any file.

- [ ] **Step 4: Preserve staging ownership**

Inspect `git diff -- app/page.tsx` and stage only the explicit OperCerta-card hunk using a patch that contains that hunk. Do not run `git add app/page.tsx`, do not commit other files, and do not deploy the portfolio until the user separately confirms the existing portfolio version is ready for public deployment.

### Task 6: Final verification, CI evidence, and release-boundary handoff

**Files:**
- Modify: `docs/release-evidence/public-portfolio-showcase.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`

- [ ] **Step 1: Run the complete OperCerta local gate**

Run from the OperCerta root:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/verify_repository_safety.py
cd web && npm run test:run && npm run build
```

Expected: every command exits 0. Record actual counts and durations only after observing them; do not reuse old counts.

- [ ] **Step 2: Push through the existing PR-only rule and inspect CI**

Create a feature branch/worktree before implementation, push it, open a PR, wait for the four fast jobs, merge only when they are green, then verify the main-only `compose-smoke` job. Preserve the current manual branch-protection rule and do not force-push.

- [ ] **Step 3: Write final evidence without changing the release status**

Record actual deployment URL, commit, local commands, CI run URLs, static-page behavior, and any remaining risks. The conclusion must state: the public static showcase is deployed if and only if its URL was directly verified; OperCerta production release remains `CLOSED` until the original detailed-design release gates are completed.

- [ ] **Step 4: Deliver the interview handoff**

Provide the public portfolio URL only after portfolio deployment is separately authorized and verified; otherwise provide the verified OperCerta static URL and the exact local interview startup sequence. State whether the video recording remains a user action or has been recorded and evidenced.

## Plan Self-Review

- **Spec coverage:** Task 1 covers static/local boundary and clear offline behavior; Task 2 covers factual static content; Task 3 covers Netlify packaging, demo script, and documentation; Task 4 covers real screenshots and static deployment; Task 5 covers the constrained portfolio entry; Task 6 covers CI, evidence, and CLOSED gate retention.
- **No-placeholder review:** external URLs are intentionally prohibited until Task 4 returns a verified value; no temporary URL is allowed. The only manual dependency is explicit user deployment authorization and any recording action, both named as gates rather than implied completed work.
- **Interface review:** `resolveConsoleApiBaseUrl` returns `string | null`, `ConsoleApp` receives only a string, and `ApiClient` receives the same base string. Every later task uses these exact names.
