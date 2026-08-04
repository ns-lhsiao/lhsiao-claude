---
name: mf-cfw-playwright
description: >-
  Start the mf-cfw dev server in a worktree and run Playwright or Cypress
  validation against it. Two modes: (1) Cypress — RBAC-mocked, fast, runs
  directly against localhost:8014; (2) Playwright — headed real browser,
  optional real QA tenant via development-proxy. No webui/devbox stack needed
  for mode 1. Browser session reuses across invocations in the same conversation.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# mf-cfw Playwright / Cypress

Validate mf-cfw changes in a real browser. Two modes:

| Mode | What runs | RBAC | Login needed |
|------|-----------|------|--------------|
| **cypress** | `cypress run --headed` against `localhost:8014` | intercepted (fixture) | No |
| **playwright** | headless=false Chromium against dev-proxy or QA tenant | real | Yes |

Default mode: **cypress** (faster, self-contained).

Use **playwright** when: testing auth-gated behavior, verifying vs a real tenant,
or the change touches code outside what RBAC intercepts can cover.

---

## Prerequisites

### Cypress mode (mode 1)

Only the mf-cfw dev server is needed — no webui, no devbox, no proxy.

### Playwright mode (mode 2)

The mf-cfw dev server AND a proxy that routes to the dev server from a real
webui session. The simplest setup is the development-proxy pointing at a QA
tenant (no local webui build needed for the Angular shell).

Credentials: `~/.claude/skills/mf-cfw-playwright/.env`

```
NS_TEST_USERNAME=<email>
NS_TEST_PASSWORD=<password>
NS_QA_TENANT=<hostname>   # e.g. nsclienttw-auto.qa.boomskope.com
```

---

## Worktree resolution

All edits target a **worktree**, never the primary checkout.

Primary checkout: `/Users/lhsiao/ns/git/mf-cfw`
Worktrees live at: `/Users/lhsiao/ns/git/mf-cfw-<slug>`

If the worktree doesn't exist, error and ask for the slug. Never create it
inside the primary.

```bash
SLUG=<slug>
WORKTREE=/Users/lhsiao/ns/git/mf-cfw-$SLUG
[ -d "$WORKTREE" ] || { echo "ERROR: worktree $WORKTREE not found"; exit 1; }
cd "$WORKTREE"
git rev-parse --abbrev-ref HEAD   # confirm correct branch
```

---

## Step 1: Start the dev server

mf-cfw uses **yarn** and **craco**. Default port `8014`.

```bash
cd "$WORKTREE"
# link node_modules from primary (avoid reinstall)
[ -L node_modules ] || ln -s /Users/lhsiao/ns/git/mf-cfw/node_modules node_modules
PORT=8014 WDS_SOCKET_PORT=8014 FAST_REFRESH=false WDS_HOT=false \
  BROWSER=none yarn start:dev
```

Run in background. Wait for `webpack compiled successfully` in the output before
proceeding.

Port conflicts: if `8014` is busy, use `PORT=8015` (and update `CYPRESS_BASE_VISIT`
or the Playwright base URL accordingly).

```bash
lsof -ti :8014 && echo "Port busy"
```

---

## Step 2: Plan validation steps

Before writing any test code, produce a numbered validation plan from the
context (changed files, PR description, user request). Each step must include:

- **What** to verify (element, text, behavior)
- **Selector** or `data-testid` to target
- **Pass condition**

Present the plan to the user before executing.

---

## Step 3a: Cypress mode

### RBAC intercept pattern

mf-cfw Cypress tests mock RBAC via `cy.intercept` on:

```
GET **/api/v2/ui/auth/authorize/pagepermissions
  ?parentpagename=Security Cloud Platform
  &pagename=<PAGE>
  &privilegename=settings
```

Standard header-driven fixture routing (copy from existing tests):

