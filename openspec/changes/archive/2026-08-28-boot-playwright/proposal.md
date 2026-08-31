## Why

Four Playwright/browser-validation skills (`webui-devbox-playwright`, `init-dev-env`,
`mf-cfw-playwright`, `mf-client-playwright`) each re-implement the same core mechanics
(browser session reuse, login flow, SPA hash navigation, validation-plan format,
headless-Chrome UA spoofing, cleanup) with copy-pasted drift between them, and use two
incompatible session mechanisms (hand-rolled `browserServer`/ws-endpoint-file vs.
`playwright-cli` sessions, the latter already used ad hoc by `boot-bugfix`). A fifth
environment (webui2 + Angular-shell hybrid dev stack) has no dedicated skill at all —
its setup only exists as a third-party plugin command (`/wb:setup:angular-shell`) not
owned by this config repo. Consolidating into one skill with per-environment recipes
removes the duplication, standardizes on one session mechanism, and gives `boot-bugfix`
/ `boot-feature` a single, consistent Playwright validation entry point instead of each
hand-coding its own dev-env bootstrap + browser plumbing.

## What Changes

- Add a new skill `boot-playwright` with:
  - Shared knowledge in `SKILL.md`: `playwright-cli` session lifecycle (open/reuse by
    `-s=<name>`, never launch raw `browserServer`), login flow, SPA hash-navigation
    pattern, headless-Chrome UA spoof, validation-plan format (numbered
    what/selector/pass-condition), per-step PASS/FAIL + screenshot template,
    summary/pause-on-failure convention, `.env` credential convention, cleanup.
  - `recipes/webui-angular-devbox.md`: base devbox-ui stack recipe — per-slug SLOT
    port formula, worktree `vendor/`+`node_modules` setup rules, `rbac-css` stash,
    cert-rotation cookie bypass, view/subview two-hash navigation quirk, list-data
    load-patience polling. Absorbs `webui-devbox-playwright` + the devbox-facing
    half of `init-dev-env`.
  - `recipes/webui-angular-devbox-mf-client.md`: layers on the base recipe —
    mf-client dev-server startup (port offset, `FAST_REFRESH=false` workaround),
    dev-proxy startup pointed at the base recipe's web TLS port, MF load-readiness
    wait. Absorbs `mf-client-playwright` + the proxy-facing half of `init-dev-env`.
  - `recipes/webui-angular-devbox-mf-cfw.md`: layers on the base recipe — mf-cfw
    dev server (yarn/craco, port 8014), Cypress RBAC-mock mode (no devbox needed)
    vs. Playwright mode (standalone or QA-tenant-via-proxy). Absorbs
    `mf-cfw-playwright` minus its ticket-specific (ENG-1118301 DNS Security) content,
    which is dropped, not migrated.
  - `recipes/webui2-angular-shell-devbox.md`: new recipe for the webui2 +
    Angular-shell hybrid stack (Vite + `angularHybridPlugin`, no Docker,
    headed-browser-only — QA tenant rejects headless UA, the opposite of the other
    three recipes' spoofed-headless default). Written from scratch, cross-checked
    against the sibling plugin command `/wb:setup:webui2-shell` to backfill gaps the
    hybrid-mode reference command lacked: MariaDB/Colima liveness check, `/pinger`
    in `PUBLIC_LOCAL_API_PATHS`, curl-based health-check retry loops with
    kill-on-failure, `dev-backend.sh`-missing fallback, dependency-install
    skip-if-present step.
  - Recipe selection is an **explicit argument** to `/boot-playwright` (recipe name +
    slug) — no auto-detection inside the skill; callers (a human, or `boot-bugfix`/
    `boot-feature`) decide which recipe applies from the files they touched.
- **BREAKING**: `boot-bugfix` Phase 5 and `boot-feature` Step 3.5 stop hand-rolling
  dev-env bootstrap + Playwright instructions inline; both are rewritten to invoke
  `/boot-playwright <recipe> <slug>` instead.
- Mark `webui-devbox-playwright`, `init-dev-env`, `mf-cfw-playwright`, and
  `mf-client-playwright` deprecated: replace each `SKILL.md` body with a one-line
  pointer to `boot-playwright`, keep the directories (no deletion, no cleanup pass
  in this change).

## Capabilities

### New Capabilities
- `boot-playwright`: single skill owning shared Playwright/browser-validation
  knowledge plus four dev-environment recipes (webui-angular-devbox,
  +mf-client, +mf-cfw, webui2-angular-shell-devbox), invoked with an explicit
  recipe + slug argument.

### Modified Capabilities
(none — no existing specs for `boot-bugfix`/`boot-feature`/the four legacy skills to
delta against; their integration-point changes are captured under Impact below.)

## Impact

- New files: `~/.claude/skills/boot-playwright/SKILL.md` and four
  `~/.claude/skills/boot-playwright/recipes/*.md` files.
- Modified files: `~/.claude/skills/boot-bugfix/SKILL.md` (Phase 5),
  `~/.claude/skills/boot-feature/SKILL.md` (Step 3.5) — both switch to invoking
  `/boot-playwright <recipe> <slug>`.
- Modified files (deprecation pointer only): `webui-devbox-playwright/SKILL.md`,
  `init-dev-env/SKILL.md`, `mf-cfw-playwright/SKILL.md`,
  `mf-client-playwright/SKILL.md`.
- No change to `mf-client-playwright/.env` — credential file convention carries
  over unchanged (same path pattern, now referenced from the new skill).
- No change to the third-party `wb:setup:angular-shell` / `wb:setup:webui2-shell`
  plugin commands — they remain the upstream reference; `boot-playwright`'s webui2
  recipe is a self-owned rewrite, not a wrapper around them.
