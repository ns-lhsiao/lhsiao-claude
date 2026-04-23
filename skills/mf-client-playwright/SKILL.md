---
name: mf-client-playwright
description: >-
  Launch a Playwright browser against the local dev proxy, auto-login with
  default credentials, and leave the browser open for manual testing.
  Assumes init-dev-env is already running.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# mf-client Playwright

Open a Playwright browser pointed at the local development proxy and log in
automatically so the user can begin manual testing immediately.

## Prerequisites

The `init-dev-env` skill (or equivalent) must already be running:
- webui watch build
- mf-client dev server on `:8017`
- development proxy on `:9797`

## Credentials

Credentials are stored in a `.env` file **next to this SKILL.md** — that file is
NOT tracked in git. Read them at runtime:

```
/Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

Format:
```
NS_TEST_USERNAME=<email>
NS_TEST_PASSWORD=<password>
```

Parse both values before launching the browser.

## Steps

### 1. Read credentials

```bash
source /Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

Store `NS_TEST_USERNAME` and `NS_TEST_PASSWORD` for use in the Playwright script.

### 2. Launch Playwright and log in

Run an inline Node.js script from `/tmp/pw-runner` (install playwright there if
needed — see Notes) that:

1. Launches **real Chrome** (`channel: 'chrome'`) in **headed** mode
   (`headless: false`) with `--no-sandbox`.
   - **Do NOT use default Chromium** — the webui returns "Browser Not Supported".
2. Creates a context with viewport `1920 x 1080`.
3. Navigates to `http://localhost:9797/locallogin`.
4. Waits for `#username` selector to appear.
5. Fills `#username` with the username from `.env`.
6. Fills `#password` with the password from `.env`.
7. Clicks `#btn-sign-in`.
8. **Waits for login to complete** using:
   ```js
   await page.waitForFunction(
     () => !window.location.hash.includes('/login'),
     { timeout: 30000 }
   );
   ```
   Do NOT use a fixed `waitForTimeout` — login takes variable time.
9. **Dismisses the welcome wizard** if present (fresh/unconfigured tenants):
   ```js
   const skipLink = page.locator('text=skip this step');
   if (await skipLink.isVisible({ timeout: 5000 }).catch(() => false)) {
     await skipLink.click();
     await page.waitForTimeout(3000);
   }
   ```
10. **Navigates to the target page** via hash assignment (preserves session,
    avoids full reload):
    ```js
    await page.evaluate(() => {
      window.location.hash = '#/settings/device-management';
    });
    ```
    Do NOT use `page.goto()` for hash-only navigation — it triggers a full
    page reload which can lose session cookies and forces the mf-client
    micro-frontend to re-bootstrap (30–60 s).
11. **Pauses** the browser (`page.pause()`) so the user can interact manually.

If the user provides a target URL or hash route in the skill arguments, use that
instead of the default `#/settings/device-management`.

Example inline script (run via `node -e`):

```bash
NS_TEST_USERNAME="$NS_TEST_USERNAME" NS_TEST_PASSWORD="$NS_TEST_PASSWORD" \
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({
    headless: false,
    channel: 'chrome',
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();

  // Login
  await page.goto('http://localhost:9797/locallogin');
  await page.waitForSelector('#username', { timeout: 15000 });
  await page.fill('#username', process.env.NS_TEST_USERNAME);
  await page.fill('#password', process.env.NS_TEST_PASSWORD);
  await page.click('#btn-sign-in');
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

  // Navigate via hash (no reload, preserves session)
  await page.evaluate(() => {
    window.location.hash = '#/settings/device-management';
  });

  console.log('Logged in — browser is open. Close it or press Ctrl+C to exit.');
  await page.pause();
})();
"
```

**Important:** Run this command in the background so the Claude session is not
blocked. The browser stays open until the user closes it or presses Ctrl+C.

### 3. Output summary

```
Playwright browser launched!

  URL       : http://localhost:9797/ns#/settings/device-management
  Username  : <NS_TEST_USERNAME>
  Viewport  : 1920 x 1080

The browser is open and logged in. Close the browser window or press Ctrl+C to stop.
```

## Notes

- Playwright must be installed in a throwaway directory — it is NOT in
  mf-client's node_modules:
  ```bash
  mkdir -p /tmp/pw-runner && cd /tmp/pw-runner && npm init -y && npm install playwright
  ```
  Then run all scripts from `/tmp/pw-runner`.
- If Playwright browsers are not installed, run `npx playwright install chromium`
  before the script.
- The `.env` file must NEVER be committed to git. It is excluded by the
  deny-by-default `.gitignore` in `~/.claude/`.