```ts
cy.intercept(rbacPermissionMockRequest, (req) => {
  if (req.headers['cy-rbac-mock-return'] === 'rw') {
    req.reply({ fixture: '<page>/get-rbac-read-write-response.json' });
  } else if (req.headers['cy-rbac-mock-return'] === 'r') {
    req.reply({ fixture: '<page>/get-rbac-read-response.json' });
  } else {
    req.reply({ fixture: '<page>/get-rbac-none-response.json' });
  }
}).as('getPageRbac');
```

RBAC fixture shapes — copy from `cypress/fixtures/socks-proxy/`:
- `get-rbac-read-write-response.json`
- `get-rbac-read-response.json`
- `get-rbac-none-response.json`

### rbac remoteEntry stub (global, already in `support/e2e.ts`)

The global `beforeEach` in `cypress/support/e2e.ts` already stubs
`**/mf/rbac/remoteEntry.js`. No per-test setup needed.

### Visit pattern

```ts
const BASE = Cypress.env('BASE_VISIT') || 'localhost:8014';
cy.visit(`${BASE}/#/<route>`);
// e.g. cy.visit(`${BASE}/#/settings/dns-security`);
```

### Run Cypress

```bash
cd "$WORKTREE"
# Cypress is in node_modules (via symlink from primary — verify first)
CYPRESS_BASE_VISIT=http://localhost:8014 \
  ./node_modules/.bin/cypress run --headed --spec "cypress/e2e/<spec>.cy.ts"

# Or open interactive runner:
./node_modules/.bin/cypress open
```

Capture screenshots: Cypress auto-saves on failure to `cypress/screenshots/`.

---

## Step 3b: Playwright mode

### Browser session reuse

Do NOT launch a new browser each invocation. Reuse via WebSocket endpoint file.

```js
const fs = require('fs');
const { chromium } = require('playwright');
const WS_FILE = '/tmp/pw-cfw-session-endpoint.txt';

let browser;
if (fs.existsSync(WS_FILE)) {
  const wsEndpoint = fs.readFileSync(WS_FILE, 'utf-8').trim();
  try {
    browser = await chromium.connect(wsEndpoint);
    await browser.contexts();  // verify alive
  } catch {
    browser = null;
    fs.unlinkSync(WS_FILE);
  }
}

if (!browser) {
  const server = await chromium.launchServer({
    channel: 'chrome',
    headless: false,
    args: ['--no-sandbox'],
  });
  fs.writeFileSync(WS_FILE, server.wsEndpoint());
  browser = await chromium.connect(server.wsEndpoint());
}

// Reuse or create context
const contexts = browser.contexts();
let context, page;
if (contexts.length > 0 && contexts[0].pages().length > 0) {
  context = contexts[0];
  page = context.pages()[0];
} else {
  context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  page = await context.newPage();
}
```

Endpoint file: `/tmp/pw-cfw-session-endpoint.txt` (distinct from mf-client's
`/tmp/pw-session-endpoint.txt` so sessions don't collide).

### Two base-URL options

**Option A — mf-cfw standalone (no webui shell)**

mf-cfw exposes a standalone React app at `http://localhost:8014`. Visit it
directly. RBAC mock: inject `cy.intercept`-equivalent via `page.route()`:

```js
await page.route(
  '**/api/v2/ui/auth/authorize/pagepermissions**',
  (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ permissions: ['read', 'write'] }),
  })
);
await page.goto('http://localhost:8014/#/settings/dns-security');
```

**Option B — real QA tenant via development-proxy**

Requires `development-proxy` pointing at a QA tenant (no local webui build).
The proxy forwards `/ns`, `/api`, `/UI_Layer` to the QA tenant.

```bash
cd /Users/lhsiao/ns/git/development-proxy
# Edit src/config.ts fallbackServer.host to NS_QA_TENANT
npm run dev   # port 9797
```

Login flow (webui hash routing, same as mf-client):

