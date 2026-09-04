---
name: cdp-sidecar-screenshots
description: >-
  Screenshot a PR sidecar page in a real headed Chrome via CDP -- lights up any
  page on a routed tenant (x-npe-env header) the way headless Playwright cannot,
  and drives toast position verification (sonner mutation-error/success toasts).
  Use when you need proof-of-render screenshots of a sidecar branch's pages/toast
  positions, or when headless Playwright with context headers fails with a
  post-login "session configuration" server error or a stuck LOADING screen.
  Proves the playbook from a webui2 (ngweb-v2) toast-verification spike; adapt
  the per-page selectors and navigation as needed.
---

# CDP + real Chrome screenshots of PR sidecar pages (toast position check)

A proven method (spike product) turned into a reusable recipe. The hard-won
pitfalls are below so a future PR verification run does not re-burn them.

## Why this exists

- Verifying a PR sidecar (`<service>-npe-pr-<num>`) on a routed tenant
  needs a **real browser** plus the `x-npe-env` header.
- **Headless Playwright + `extraHTTPHeaders` fails**: after the shell login it
  hits a `server-error "session configuration"` (headless fingerprint / session
  bootstrap is blocked).
- **Headless hash-goto to a page MFE stalls on LOADING**: Angular has not fully
  booted, page data never loads.
- Fix: **real (headed) Chrome + CDP attach + `Network.setExtraHTTPHeaders`
  (session-level, NOT context header) + full-page-reload navigation** (not
  `location.hash`).

## Prerequisites

1. A Chrome with a debug port, logged into the routed tenant:
   ```bash
   pkill -f "Google Chrome"
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --remote-debugging-port=${CDP_PORT:-9222} --user-data-dir=/tmp/chrome-debug-profile \
     --no-first-run --no-default-browser-check \
     "${BASE:-https://<tenant>.qa.boomskope.com}" &
   curl -s "localhost:${CDP_PORT:-9222}/json/version"   # confirm CDP is up
   ```
   (Or use a ModHeader extension to carry the header manually; CDP injection is
   more automatic.)
2. Tenant credentials. Read them at runtime from `~/.claude/tenants.json`
   (example key: `tiger-team-automation4`) or
   `~/.claude/connections/<name>.json` -- never paste a password into this
   skill or the repo.
3. Node with `@playwright/test` resolvable. The skill **ships** scripts that
   `require('@playwright/test')`; in a repo checkout that has Playwright
   installed (e.g. webui2), this resolves from
   `node_modules/.pnpm/@playwright+test@*/node_modules` (set
   `NODE_PATH=$(pnpm dir -r ...)/@playwright+test@*/node_modules`, or run from a
   dir that has Playwright installed). There is no npm install here -- the
   scripts are run from inside a repo that already has Playwright.

## Where the scripts live

The skill installs to `~/.claude/skills/cdp-sidecar-screenshots/` (user-level)
or `<project>/.claude/skills/cdp-sidecar-screenshots/` (project-level). Resolve
the script directory **once at the start of the session**, then reuse it:

```bash
SKILL_DIR=$(ls -d \
  ~/.claude/skills/cdp-sidecar-screenshots \
  .claude/skills/cdp-sidecar-screenshots \
  2>/dev/null | head -1)
[ -z "$SKILL_DIR" ] && { echo "cdp-sidecar-screenshots not installed"; exit 1; }
TOAST_LIB="$SKILL_DIR/scripts/cdp_toast_lib.js"
```

`TOAST_LIB` is what the example pages `require()` as `process.env.TOAST_LIB`.

## Config (env var based -- nothing machine-specific hardcoded)

| Env | Meaning | Default |
|---|---|---|
| `BASE` | tenant origin, e.g. `https://tiger-team-automation4.qa.boomskope.com` | (required) |
| `X_NPE_ENV` | sidecar routing header value, e.g. `npe-pr-2021` | (required) |
| `SHOTS` | screenshot output dir (mkdir it first) | (required) |
| `CDP_URL` | CDP endpoint | `http://localhost:9222` |
| `CDP_PORT` | debug port; only used when `CDP_URL` is unset | `9222` |
| `TU` / `TP` | tenant username / password (login flow) | (required only if login) |

