# mf-client (netskope-ng-base/frontends/mf-client)

## ENG-1356094 — Internet Security row must read `lseDeviceEvent.status`, not `status_v2` (2026-11-06)

- L3 mapping: `client_status` == Internet Security status == Tunnel status; `client_status_v2` = IS + NPA aggregate.
- Internet Security row: read `lse_event_status` (i.e. `lseDeviceEvent.status`), submit `client_status_v2`.
- All Client Status row: read `lse_event_status_v2`, submit `client_status`.
- Bug: `handleInternetSecurityStatus` originally read top-level `selectedDevice.last_event__status_v2` (aggregate) while the button label + status cell read service-level `lseDeviceEvent.status`. On OTP-disabled devices these diverge → button says "Enable" but handler submits `client_status_v2: 0`.
- First-pass fix wrongly pivoted everything to `status_v2` — that's the IS+NPA aggregate, not pure IS. Correct fix: all three (status cell, button label, `isEnabled` payload) read `lseDeviceEvent.status`.
- Test divergence case must set `last_seen_device_event.status='Disabled'` AND `last_seen_device_event.status_v2='Enabled'` (and top-level `last_event__status_v2='Enabled'`) to prove the handler ignores both aggregates.

## Run jest via `yarn test` (craco), never `npx jest` directly (2026-11-06)

- Symptom: `npx jest <path>` fails with `SyntaxError: Unexpected token 'export'` from
  `@netskope-ui/core/dist/es/index.js` (ESM inside a CJS-consumed package), or earlier with
  `ReferenceError: MutationObserver is not defined` when the suite needs the jsdom29 env.
- Root cause: mf-client is a CRA + craco repo. The CRA default jest config (babel transform,
  jsdom env, transformIgnorePatterns covering `@netskope-ui/*`) is only applied through
  `craco test`. Bare `npx jest` uses the minimal `jest` block in `package.json`, which lacks
  the CRA transform pipeline.
- Fix: always run `yarn test --testPathPattern="<name>"` (script is `craco test --watchAll=false`).
- Related: for suites that hit `MutationObserver is not defined`, add the docblock
  `/** @jest-environment <rootDir>/src/test-utils/jest-environment-jsdom29.js */` at the top
  of the test file (sibling suites already do this — see
  `src/components/SteeringConfigModal/PrivateAppsGatewaySelection.test.tsx`). The custom env
  uses `pretendToBeVisual: true` so `MutationObserver` is defined. mf-cfw has a similar
  custom-env trap — see [[mf-cfw]].

## Submodule bumps surface in the parent `netskope-ng-base` worktree

- `frontends/mf-client` is a git submodule of `netskope-ng-base`. Committing inside the
  submodule leaves the parent worktree with `M frontends/mf-client` until the parent is
  updated to point at the new submodule SHA. Boot-feature flow: do the feature work in the
  submodule's own branch (`pr/ENG-XXX/...`), push, PR against mf-client's `master`. Parent
  submodule bump is a separate, later step (usually handled by release tooling).

## tsc --noEmit baseline is ~300 pre-existing errors (2026-11-10)

- `npx tsc --noEmit` on mf-client `master` reports ~300 errors (TS2345 x299, TS2589 x1) across 26 files — template-literal types vs `i18n.t(string)`, unrelated to your change. Don't try to fix them; the `lint` script's `tsc` step is dead weight locally, CI gates on its own config.
- Correct use: run `npx tsc --noEmit` on BOTH the worktree and the primary checkout (same commit = same count), diff the counts. "No new errors" = same count, not zero. Verify your touched files contribute nothing via `npx tsc --noEmit 2>&1 | grep <your-file-names>` (empty = clean).
- Coverage baseline for reference: `DevicesFilters.tsx` sits at ~95% stmts / 86% branches with UNCOVERED lines only in the JIT-provisioning `processQuery`/`processCacheQuery` memos and `handlerWhenQueryStartsOrStopsPending` (lines ~174/184/219-221) — pre-existing gaps, not yours to close when validating a filter-mapping change.