```js
await page.goto('http://localhost:9797/locallogin');
await page.waitForSelector('#username', { timeout: 15000 });
await page.fill('#username', process.env.NS_TEST_USERNAME);
await page.fill('#password', process.env.NS_TEST_PASSWORD);
await page.click('#btn-sign-in');
await page.waitForFunction(
  () => !window.location.hash.includes('/login'),
  { timeout: 30000 }
);
const skip = page.locator('text=skip this step');
if (await skip.isVisible({ timeout: 5000 }).catch(() => false)) {
  await skip.click();
  await page.waitForTimeout(3000);
}
```

SPA navigation (hash routing — do NOT use `page.goto()` after login):

```js
await page.evaluate(() => {
  window.location.hash = '#/settings/dns-security';
});
```

mf-cfw MFE load readiness: wait for the topbar title or a known `data-testid`:

```js
await page.waitForSelector('[data-testid="topbar-title"]', { timeout: 60000 });
```

### Install Playwright (if not installed)

```bash
mkdir -p /tmp/pw-runner && cd /tmp/pw-runner
npm init -y && npm install playwright
```

Run scripts from `/tmp/pw-runner`.

### Step template

```js
const results = [];

// Step N: <description>
console.log('Step N: ...');
try {
  // assert
  const el = await page.locator('[data-testid="..."]').count();
  const passed = el > 0;
  console.log(passed ? 'PASS' : 'FAIL', '— Step N');
  results.push({ step: N, desc: '...', passed });
} catch (e) {
  console.log('FAIL — Step N:', e.message);
  results.push({ step: N, desc: '...', passed: false });
}
await page.screenshot({ path: '/tmp/pw-cfw-step-N.png' });

// Summary
console.log('\n--- Validation Summary ---');
results.forEach(r => console.log(r.passed ? 'PASS' : 'FAIL', `Step ${r.step}: ${r.desc}`));
const allPassed = results.every(r => r.passed);
if (!allPassed) await page.pause();
// Do NOT call browser.close() — leave session alive for reuse
```

---

## Step 4: Report results

1. Read console output for PASS/FAIL lines.
2. For FAIL steps, read screenshot files.
3. Present summary: passed/failed, screenshots, suggested next actions.

---

## DNS Security specifics (ENG-1118301)

Route: `#/settings/dns-security`
Page object class to create: `cypress/pages/dns-security.page.cy.ts`

Key `data-testid` targets (add as you build the UI in ENG-1118307):
- `[data-testid="topbar-title"]` — page title "DNS Security"
- `[data-testid="unauthorized-page"] h1` — RBAC blocked state

RBAC pagepermissions request params:
```ts
{
  parentpagename: 'Security Cloud Platform',
  pagename: 'DNS Security',       // matches ms-rbac displayName
  privilegename: 'settings',
}
```

Fixture directory to create: `cypress/fixtures/dns-security/`
Copy and adapt from `cypress/fixtures/socks-proxy/`.

---

## Cleanup

```bash
# Kill dev server for this worktree
lsof -ti :8014 | xargs kill -9 2>/dev/null

# Kill Playwright browser server
pkill -f "pw-runner" 2>/dev/null
rm -f /tmp/pw-cfw-session-endpoint.txt
```

---

## Key differences from mf-client-playwright

| Aspect | mf-client | mf-cfw |
|--------|-----------|--------|
| Package manager | npm | **yarn** |
| Dev server | `npm run start:dev` port 8017 | `yarn start:dev` port **8014** |
| Framework | CRA + webpack | CRA + **craco** |
| E2e tool | Playwright (external) | **Cypress** (in devDeps) |
| RBAC | real (via devbox stack) | **intercepted fixture** |
| Webui/devbox stack | required for Option B | **optional** (standalone mode works) |
| Session endpoint file | `/tmp/pw-session-endpoint.txt` | `/tmp/pw-cfw-session-endpoint.txt` |
| Node_modules symlink | primary `mf-client/node_modules` | primary `mf-cfw/node_modules` |
