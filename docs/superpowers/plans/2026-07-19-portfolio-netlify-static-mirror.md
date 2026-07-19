# Portfolio Netlify Static Mirror Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a fast, public Netlify static mirror of the existing portfolio that safely links to the verified OperCerta static showcase.

**Architecture:** `D:\CODEX\resume\portfolio` remains the only hand-maintained Vinext/Sites source. A separate `D:\CODEX\resume\portfolio-netlify` Node project builds that source, renders its already-built worker entry for `/`, copies `dist/client` into its own `dist`, validates the generated HTML and assets, then deploys the resulting static directory to a new Netlify site. No Netlify Function, API, database, token, or OperCerta write endpoint is added.

**Tech Stack:** Node.js 22+, existing Vinext production build, Node built-in test runner, Netlify CLI, static HTML/CSS/JS.

## Global Constraints

- Only implement the public portfolio entry; OperCerta product release gate remains `CLOSED`.
- Do not change, stage, reset, clean, or commit existing user changes under `D:\CODEX\resume\portfolio`.
- The source portfolio has `.openai/hosting.json`; do not deploy that project through Netlify. The mirror project must be a sibling directory without that file.
- Reuse the existing visual output; do not duplicate or rewrite the React page and CSS.
- Never overwrite the existing Netlify site `opercerta-kxh`.
- The mirror is static only: no public business write path, API URL, demo credential, database string, or invented performance claim.
- On Windows, source `npm run build` must use the verified Git Bash script shell at `F:\Git\bin\bash.exe`; fail explicitly if it is unavailable instead of silently producing incomplete output.
- Every deployment claim must be backed by fresh local and public verification evidence.

## File Structure

| Path | Responsibility |
| --- | --- |
| `D:\CODEX\resume\portfolio-netlify\package.json` | Declares Node version and `test`, `export`, `verify` commands for the independent mirror project. |
| `D:\CODEX\resume\portfolio-netlify\.gitignore` | Excludes generated `dist`, Netlify local state and logs. |
| `D:\CODEX\resume\portfolio-netlify\src\export-static.mjs` | Builds source, renders `/`, copies client assets, validates HTML, and writes the static output. |
| `D:\CODEX\resume\portfolio-netlify\scripts\export-static.mjs` | Thin CLI that resolves paths and calls the export library. |
| `D:\CODEX\resume\portfolio-netlify\tests\export-static.test.mjs` | Node tests for HTML contract, local-asset verification, failure behavior, and output safety. |
| `D:\CODEX\resume\portfolio-netlify\netlify.toml` | Declares `dist` as the publish directory; intentionally has no cloud build command. |
| `docs/development-log/daily/2026-07-19.md` | Records the Sites 403 observation, Netlify fallback and factual deployment result. |
| `docs/development-log/current-state.md` | Replaces the pending portfolio-entry status only after successful public verification. |
| `docs/development-log/interview-casebook.md` | Adds the deployment-versus-accessibility troubleshooting case. |
| `DOCUMENT_INDEX.md` | Adds the implementation plan and the resulting evidence document after it exists. |
| `docs/release-evidence/portfolio-netlify-static-mirror.md` | Created only after real preview/production verification; contains URL, deployment identity, checks, rollback and limitations. |

---

### Task 1: Create the independent mirror project and RED contract tests

**Files:**
- Create: `D:\CODEX\resume\portfolio-netlify\package.json`
- Create: `D:\CODEX\resume\portfolio-netlify\.gitignore`
- Create: `D:\CODEX\resume\portfolio-netlify\tests\export-static.test.mjs`
- Create: `D:\CODEX\resume\portfolio-netlify\netlify.toml`

**Interfaces:**
- Consumes: a generated source client directory and an SSR response supplied by a fake renderer.
- Produces: test expectations for `assertRenderedHtml(html, outputDirectory)` and `writeStaticMirror(options)` from `src/export-static.mjs`.

- [ ] **Step 1: Create the mirror project manifest and ignore rules**

```json
{
  "name": "kxh-agent-portfolio-netlify",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22.13.0" },
  "scripts": {
    "test": "node --test tests/export-static.test.mjs",
    "export": "node scripts/export-static.mjs",
    "verify": "npm run test && npm run export"
  }
}
```

