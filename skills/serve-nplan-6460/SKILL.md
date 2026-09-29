---
name: serve-nplan-6460
description: >-
  Brings up the NPLAN-6460 (Traffic Simulator / Policy Analyzer) integration
  environment: webui on pr/ENG-1274460/nplan-6460-main and mf-cfw on
  pr/ENG-1274461/nplan-6460-main, both fast-forwarded to origin first.
  Triggers on "/serve-nplan-6460" or a request to serve/run the NPLAN-6460
  integration branches locally.
argument-hint: "[--with-shell] [--msw] [--port <mf-cfw port, default 8034>]"
allowed-tools: Bash(git:*), Bash(yarn:*), Bash(npx:*), Bash(curl:*), Bash(lsof:*), Read, Grep, Glob
user-invocable: true
---

# Serve NPLAN-6460

**Emit "Skill activated: serve-nplan-6460"**

Serves the two NPLAN-6460 integration branches from their fixed worktrees. Shared
session/login/navigation/reporting mechanics live in
`~/.claude/skills/boot-playwright/SKILL.md` — read it before driving a browser
against anything this skill starts. Recipe-level detail: mf-cfw mechanics in
`boot-playwright/recipes/webui-angular-devbox-mf-cfw.md`, webui devbox mechanics
in `boot-playwright/recipes/webui-angular-devbox.md` (Shared stack mode).

## Fixed inputs

| Repo | Branch | Worktree |
|------|--------|----------|
| webui | `pr/ENG-1274460/nplan-6460-main` | `/Users/lhsiao/ns/git/webui-6460-main` |
| mf-cfw | `pr/ENG-1274461/nplan-6460-main` | `/Users/lhsiao/ns/git/nplan6460/mf-cfw-eng-1274461-nplan-6460-main` |

If a worktree is missing, recreate it from the primary checkout
(`git worktree add <path> <branch>` tracking the origin branch) — never serve
from the primary checkout itself.

## Step 1 — Sync both worktrees

For each worktree: fetch its branch, `git status --porcelain` (bail and report if
dirty — never discard local work), then `git merge --ff-only origin/<branch>`.
Use `/usr/bin/git` directly (rtk hook trips the worktree isolation guard).

mf-cfw only: ensure `node_modules` resolves (symlink from a sibling worktree
whose `yarn.lock` md5 matches — currently
`/Users/lhsiao/ns/git/mf-cfw-eng-1266586-analyze-sidepanel-filter/node_modules`)
and `.husky/_/` exists (`npx husky install` once if not; needed only if the
session will also commit).

## Step 2 — Serve mf-cfw (always)

Default port **8034** (`--port` overrides; check `lsof -ti :<port>` first — a
stale sibling server on the default port silently wins otherwise). `--msw` adds
`REACT_APP_ENABLE_MSW=true` so `POST /simulate` is served by the MSW stub
(spec-2.1 wrapped shape) and the Simulator tab works end-to-end offline.

```bash
cd <mf-cfw worktree>
PORT=<port> WDS_SOCKET_PORT=<port> BROWSER=none [REACT_APP_ENABLE_MSW=true] \
  npx craco start   # background; wait for "webpack compiled successfully"
```

mf-cfw uses `createHashRouter` — every URL below is `http://localhost:<port>/#/...`.

| Surface | Hash route | Notes |
|---------|-----------|-------|
| Traffic Simulator page (real) | `/traffic-simulator-page` | Simulator tab is fully assembled; submit needs `--msw` (or a dev-proxy tenant) |
| Analyze wrapper preview | `/analyze-sidepanel-preview` | `?last=ok\|empty\|error`; needs the RBAC stub trio below |
| Analyze list/detail preview | `/policy-analyzer-preview` | `?focus=<policy_id>` `?search=<term>`; no stubs needed |
| Simulate input form preview | `/traffic-simulator-preview` | |
| Simulate results preview | `/traffic-simulator-results-preview` | `?variant=empty` |
| Simulate history full-flow preview | `/traffic-simulator-history-preview` | axios-adapter fixture, no stubs needed |

RBAC stub trio (anything mounting `withAuthorization` — the wrapper preview and
the real page): set BEFORE `goto`, per `knowledge/mf-cfw.md`:

```bash
playwright-cli -s=<session> route '**/mf/rbac/remoteEntry.js' --body '' --content-type application/javascript
playwright-cli -s=<session> route '**rbac_v3_feature_enabled**' --body '"0"' --content-type application/json
playwright-cli -s=<session> route '**/api/v2/ui/auth/authorize/pagepermissions**' --body '{"data":"rw"}' --content-type application/json
```

Real-tenant API calls (`/api/policyanalyzer/*`) still 403 everywhere until the
RBAC apiGroup lands (ENG-1322109) — MSW/preview adapters are the working lanes.

## Step 3 — Serve webui (only with `--with-shell`)

The webui half only matters for shell-side surfaces: the Skope IT "Traffic
Simulator" nav entry (ENG-1270535), the inline-policy-page "Analyze Policies"
button (ENG-1266585), and the Angular↔MFE handoff. Follow
`boot-playwright/recipes/webui-angular-devbox.md` **Shared stack mode** — the
per-slug SLOT scheme breaks tenant recognition, so repoint the base containers:

```bash
cd /Users/lhsiao/ns/git/devbox-ui
NS_WEB_UI_DIR=/Users/lhsiao/ns/git/webui-6460-main \
  docker compose up -d --force-recreate web angular-ui
# then browse https://developer.vbox (bare hostname, no port)
```

Prerequisites called out in that recipe apply (base devbox stack up, worktree
vendor/ is a real rsync copy, feature flags `nplan6460_policy_analyzer_enabled` /
`nplan6460_policy_simulator_enabled` + CF on the tenant — `/wb:utils:ff` is the
sanctioned toggle path). **Caveat:** the shell resolves the `<mf-cfw>` remote
through nginx (`ngweb_mf` fallback), not through the Step-2 dev server — the
shell lane validates webui-side wiring against the *deployed* mf-cfw bundle.
End-to-end "local mf-cfw inside local shell" wiring is not established; if the
task needs it, stop and say so rather than improvising an override.

When done, repoint back:
`docker compose up -d --force-recreate web angular-ui` with `NS_WEB_UI_DIR` unset.

## Step 4 — Verify + report

- mf-cfw: `curl -s -o /dev/null -w '%{http_code}' http://localhost:<port>/` → 200,
  and the target hash route mounts (`[data-testid="topbar-title"]` or the
  preview's own testid).
- webui (shell lane): `https://developer.vbox/locallogin` renders the login form
  (`boot-playwright/SKILL.md` owns the login/nav mechanics from here).

Report a table: surface → URL → status. State which lanes are stubbed
(MSW / RBAC trio) vs real.

## Cleanup

Kill only servers this invocation started (`lsof -ti :<port> | xargs kill`),
repoint devbox back to primary if Step 3 ran, and leave the worktrees in place —
they are the standing integration checkouts, not per-run scratch.
