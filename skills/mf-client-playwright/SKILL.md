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

Run an inline Node.js script via `npx playwright` that:

1. Launches Chromium in **headed** mode (`headless: false`) with `--no-sandbox`.
2. Sets viewport to `1920 x 1080`.
3. Navigates to `http://localhost:9797/locallogin`.
4. Waits for the login form to appear.
5. Fills `#username` with the username from `.env`.
6. Fills `#password` with the password from `.env`.
7. Clicks `#btn-sign-in`.
8. Waits for navigation to complete (URL should contain `#/dashboard` or similar).
9. **Pauses** the browser (`page.pause()`) so the user can interact manually.

Example inline script (run via `node -e`):

```bash
NS_TEST_USERNAME="$NS_TEST_USERNAME" NS_TEST_PASSWORD="$NS_TEST_PASSWORD" \
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: false, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  await page.goto('http://localhost:9797/locallogin');
  await page.waitForSelector('#username');
  await page.fill('#username', process.env.NS_TEST_USERNAME);
  await page.fill('#password', process.env.NS_TEST_PASSWORD);
  await page.click('#btn-sign-in');
  await page.waitForURL(/.*#\\/.*/, { timeout: 30000 });

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

  URL       : http://localhost:9797/locallogin
  Username  : <NS_TEST_USERNAME>
  Viewport  : 1920 x 1080

The browser is open and logged in. Close the browser window or press Ctrl+C to stop.
```

## Notes

- If Playwright browsers are not installed, run `npx playwright install chromium`
  before the script.
- The `.env` file must NEVER be committed to git. It is excluded by the
  deny-by-default `.gitignore` in `~/.claude/`.