```gitignore
dist/
.netlify/
*.log
```

```toml
[build]
  publish = "dist"

[build.environment]
  NODE_VERSION = "22"
```

- [ ] **Step 2: Write failing tests before creating the implementation module**

```js
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { assertRenderedHtml, writeStaticMirror } from "../src/export-static.mjs";

const OPER_CERTA_URL = "https://opercerta-kxh.netlify.app";

async function fixtureDirectory() {
  return await import("node:fs/promises").then(({ mkdtemp }) =>
    mkdtemp(path.join(os.tmpdir(), "portfolio-netlify-")),
  );
}

test("rejects HTML that omits the exact OperCerta link", async () => {
  const outputDirectory = await fixtureDirectory();
  await assert.rejects(
    () => assertRenderedHtml("<title>KXH</title>", outputDirectory),
    /OperCerta link/,
  );
});

test("writes HTML and verifies copied local assets", async () => {
  const root = await fixtureDirectory();
  const clientDirectory = path.join(root, "client");
  const outputDirectory = path.join(root, "dist");
  await mkdir(path.join(clientDirectory, "assets"), { recursive: true });
  await writeFile(path.join(clientDirectory, "assets", "app.js"), "export {};");
  const html = `<title>KXH — AI Agent / 大模型应用开发工程师</title><a href="${OPER_CERTA_URL}" target="_blank" rel="noreferrer">OperCerta</a><script src="/assets/app.js"></script>`;

  await writeStaticMirror({ clientDirectory, html, mirrorRoot: root, outputDirectory });

  const { access } = await import("node:fs/promises");
  await access(path.join(outputDirectory, "index.html"));
  await access(path.join(outputDirectory, "assets", "app.js"));
});
```

- [ ] **Step 3: Run the tests to prove RED**

Run:

```powershell
Set-Location D:\CODEX\resume\portfolio-netlify
npm test
```

Expected: failure during test-module loading because `../src/export-static.mjs` does not exist.

- [ ] **Step 4: Commit only the project skeleton and RED tests**

```powershell
git init
git add package.json .gitignore netlify.toml tests/export-static.test.mjs
git commit -m "test: define static mirror export contract"
```

### Task 2: Implement deterministic static export and GREEN tests

**Files:**
- Create: `D:\CODEX\resume\portfolio-netlify\src\export-static.mjs`
- Modify: `D:\CODEX\resume\portfolio-netlify\tests\export-static.test.mjs`

**Interfaces:**
- Consumes: `clientDirectory: string`, `html: string`, `mirrorRoot: string`, `outputDirectory: string`.
- Produces: `assertRenderedHtml(html, outputDirectory): Promise<void>` and `writeStaticMirror({ clientDirectory, html, outputDirectory }): Promise<void>`.
- Failure contract: throws an `Error` containing `OperCerta link`, `target=_blank`, `rel=noreferrer`, `asset missing`, or `unsafe output directory` for the corresponding violation.

- [ ] **Step 1: Add failure tests for unsafe output and missing copied assets**

```js
test("fails closed when a referenced local asset is absent", async () => {
  const outputDirectory = await fixtureDirectory();
  const html = `<title>KXH</title><a href="${OPER_CERTA_URL}" target="_blank" rel="noreferrer">OperCerta</a><script src="/assets/missing.js"></script>`;
  await assert.rejects(
    () => assertRenderedHtml(html, outputDirectory),
    /asset missing: \/assets\/missing\.js/,
  );
});

test("rejects an output directory outside the mirror root", async () => {
  const root = await fixtureDirectory();
  await assert.rejects(
    () => writeStaticMirror({ clientDirectory: root, html: "", mirrorRoot: root, outputDirectory: path.parse(root).root }),
    /unsafe output directory/,
  );
});
```

- [ ] **Step 2: Run the focused tests and confirm they fail for missing exports**

Run:

```powershell
npm test
```

Expected: failure because the two functions are not yet exported.

- [ ] **Step 3: Implement the validation and copy library**

