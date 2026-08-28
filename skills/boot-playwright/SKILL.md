---
name: boot-playwright
description: >-
  Unified Playwright/browser-validation skill for NGWeb local dev stacks. Owns
  shared session/login/navigation/reporting mechanics once; per-environment setup
  lives in recipes/. Invoke as `/boot-playwright <recipe> <slug>` with an explicit
  recipe name — this skill does not auto-detect which environment applies.
  Replaces webui-devbox-playwright, init-dev-env, mf-cfw-playwright, and
  mf-client-playwright (each now deprecated, points here).
argument-hint: "<recipe> <slug> [validation context]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Grep
---

# Boot Playwright

Shared browser-automation knowledge for validating NGWeb changes across five local
dev-stack flavors. This file owns everything that does NOT vary by environment;
`recipes/*.md` own everything that does.

## Recipes

| Recipe | Environment | Base? |
|--------|-------------|-------|
| `webui-angular-devbox` | devbox-ui + webui (Angular Settings pages) | base |
| `webui-angular-devbox-mf-client` | devbox-ui + webui + mf-client MFE | layers on base |
| `webui-angular-devbox-mf-cfw` | devbox-ui (optional) + mf-cfw MFE | layers on base for Playwright mode; Cypress mode needs no devbox |
| `webui2-angular-shell-devbox` | webui2 + Angular-shell hybrid (Vite, no Docker) | standalone |

## Invocation contract

```
/boot-playwright <recipe> <slug> [validation context]
```

- `<recipe>` MUST be one of the four names above (matches a file under `recipes/`).
  If omitted or unrecognized, list the four valid names and STOP — do not guess
  from context, changed files, or conversation history. Recipe selection is the
  caller's job (a human, or `boot-bugfix`/`boot-feature` picking from the UI area
  they just touched).
- `<slug>` is the kebab-case feature descriptor shared with the worktree triad
  (see the base recipe). Reused as the `playwright-cli` session name unless the
  recipe says otherwise.
- Read the named recipe file first. If it opens with a pointer to another recipe
  (the two MF-specific recipes point to `webui-angular-devbox.md`), read that one
  too, in order, before executing any setup steps.

## Session lifecycle: `playwright-cli` only

All four recipes drive the browser through named `playwright-cli` sessions. Never
hand-roll a raw `chromium.launchServer()` + ws-endpoint-file — that pattern is
retired; `-s=<name>` sessions give you launch-or-reuse for free.

```bash
playwright-cli list                    # see what's already open
playwright-cli -s=<slug> open          # headless by default; reuses <slug> if it exists
playwright-cli -s=<slug> open --headed # only for webui2-angular-shell-devbox (see below)
```

Default to **headless**. The one exception is `webui2-angular-shell-devbox`, whose
target QA tenant rejects the headless Chrome UA outright — that recipe's own file
calls this out again at the point of use, but the rule originates here: pick
headless unless the recipe you're following says otherwise.

Never `close` a session mid-validation, pass or fail — leave it open for reuse by
the next invocation in the same conversation. Only close when the user explicitly
asks to end the session, or a session is confirmed stale:

```bash
playwright-cli -s=<slug> close
```

## Credentials

Stored in a `.env` file next to the relevant recipe's originating skill, never
committed. Existing convention, unchanged by this consolidation:

```
/Users/lhsiao/.claude/skills/mf-client-playwright/.env
NS_TEST_USERNAME=<email>
NS_TEST_PASSWORD=<password>
```

```bash
source /Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

mf-cfw's QA-tenant mode additionally needs `NS_QA_TENANT` in
`~/.claude/skills/mf-cfw-playwright/.env` (see that recipe).

## Login flow

Applies to any recipe authenticating against webui/webui2. Skip entirely if the
current page is already past `/login`/`/locallogin` — check before running it:

```bash
# only run the block below if the current page is about:blank, /login, or /locallogin
playwright-cli -s=<slug> open http://<proxy-host>/locallogin
playwright-cli -s=<slug> fill '#username' "$NS_TEST_USERNAME"
playwright-cli -s=<slug> fill '#password' "$NS_TEST_PASSWORD"
playwright-cli -s=<slug> click '#btn-sign-in'
# wait for the hash to leave /login before proceeding — poll, don't sleep-and-hope:
playwright-cli -s=<slug> eval "() => !window.location.hash.includes('/login')"
# dismiss the welcome wizard if present
playwright-cli -s=<slug> click 'text=skip this step'
```

## SPA navigation: hash assignment, never `goto`

Post-login navigation inside the SPA MUST use hash assignment. `goto` (or any full
reload) drops session cookies and forces the micro-frontend to re-bootstrap
(30–60s).

```bash
playwright-cli -s=<slug> eval "() => { window.location.hash = '#/settings/device-management'; }"
```

Wait for a known readiness element before asserting anything — MFE/Angular loads
are slow (30–60s is normal, not a failure):

```bash
playwright-cli -s=<slug> eval "() => !!document.querySelector('[data-testid=\"filter-toggle-advanced\"]')"
```

## Validation plan + reporting format

Before writing any automation, turn the validation context into a **numbered
plan** and show it: each step names what to check, the selector/locator, and the
pass condition. Present it before executing.

Per step: perform the action/assertion, then capture proof regardless of outcome:

```bash
playwright-cli -s=<slug> screenshot --filename /tmp/<slug>-step-N.png --full-page
```

Report PASS/FAIL per step as you go. At the end, print a summary table. **Never
close the session on failure or success** — leave it open for inspection/reuse.
If any step failed, say so plainly; do not retry silently past the recipe's own
failure policy (each recipe/caller defines its own retry cap, e.g. `boot-bugfix`'s
3-attempt rule).

## Cleanup

```bash
playwright-cli -s=<slug> close   # only when the user is done with this session
```

Recipe-specific process/container teardown (dev servers, proxies, docker
containers) lives in each recipe's own Teardown section — this file only owns the
browser session.
