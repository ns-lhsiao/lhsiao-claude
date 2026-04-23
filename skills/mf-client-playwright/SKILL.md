---
name: mf-client-playwright
description: >-
  Plan and execute automated Playwright validation against the local dev proxy.
  Builds a test plan from the context, runs assertions in a headed browser,
  screenshots each step, and reports pass/fail. Falls back to manual pause on
  failure. Assumes init-dev-env is already running. Reuses a persistent browser
  session across invocations within the same conversation.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# mf-client Playwright

Automated visual validation of mf-client changes in a real browser against the
local development proxy.

## Prerequisites

The `init-dev-env` skill (or equivalent) must already be running:
- webui watch build
- mf-client dev server on `:8017`
- development proxy on `:9797`

## Credentials

Stored in a `.env` file **next to this SKILL.md** (NOT tracked in git):

```
/Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

Format:
```
NS_TEST_USERNAME=<email>
NS_TEST_PASSWORD=<password>
```

---

## Browser Session Reuse

**CRITICAL:** Do NOT launch a new browser on every invocation. Reuse an existing
browser session within the same conversation to avoid accumulating orphaned
Chrome windows.

### How it works

The Playwright script connects to a **persistent browser server** via WebSocket.
On first invocation, the script launches a `browserServer` and writes its
WebSocket endpoint to a well-known file. On subsequent invocations, the script
reads the endpoint file and connects to the existing server.

**Endpoint file:** `/tmp/pw-session-endpoint.txt`

#### First invocation (launch + persist)

```js
const fs = require('fs');
const WS_FILE = '/tmp/pw-session-endpoint.txt';