```js
import { access, cp, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const OPER_CERTA_URL = "https://opercerta-kxh.netlify.app";
const localAssetPattern = /(?:src|href)=["'](\/[^"'#?]+)["']/gi;

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function requireInsideOutput(outputDirectory, candidate) {
  const resolvedOutput = path.resolve(outputDirectory);
  const resolvedCandidate = path.resolve(candidate);
  if (resolvedCandidate !== resolvedOutput && !resolvedCandidate.startsWith(`${resolvedOutput}${path.sep}`)) {
    throw new Error("unsafe output directory");
  }
  return resolvedCandidate;
}

export async function assertRenderedHtml(html, outputDirectory) {
  if (!html.includes(OPER_CERTA_URL) || !html.includes("OperCerta")) {
    throw new Error("OperCerta link is missing");
  }
  const anchor = new RegExp(`<a\\b(?=[^>]*href=["']${escapeRegExp(OPER_CERTA_URL)}["'])(?=[^>]*target=["']_blank["'])(?=[^>]*rel=["']noreferrer["'])[^>]*>`, "i");
  if (!anchor.test(html)) throw new Error("OperCerta link requires target=_blank and rel=noreferrer");

  const assets = new Set([...html.matchAll(localAssetPattern)].map((match) => match[1]));
  for (const asset of assets) {
    const target = requireInsideOutput(outputDirectory, path.join(outputDirectory, asset.slice(1)));
    try { await access(target); } catch { throw new Error(`asset missing: ${asset}`); }
  }
}

export async function writeStaticMirror({ clientDirectory, html, mirrorRoot, outputDirectory }) {
  const resolvedMirrorRoot = path.resolve(mirrorRoot);
  const resolvedOutput = path.resolve(outputDirectory);
  if (resolvedOutput !== path.join(resolvedMirrorRoot, "dist")) {
    throw new Error("unsafe output directory");
  }
  await rm(resolvedOutput, { recursive: true, force: true });
  await mkdir(resolvedOutput, { recursive: true });
  await cp(clientDirectory, resolvedOutput, { recursive: true });
  await writeFile(path.join(resolvedOutput, "index.html"), html, "utf8");
  await assertRenderedHtml(html, resolvedOutput);
}
```

- [ ] **Step 4: Run focused and full mirror tests to prove GREEN**

Run:

```powershell
npm test
```

Expected: all `export-static` tests pass with zero failures.

- [ ] **Step 5: Commit the export library and tests**

```powershell
git add src/export-static.mjs tests/export-static.test.mjs
git commit -m "feat: export validated portfolio static mirror"
```

### Task 3: Add the real Vinext build-and-render CLI, then verify the generated site

**Files:**
- Create: `D:\CODEX\resume\portfolio-netlify\scripts\export-static.mjs`
- Modify: `D:\CODEX\resume\portfolio-netlify\src\export-static.mjs`
- Modify: `D:\CODEX\resume\portfolio-netlify\tests\export-static.test.mjs`

**Interfaces:**
- Consumes: `PORTFOLIO_SOURCE_DIR` optional environment override; default source is `D:\CODEX\resume\portfolio` on this Windows workstation.
- Produces: `D:\CODEX\resume\portfolio-netlify\dist\index.html` and copied client files.
- Failure contract: missing `package.json`, missing `dist/server/index.js`, non-200/non-HTML SSR response, or unavailable Git Bash each exits nonzero before Netlify deployment.

- [ ] **Step 1: Extend the test import and add a failing renderer contract test**

```js
import { assertRenderedHtml, renderHome, writeStaticMirror } from "../src/export-static.mjs";

test("rejects a non-HTML SSR response", async () => {
  await assert.rejects(
    () => renderHome(async () => new Response("bad", { status: 500, headers: { "content-type": "text/plain" } })),
    /SSR response must be 200 HTML/,
  );
});
```

- [ ] **Step 2: Implement the renderer and Windows build runner**

