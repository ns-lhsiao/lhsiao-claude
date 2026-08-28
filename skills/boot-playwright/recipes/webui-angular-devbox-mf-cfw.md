# Recipe: webui-angular-devbox-mf-cfw

Two modes:

| Mode | What runs | RBAC | Devbox needed? |
|------|-----------|------|-----------------|
| **cypress** | `cypress run --headed` against `localhost:8014` | intercepted (fixture) | No |
| **playwright** | `playwright-cli` session against dev-proxy or QA tenant | real | Only for QA-tenant-via-proxy option |

Default mode: **cypress** (faster, self-contained, no devbox dependency).

Use **playwright** when: testing auth-gated behavior, verifying against a real
tenant, or the change touches code outside what RBAC intercepts can cover.

**Only for Playwright mode's QA-tenant-via-proxy option** — read
`webui-angular-devbox.md` first and bring up the base devbox-ui stack. Cypress mode
and Playwright's standalone mode need none of that.

Read `../SKILL.md` first for the shared session/login/nav/reporting mechanics
(Playwright mode only — Cypress mode doesn't use `playwright-cli`).

## Prerequisites

### Cypress mode

Only the mf-cfw dev server is needed.

### Playwright mode

The mf-cfw dev server, plus (for the QA-tenant option) a development-proxy
pointing at a QA tenant.

Credentials: `~/.claude/skills/mf-cfw-playwright/.env`

```
NS_TEST_USERNAME=<email>
NS_TEST_PASSWORD=<password>
NS_QA_TENANT=<hostname>   # e.g. nsclienttw-auto.qa.boomskope.com
```

## Resolve the worktree

Primary checkout: `/Users/lhsiao/ns/git/mf-cfw`. Worktree:
`/Users/lhsiao/ns/git/mf-cfw-<slug>`. If it doesn't exist, error and ask for the
slug — never create it inside the primary.

```bash
SLUG=<slug>
WORKTREE=/Users/lhsiao/ns/git/mf-cfw-$SLUG
[ -d "$WORKTREE" ] || { echo "ERROR: worktree $WORKTREE not found"; exit 1; }
cd "$WORKTREE" && git rev-parse --abbrev-ref HEAD
```

## Start the dev server

mf-cfw uses **yarn** and **craco**. Default port `8014`.

```bash
cd "$WORKTREE"
[ -L node_modules ] || ln -s /Users/lhsiao/ns/git/mf-cfw/node_modules node_modules
PORT=8014 WDS_SOCKET_PORT=8014 FAST_REFRESH=false WDS_HOT=false \
  BROWSER=none yarn start:dev
```

Run in background; wait for `webpack compiled successfully`. If `8014` is busy,
use `PORT=8015` and update the base URL used below accordingly:

```bash
lsof -ti :8014 && echo "Port busy"
```

## Plan validation steps

Per `../SKILL.md`'s validation-plan format — numbered, each with what/selector/pass
condition — before writing any automation.

## Cypress mode

### RBAC intercept pattern

```
GET **/api/v2/ui/auth/authorize/pagepermissions
  ?parentpagename=Security Cloud Platform
  &pagename=<PAGE>
  &privilegename=settings
```

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

Fixture shapes — copy from `cypress/fixtures/socks-proxy/`:
`get-rbac-read-write-response.json`, `get-rbac-read-response.json`,
`get-rbac-none-response.json`.

The global `beforeEach` in `cypress/support/e2e.ts` already stubs
`**/mf/rbac/remoteEntry.js` — no per-test setup needed.

### Visit pattern

```ts
const BASE = Cypress.env('BASE_VISIT') || 'localhost:8014';
cy.visit(`${BASE}/#/<route>`);
```

### Run

```bash
cd "$WORKTREE"
CYPRESS_BASE_VISIT=http://localhost:8014 \
  ./node_modules/.bin/cypress run --headed --spec "cypress/e2e/<spec>.cy.ts"
# or: ./node_modules/.bin/cypress open
```

Screenshots auto-save on failure to `cypress/screenshots/`.

## Playwright mode

### Option A — mf-cfw standalone (no webui shell)

```bash
playwright-cli -s=<slug> route '**/api/v2/ui/auth/authorize/pagepermissions**' \
  --status 200 --content-type application/json \
  --body '{"permissions":["read","write"]}'
playwright-cli -s=<slug> open http://localhost:8014/#/<route>
```

### Option B — real QA tenant via development-proxy

Requires the base recipe's devbox stack (only if you also need the webui shell)
or, more commonly, just development-proxy pointed at a QA tenant directly (no
local webui build needed for standalone mf-cfw validation):

```bash
cd /Users/lhsiao/ns/git/development-proxy
# edit src/config.ts fallbackServer.host to NS_QA_TENANT
npm run dev   # port 9797, run in background
```

Login flow, hash navigation, and MFE-readiness wait follow `../SKILL.md` exactly.
mf-cfw's readiness signal:

```bash
playwright-cli -s=<slug> eval "() => !!document.querySelector('[data-testid=\"topbar-title\"]')"
```

## Report results

Per `../SKILL.md`'s reporting format: PASS/FAIL per step + screenshot, summary
table, never close the session.

## Cleanup

```bash
lsof -ti :8014 | xargs kill -9 2>/dev/null
playwright-cli -s=<slug> close   # only if the user is done with the session
```

## Key differences from webui-angular-devbox-mf-client

| Aspect | mf-client | mf-cfw |
|--------|-----------|--------|
| Package manager | npm | **yarn** |
| Dev server | `npm run start:dev` port 8017+offset | `yarn start:dev` port **8014** |
| Framework | CRA + webpack | CRA + **craco** |
| E2e tool | Playwright only | Playwright **or Cypress** (in devDeps) |
| RBAC | real (via devbox stack) | **intercepted fixture** (Cypress) or real (Playwright) |
| Devbox stack | required | **optional** — only for Playwright's QA-tenant option |
| Node_modules symlink | primary `mf-client/node_modules` | primary `mf-cfw/node_modules` |