let browser;
if (fs.existsSync(WS_FILE)) {
  const wsEndpoint = fs.readFileSync(WS_FILE, 'utf-8').trim();
  try {
    browser = await chromium.connect(wsEndpoint);
    // Verify connection is alive
    await browser.contexts();
  } catch {
    // Stale endpoint — launch fresh
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
```

#### Reuse existing page or create new one

```js
const contexts = browser.contexts();
let context, page;
if (contexts.length > 0 && contexts[0].pages().length > 0) {
  context = contexts[0];
  page = context.pages()[0];
  console.log('Reusing existing browser session:', page.url());
} else {
  context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  page = await context.newPage();
  console.log('Created new browser context');
}
```

#### Login only if needed

```js
const currentUrl = page.url();
const needsLogin = currentUrl === 'about:blank'
  || currentUrl.includes('/login')
  || currentUrl.includes('/locallogin');

if (needsLogin) {
  // ... full login flow (see Login section below)
}
```

### Cleanup

When the user is done with the session (explicitly asks to close, or the
conversation ends), kill the browser server:

```bash
# Kill any existing Playwright browser server
PW_PID=$(lsof -i :0 -c chrome 2>/dev/null | head -1 | awk '{print $2}')
pkill -f "pw-runner" 2>/dev/null
rm -f /tmp/pw-session-endpoint.txt
```

Or from within the script: `await browser.close()`.

---

## Steps

### 1. Plan Validation Steps

Before writing any Playwright code, analyze the context (changed files, bug
description, user instructions) and produce a **numbered validation plan** in
prose. Present it to the user before executing. Example:

```
Playwright Validation Plan:

1. Login and navigate to Settings > Device Management
2. Wait for the Devices table to render with data
3. Verify Device Classification column shows tags (selector: .ps-tag)
4. Verify "View All" appears when tag text is truncated (selector: [data-testid="column-device-tags-view-all"])
5. Click "View All" and verify the popover renders all tags
6. Screenshot each step for evidence
```

Each step should include:
- **What** to check (element, behavior, text content)
- **Selector** or locator to use
- **Pass condition** (element visible, text matches, count > N, class present, etc.)

### 2. Read Credentials

```bash
source /Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

### 3. Generate and Run Playwright Script

Build a single inline `node -e` script that implements every step from the plan.
The script must follow these patterns:

#### Browser Session (mandatory — use reuse pattern above)

Always attempt to connect to an existing session first. Only launch a new
browser server if no session exists or the existing one is stale.

#### Login (only if needed)

```js
if (needsLogin) {
  await page.goto('http://localhost:9797/locallogin');
  await page.waitForSelector('#username', { timeout: 15000 });
  await page.fill('#username', process.env.NS_TEST_USERNAME);
  await page.fill('#password', process.env.NS_TEST_PASSWORD);
  await page.click('#btn-sign-in');

  // Wait for login to ACTUALLY complete — do NOT use fixed timeout
  await page.waitForFunction(
    () => !window.location.hash.includes('/login'),
    { timeout: 30000 }
  );

  // Dismiss welcome wizard if present
  const skipLink = page.locator('text=skip this step');
  if (await skipLink.isVisible({ timeout: 5000 }).catch(() => false)) {
    await skipLink.click();
    await page.waitForTimeout(3000);
  }
}
```

#### SPA Navigation (mandatory pattern)

**Use hash assignment, NOT `page.goto()`** for navigating within the SPA.
`page.goto()` triggers a full reload which loses session cookies and forces
the micro-frontend to re-bootstrap (30–60 s).

```js
await page.evaluate(() => {
  window.location.hash = '#/settings/device-management';
});
```

#### Wait for Micro-Frontend (mandatory)

The mf-client micro-frontend loads via module federation and takes 30–60 s.
Wait for a known element as a readiness signal:

```js
await page.waitForSelector(
  '[data-testid="filter-toggle-advanced"]',
  { timeout: 60000 }
);
```

#### Validation Steps (from the plan)

For each planned step, follow this pattern:

```js
// Step N: <description from plan>
console.log('Step N: <description>...');
try {
  // Perform action / assert condition
  const count = await page.locator('.ps-tag').count();
  const passed = count > 0;
  console.log(passed ? 'PASS' : 'FAIL', '— Step N:', '<description>', `(found ${count})`);
  results.push({ step: N, desc: '<description>', passed });
} catch (e) {
  console.log('FAIL — Step N:', '<description>', e.message);
  results.push({ step: N, desc: '<description>', passed: false });
}
await page.screenshot({ path: '/tmp/pw-step-N.png' });
```

#### Summary and Fallback (mandatory)

At the end, print a summary table. **Do NOT close the browser** — leave it
running for potential reuse. Only pause on failure:

```js
// Summary
console.log('\n--- Validation Summary ---');
results.forEach(r => {
  console.log(r.passed ? 'PASS' : 'FAIL', `Step ${r.step}: ${r.desc}`);
});
const allPassed = results.every(r => r.passed);
console.log(allPassed ? '\nAll steps passed!' : '\nSome steps failed.');

if (!allPassed) {
  console.log('Browser paused for manual inspection.');
  await page.pause();
}
// NOTE: do NOT call browser.close() — leave session alive for reuse
```

### 4. Report Results

After the script completes:

1. Read the console output for PASS/FAIL results.
2. Read the screenshot files (`/tmp/pw-step-N.png`) for any FAIL steps.
3. Present a summary to the user:
   - Which steps passed/failed
   - Screenshots of failures
   - Suggested next actions if failures occurred

---

## Runtime Notes

- **Install Playwright** in a throwaway directory (not in mf-client's node_modules):
  ```bash
  mkdir -p /tmp/pw-runner && cd /tmp/pw-runner && npm init -y && npm install playwright
  ```
  Run all scripts from `/tmp/pw-runner`.
- Run the script **in the background** so the Claude session is not blocked.
- The `.env` file must NEVER be committed to git.
- If the user provides a target hash route in the skill arguments, use that
  instead of the default `#/settings/device-management`.
- **Before launching**, kill any orphaned Playwright processes from previous
  sessions that may not have cleaned up:
  ```bash
  pkill -f "pw-runner" 2>/dev/null
  ```
  But do NOT kill if the endpoint file exists and the connection succeeds —
  that's a live session to reuse.