## Core steps (each screenshot run)

1. **attach** — `chromium.connectOverCDP('http://localhost:9222')`
2. **header** — `session = await ctx.newCDPSession(page)`; `Network.enable`; `Network.setExtraHTTPHeaders({headers: {'x-npe-env': 'npe-pr-2021'}})`
3. **goto target directly** — `page.goto('${BASE}/ns#/ROUTE', {waitUntil:'domcontentloaded'})` — full reload, NOT `location.hash` (unreliable after MFE remount)
4. **wait for page content** — poll until `/LOADING/i` disappears and body length passes sidebar length (12s+ typical)
5. **trigger the toast** — per-page action (create/delete/save) with the mutation API intercepted to 400
6. **screenshot** — `page.screenshot({path, fullPage})`

## Toast capture + position classification

Sonner toast visual elements are **classless `<li>`s**. Capture: poll innerText
for the default toast keywords and `w<500` with `getBoundingClientRect` (see
`DEFAULT_TOAST_RE` in `scripts/cdp_toast_lib.js`; pass a narrower `re` to pin
down success vs. error toasts).

Classification: `cx = x + w/2`; zoneX = left/center/right by `innerWidth`
thirds; zoneY = top (`<0.2h`) / bottom (`>0.8h`) / middle. Example rect
`{x:820,y:891}` on a 1200x900 viewport = **bottom-right**.

**Mutation interception**: CDP `Fetch.enable` + pattern `*policy/urllist*` (or
the page's API), method POST/PUT/DELETE, then `Fetch.fulfillRequest` 400 with
`{"validation_errors":[{"field":"name","error":"forced"}]}`. url-list's unified
`onError` needs the `validation_errors` shape to show a mutation-error toast; a
plain `{"message":"..."}` body is swallowed and nothing displays.

## Pitfalls (burned once each)

| Pitfall | Result | Fix |
|---|---|---|
| headless Playwright + context header | post-login server-error "session configuration" | real Chrome + CDP setExtraHTTPHeaders |
| direct hash-goto `#/target` | main content stuck on "LOADING..." (data API 200 but UI does not switch) | goto `/ns` then UI-click navigation |
| `page.fill` too early on login | timeout if login input not yet mounted (~5.5s mount) | `waitFor` visible + state visible, 60s |
| screenshot too early | only splash/LOGO captured | wait until `document.body.innerText` drops LOADING and length exceeds sidebar |
| toast selector by class | sonner toast is a classless `<li>`; class "toast" lives only on the container | poll innerText match + rect (`w<500`) and classify position |
| `location.hash` navigation | MFE remount lands on wrong Angular page | `page.goto('${BASE}/ns#/ROUTE')` full reload instead |
| Fetch interception with `{"message":"..."}` | mutationError not triggered (showValidationErrorToast looks for validation_errors) | body uses `{"validation_errors":[{"field":"name","error":"forced"}]}` |

## Verify the sidecar is actually live

```
in-browser fetch /mf/shell/build-info.json
with header  -> {"service":"webui2","version":"dev","commit":"unknown"}
without      -> {"service":"webui2","version":"1.0.0-1770-rc","commit":"5340cbc", ...}
```

## Per-session start

1. Start the debug Chrome (above), logged into the routed tenant.
2. Settle env (`BASE`, `X_NPE_ENV`, `SHOTS`, `TU`/`TP` from `~/.claude/tenants.json`) and
   `node "$SKILL_DIR/scripts/cdp_login.js"` for a fresh profile -- it is a thin
   wrapper over the lib's shared login flow.
3. Run the example page flow or your adapted per-page script; record per page:
   the triggering action, the toast text, and its position.