```js
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

export async function renderHome(fetchPage) {
  const response = await fetchPage();
  if (response.status !== 200 || !/^text\/html\b/i.test(response.headers.get("content-type") ?? "")) {
    throw new Error("SSR response must be 200 HTML");
  }
  return await response.text();
}

export async function buildPortfolio(sourceDirectory) {
  const bash = "F:/Git/bin/bash.exe";
  if (process.platform === "win32" && !existsSync(bash)) {
    throw new Error(`required npm script shell is unavailable: ${bash}`);
  }
  await new Promise((resolve, reject) => {
    const child = spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "build"], {
      cwd: sourceDirectory,
      stdio: "inherit",
      env: { ...process.env, ...(process.platform === "win32" ? { npm_config_script_shell: bash } : {}) },
    });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`portfolio build failed: ${code}`)));
  });
}

export async function renderBuiltHome(serverEntry) {
  const entryUrl = pathToFileURL(serverEntry);
  entryUrl.searchParams.set("static-mirror", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(entryUrl.href);
  return await renderHome(() => worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  ));
}
```

- [ ] **Step 3: Implement the CLI orchestration**

```js
import path from "node:path";
import { fileURLToPath } from "node:url";
import { access } from "node:fs/promises";
import { buildPortfolio, renderBuiltHome, writeStaticMirror } from "../src/export-static.mjs";

const mirrorRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDirectory = path.resolve(process.env.PORTFOLIO_SOURCE_DIR ?? "D:/CODEX/resume/portfolio");
const serverEntry = path.join(sourceDirectory, "dist", "server", "index.js");
const clientDirectory = path.join(sourceDirectory, "dist", "client");

await access(path.join(sourceDirectory, "package.json"));
await buildPortfolio(sourceDirectory);
await access(serverEntry);
await access(clientDirectory);
const html = await renderBuiltHome(serverEntry);
await writeStaticMirror({ clientDirectory, html, mirrorRoot, outputDirectory: path.join(mirrorRoot, "dist") });
console.log(`static mirror written to ${path.join(mirrorRoot, "dist")}`);
```

- [ ] **Step 4: Run the real build/export and inspect its concrete output**

Run:

```powershell
Set-Location D:\CODEX\resume\portfolio-netlify
npm run verify
Get-Content -Raw dist\index.html
Get-ChildItem -Recurse -File dist\assets
```

Expected: `dist/index.html` has title `KXH — AI Agent / 大模型应用开发工程师`, the exact OperCerta URL, an external-link safety attribute pair, and every referenced `/assets/...` file exists.

- [ ] **Step 5: Commit the real exporter after local verification**

```powershell
git add src/export-static.mjs scripts/export-static.mjs tests/export-static.test.mjs
git commit -m "feat: render portfolio for static deployment"
```

### Task 4: Create the independent Netlify site and verify preview then production

**Files:**
- Modify: `D:\CODEX\resume\portfolio-netlify\netlify.toml` only if the CLI reports a configuration error.
- Create: `D:\CODEX\resume\portfolio-netlify\README.md`

**Interfaces:**
- Consumes: a validated local `dist` directory and authenticated Netlify CLI session.
- Produces: a new Netlify site URL distinct from `opercerta-kxh`, one preview deployment and one production deployment.
- Failure contract: deployment failure leaves the known-good OperCerta Netlify site untouched; do not claim the portfolio entry is public until HTTPS validation passes.

- [ ] **Step 1: Document exact local release commands and rollback**

```markdown
# Portfolio Netlify Static Mirror

Build and validate: `npm run verify`

Preview: `netlify deploy --dir dist --message "portfolio static mirror preview"`

Production: `netlify deploy --dir dist --prod --message "portfolio static mirror production"`

Rollback: deploy the previous verified `dist` artifact to this portfolio site. Do not deploy to `opercerta-kxh`.
```

- [ ] **Step 2: Verify authenticated CLI identity and create/link a new site**

Run from the already-configured Ubuntu/WSL Netlify CLI environment:

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/resume/portfolio-netlify && netlify status'
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/resume/portfolio-netlify && netlify sites:create --name kxh-agent-portfolio'
```

Expected: authenticated account information and a site ID/URL different from `opercerta-kxh`. If the requested name is unavailable, stop before creating any alternate site and report the CLI error for a deliberate name decision.

- [ ] **Step 3: Deploy a preview and validate public content**

Run:

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/resume/portfolio-netlify && netlify deploy --dir dist --message "portfolio static mirror preview"'
```

Then probe the exact preview URL printed by the CLI with `curl -fsSLI` and `curl -fsSL | grep -F "https://opercerta-kxh.netlify.app"` inside the same Ubuntu shell. Expected: HTTPS 200, HTML content type, portfolio title and exact OperCerta URL. Never invent or prefill a URL.

- [ ] **Step 4: Deploy production and repeat the checks**

Run:

```bash
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/CODEX/resume/portfolio-netlify && netlify deploy --dir dist --prod --message "portfolio static mirror production"'
```

Then probe the exact production URL printed by the CLI with `curl -fsSLI` and `curl -fsSL | grep -F "https://opercerta-kxh.netlify.app"` inside the same Ubuntu shell. Expected: production HTTPS 200. Use the browser once to confirm visual rendering and that the OperCerta card opens the separate static showcase in a new tab.

- [ ] **Step 5: Commit mirror-project release documentation**

```powershell
git add README.md netlify.toml
git commit -m "docs: document netlify mirror release"
```

### Task 5: Record factual evidence and update OperCerta handoff

**Files:**
- Modify: `docs/development-log/daily/2026-07-19.md`
- Modify: `docs/development-log/current-state.md`
- Modify: `docs/development-log/interview-casebook.md`
- Modify: `DOCUMENT_INDEX.md`
- Create: `docs/release-evidence/portfolio-netlify-static-mirror.md`

**Interfaces:**
- Consumes: actual Netlify preview/production output, final URL, deploy identifier, local test results and HTTPS probe results.
- Produces: traceable Chinese evidence that distinguishes platform deployment success from public accessibility.

- [ ] **Step 1: Add only observed facts to the daily log**

Record: Sites URL returned 403 from this network; static mirror generation command and exit code; Netlify preview/production URL and deployment ID; HTTP status, title/link verification time; no credentials.

- [ ] **Step 2: Create release evidence using this fixed structure**

```markdown
# 作品集 Netlify 静态镜像证据

## 范围与边界
仅提供公开作品集入口和 OperCerta 静态专题外链；不提供公开 API、数据库、MCP 或审批写入。

## 本地导出
记录 `npm run verify` 的实际输出和时间。

## Netlify 部署
记录实际站点 URL、preview/production 部署 ID、部署时间和发布提交。

## 公网验证
记录 HTTPS 状态、页面标题、OperCerta URL、资源响应与浏览器观察。

## 回退
说明如何重新部署上一份经验证的 `dist`，且不得影响 `opercerta-kxh`。

## 未完成范围
OperCerta release gate 仍为 `CLOSED`；公开交互后端、生产 IAM/SSO、设备场景、真实模型、自动部署和完整 E2E 未完成。
```

- [ ] **Step 3: Update the current-state and interview casebook**

Add the concrete lesson: a platform reports deployment success and still may be inaccessible from a real network due to Cloudflare/access policy; therefore verify the audience path with HTTPS and browser evidence, not deployment status alone.

- [ ] **Step 4: Run documentation integrity checks**

Run:

```powershell
Set-Location D:\CODEX\agent-portfolio\opercerta
git diff --check
rg -n -i "placeholder|待定|占位" docs\development-log docs\release-evidence DOCUMENT_INDEX.md
```

Expected: no whitespace errors and no placeholder text in new evidence. Any pre-existing result outside modified files must be reported separately, not silently removed.

- [ ] **Step 5: Commit only the factual OperCerta documentation changes**

```powershell
git add DOCUMENT_INDEX.md docs/development-log docs/release-evidence/portfolio-netlify-static-mirror.md
git commit -m "docs: record portfolio netlify mirror evidence"
```

## Final Verification Checklist

- [ ] `D:\CODEX\resume\portfolio-netlify\npm test` passes.
- [ ] `D:\CODEX\resume\portfolio-netlify\npm run export` succeeds from the same source used for the visual portfolio.
- [ ] Generated `dist/index.html` contains the exact OperCerta URL and safe external-link attributes.
- [ ] Every HTML-referenced local CSS/JS/image path exists under `dist`.
- [ ] Preview and production deploy to a new Netlify site, not `opercerta-kxh`.
- [ ] Production URL returns HTTPS 200 and is browser-accessible from the user path.
- [ ] Evidence records actual IDs/URLs/times and keeps the OperCerta release gate `CLOSED`.
