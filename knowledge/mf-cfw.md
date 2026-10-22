# mf-cfw: CI & Playwright

## mf-cfw CI: "Unit tests" job failure is often the SonarQube gate, not Jest

- **The mf-cfw "Unit tests" CI job runs `yarn test:coverage` THEN a SonarQube scan in the same job; a red "Unit tests" with `Process completed with exit code 3` at the `Scan Code` step means the SQ quality gate failed, NOT that any Jest suite failed.** All suites can be green (`Test Suites: N passed`) while the job is red. Tell: the failing step is `Scan Code`, and the log tail shows `ERROR QUALITY GATE STATUS: FAILED` + `EXECUTION FAILURE` + `exit code 3`. Read the exact failing condition from the SQ PR comment (`gh pr view N --json comments`), e.g. `66.7% Coverage on New Code (required ≥ 90%)`. mf-cfw new-code coverage gate = **90%**. Fix = add direct unit tests for the uncovered new files. Common gap: per-page `api.ts`/`query.ts`/`store.ts` modules only get indirect coverage via the component test, which isn't enough — each needs its own `__tests__` suite (api: `jest.mock('~/api/api')` + assert endpoint/payload; query: `renderHook` + `QueryClientProvider` wrapper, assert success/error/cache-seed; store: import valtio proxy, assert default + setter). Confirmed 2026-08-05 (ENG-1118307, PR #488).

## mf-cfw Playwright / Cypress

- **mf-cfw webpack dev bundle too heavy for Playwright's isolated Chromium.** Both `cypress run --headed` (Electron OOM) and Playwright vs. dev server crash before any test runs — V8 heap limit, renderer crash. Fix: serve a static prod build with `DISABLE_ESLINT_PLUGIN=true yarn build` then `serve -s build -p 3500`. Playwright against the static build works cleanly.
  - **Update 2026-09-16**: Playwright against the plain `yarn start` dev server worked fine, no crash, when the harness route mounted just one small isolated component (no full page's worth of providers/data). The OOM above is likely specific to loading a heavier real page (auth/RBAC/query providers, big tables) through the dev bundle, not a blanket "dev server + Playwright" incompatibility — try the dev server directly for lightweight component-level harnesses before reaching for the static-build workaround.
- **Default dev port 8014 (from `.env`) can already be occupied by a different worktree's long-lived stale server** (`lsof -i :8014` showed a process alive 4+ days, `cwd` pointing at a sibling `mf-cfw-eng-*` worktree). `craco start` silently no-ops with "Something is already running on port 8014" instead of erroring, so `curl localhost:8014` "succeeds" against the WRONG worktree's build. Don't kill an unrecognized long-running process — use an alternate port instead: `PORT=8114 WDS_SOCKET_PORT=8114 yarn start`. Confirmed 2026-09-16 (ENG-1266586).
- **`DISABLE_ESLINT_PLUGIN=true` required for mf-cfw prod build** when a circular import exists. ESLint `Dependency cycle detected` error aborts normal `yarn build`. Use this env var to bypass for validation-only builds; fix the underlying cycle before shipping.
- **Circular import in `DNSSecurityRoutes.tsx`: `import('./dnsSecurity')` resolved to outer router, not subdirectory index.** On case-insensitive + case-sensitive filesystem, `import('./dnsSecurity')` matched `DNSSecurity.tsx` (outer router component) instead of `dnsSecurity/` subdirectory. `DNSSecurity.tsx` in turn imported `DNSSecurityRoutes.tsx` — circular — causing V8 OOM on every page load. Fix: `import('./dnsSecurity/index')` (explicit subdirectory index). Confirmed 2026-07 (ENG-1118301).
- **mf-cfw primary checkout had no `node_modules`** — symlink from primary fails if primary itself uninstalled. Run `yarn install --frozen-lockfile` directly in worktree (~46s). Don't use `npm install`; mf-cfw uses yarn.
- **mf-cfw uses `createHashRouter` — deep links are `http://localhost:<port>/#/<route>?q=…`.** `curl localhost:8214/settings/socks-proxy` returns 404 (only `/` and `/index.html` are served), which looks like a broken dev server but is just the hash router. Playwright/`page.goto` must use the `/#/` form. Confirmed 2026-09-16 (ENG-1266587 harness route).
- **Claude-in-Chrome extension cannot open `localhost`** — `navigate` returns "This site is blocked by your organization's policy". For local dev-server screenshots use Playwright instead. No Playwright package is installed in mf-cfw or globally (`npm root -g` only has `@playwright/cli`), but any webui2 worktree's `node_modules/@playwright/test` exports `chromium` and matches the cached browsers in `~/Library/Caches/ms-playwright`: `const { chromium } = require('/Users/lhsiao/ns/git/balken/<webui2-worktree>/node_modules/@playwright/test')`. Confirmed 2026-09-16.
- **`run_in_background` + a trailing `&` inside the command** makes the Bash task report "completed" immediately while the detached `yarn start` keeps running (find it with `lsof -i :<port> -sTCP:LISTEN`, kill by PID when done). Either drop the `&` and let `run_in_background` own the process, or expect to manage the PID yourself.
- **Playwright `page.route()` for mf-cfw standalone** must stub three endpoints before `page.goto()`: `/mf/rbac/remoteEntry.js` (return empty JS module), featureflag for `rbac_v3_feature_enabled` (return `false`), and `**/api/v2/ui/auth/authorize/pagepermissions**` (return permission fixture). Missing any causes `withAuthorization` HOC to hang on its loading state indefinitely.

## Run jest via `CI=true yarn -s test <path>`, not bare `npx jest` (2026-09-23; expanded 2026-10-05)

- `npx jest src/...` in mf-cfw fails every RTL suite with `ReferenceError: document is not defined` —
  the jsdom env + moduleNameMapper live in craco's jest config, not a standalone jest.config.
  Use `CI=true yarn -s test <path>` (`craco test --watchAll=false`).
- (2026-10-05, PR #561) `CI=true npx jest --watchAll=false` in mf-cfw produced 112/161 suites "failed to run" with `SyntaxError: Unexpected token 'export'` (ESM `@netskope-ui` component files parsed as CJS) — 943 cascading test failures in ~6s. Fresh `yarn install --frozen-lockfile` did NOT fix it (misdiagnosed as stale node_modules first).
- Root cause: `scripts.test` is `craco test --watchAll=false`; craco wires the CRA jest transform + `transformIgnorePatterns`. Bare `npx jest` uses package.json's jest block without the CRA/babel transform context and cannot parse the design-system ESM.
- Fix: `CI=true yarn test > $TMPDIR/x.log 2>&1` — 2284/2284 green. Also note the run exits 1 on "1 snapshot obsolete" even with 0 failing tests (NetworkLocationHome, pre-existing on the integration branch) — check the `Tests:` line, not the exit code.

## Cypress dns-resolver "Table Row Actions" flake: unstubbed admin-preferences API (2026-09-29)
- CI symptom: 2/46 fail in `dns-resolver.cy.ts` (row-actions menu items never found) on a PR that
  touched nothing in dnsResolver. Cause: `withAdminPreferences` (wrapping `DNSResolverTable` via
  `@netskope-ui/table`) fires GET `/api/v2/platform/admin/preferences?page=<page>` + initial
  per-feature saves on every mount; the spec never intercepted them, so they fell through to the
  dev-server proxy (`https://developer.vbox`, ENOTFOUND in CI) and failed slowly — the HOC's late
  state updates re-render the table and close an open Radix row-actions dropdown mid-test.
- Fix: stub in the spec's top-level beforeEach — GET `pathname: '**/api/v2/platform/admin/preferences'`
  → `[]`, and catch-all `pathname: '**/api/v2/platform/admin/preferences/**'` → `{}`. Any spec whose
  table uses withAdminPreferences needs the same stubs.
- **Local `cypress run` CANNOT reproduce CI for these specs**: locally the dev proxy resolves to a
  live tenant, so `featureflags/rbac_v3_feature_enabled` returns real values → RBAC v3 path
  (`/rbac/roles/me` + `/rbac/apigroups/pagemapping`) → 403 Not Authorized page; the spec's legacy
  `pagepermissions` intercept never matches and all tests die in before-each. In CI those calls
  ENOTFOUND → app falls back to the legacy path the mocks target. Validate spec changes on CI, or
  stub the rbac_v3 flag off locally first.

## `@netskope-ui/table` column order comes from `accessorKey`, not array order (2026-10-01)
- Display-only columns defined with just `id` (no `accessorKey`) rendered AFTER all keyed columns
  regardless of their position in `columns[]`: `getDefaultColumnOrder` maps `column.accessorKey`.
  Fix: give every column an `accessorKey` (a display-only key like `source_criteria` is fine).
- Sandbox gotcha: worktree under `~/ns/git/nplan6460/` is outside session cwd, so Bash writes there
  EPERM (Edit/Write tools work). Unsandboxed Bash gets a DIFFERENT `$TMPDIR` than sandboxed, so a
  script written to sandboxed `$TMPDIR` must be referenced by absolute path (`/tmp/claude-501/...`).

## @netskope-ui/dates is unusable in mf-cfw; icons shadow-decl additions needed per new icon (2026-10-16)
- `@netskope-ui/dates` 3.0 bundles a nested `@netskope-ui/core@8` whose `AngleRightIcon`/`XIcon`/etc. imports don't exist in icons 4.8 — webpack dev build fails with 7 "export not found" errors the moment anything from the package is imported. Jest passes (CJS build resolves differently), so run `yarn start:dev` (or build) before trusting a new @netskope-ui package. Workaround of record for Figma time ranges: a preset `@netskope-ui/select` ("Last 30 Days" etc.) feeding ISO `starttime`.
- Same session: new icons (`GoToPolicyIconIcon`, `ShieldIcon`) require adding to `src/react-app-env.d.ts`'s shadow declaration (known TS2305 trap); `@netskope-ui/dropdown` items only mount after the trigger opens — tests must click the kebab trigger before querying items.

## mf-cfw visual-check harness: `__preview__/` route + playwright-cli + MSW gotchas (2026-09-24)

- mf-cfw uses `createHashRouter` — dev preview routes are `http://localhost:PORT/#/<route>`, NOT path URLs. A path-only URL loads the SPA shell and sits on "Loading..." forever.
- Preview-harness precedent: `src/pages/policyAnalyzer/__preview__/PolicyGroupListPreview.tsx` + `APP_ROUTES.POLICY_ANALYZER_PREVIEW_PAGE` gated on `AppConfig.IS_DEV_ENV` in `AppRoutes.tsx` — committed to master (ee26b696), so keep new harnesses rather than reverting when the pattern matches.
- MSW in mf-cfw dev server: needs `REACT_APP_ENABLE_MSW=true` on the `craco start` env AND the browser session must register `mockServiceWorker.js` before `worker.start()` runs — on a fresh playwright-cli profile the first page load races SW activation, so `worker.start()` (not awaited in compiled bootstrap) never attaches and requests pass through to 404. Manual `navigator.serviceWorker.register('/mockServiceWorker.js')` + reload does NOT fix it (client handshake missing). RTL tests remain the reliable submit-path proof; browser run still validates render/checklist/add-remove and the error path (bottom-right toast on the 404).
- `src/react-app-env.d.ts` redeclares `@netskope-ui/core` (and several other @netskope-ui/* packages) with an explicit untyped export list — any component NOT listed there (e.g. `Checkbox`) fails TS2305 even though the real package exports it. Add the export to the shadow declaration when using a new component.
- jest.mock factories hoist above imports: `React.forwardRef` inside a factory throws `Cannot access '_react' before initialization` if `import React` sits below the mock (prettier/eslint import-order can move it). Fix: `const ReactLocal = jest.requireActual<typeof import('react')>('react')` inside the factory.
- jsdom in mf-cfw has no WebCrypto global — `crypto.randomUUID()` throws `ReferenceError: crypto is not defined`. Mirror `AnalyzeSidePanelWrapper.test.tsx`: `Object.defineProperty(globalThis, 'crypto', { value: { randomUUID: ... } })`.
- jsdom `fireEvent.click` on a `<button type="submit">` does not trigger RHF `handleSubmit`; use `fireEvent.submit(formElement)` instead.
- `@netskope-ui/select` real types: `onChange` is intersected with `FormEventHandler`, so a handler param typed `Array<string|number|object>` fails TS2322 — type the param `unknown` and cast inside.

## mf-cfw real-tenant validation via development-proxy (2026-09-25)

- Path: dev-proxy (`/Users/lhsiao/ns/git/development-proxy`, port 9797, fallbackServer.host = QA tenant) + mf-cfw craco devServer with a TEMP `devServer.proxy` entry mapping the API path to `http://localhost:9797` (same-origin from the page → no CORS). Setting `REACT_APP_API_BASE_URL=http://localhost:9797` instead FAILS: cross-origin XHR, preflight has no ACAO header.
- Login: playwright-cli against `http://localhost:9797/locallogin` with NS_TEST_USERNAME/PASSWORD; cookies land on domain `localhost` (port-agnostic) so the :3009 page session carries them.
- Webpack chunk cache trap: after restarting `craco start` with different env, `goto` to the same URL may keep stale chunks (dev chunk names aren't content-hashed); verify with a `fetch(chunk, {cache:'no-store'})` probe and hard-reset via `goto about:blank` first.
- Fullscreen overlay iframe (z-index 2147483647, likely MF shell/devtools artifact) swallows all clicks — `document.elementFromPoint` returns IFRAME; set `pointerEvents:none`/`display:none` on iframes wider than viewport before driving the page.
- REAL BUG FOUND: spec-documented bare paths `/simulate` and `/analyze` 404 on real tenants; the policyanalyzer family answers at `/api/policyanalyzer/*` (verified 2026-09-25 on nsclienttw-auto.qa.boomskope.com — POST returns RBAC "Permission denied" for the test user, i.e. endpoint live). mf-cfw api-url.ts analyze entries from PR #534 need the same prefix fix.
- **CORRECTED 2026-10-05 (PR #561)**: the claim above is itself wrong — the real family is `/api/v2/policyanalyzer/*` (all 4 endpoints answer 403 "Forbidden" = live on nsclienttw-auto; the unversioned `/api/policyanalyzer/*` 404s). Two successive tenant-probe claims were wrong; when a path claim is load-bearing, probe BOTH candidate families in the same session before writing a "tenant-verified" comment.
- playwright-cli has `cookie-list` / `cookie-get <name>` — export the session cookie and curl path variants through the proxy to map a tenant's real API surface fast.

## CRA (react-scripts) jest default `resetMocks: true` silently wipes `jest.fn(impl)` creation-time implementations (2026-10-01, mf-cfw PR 506)

- react-scripts' createJestConfig defaults include `resetMocks: true` (line ~68) and the repo's package.json `jest` block didn't override it. Every `jest.fn((fn) => (e) => ...)` whose implementation was set at mock CREATION returns `undefined` inside tests: component received `onClick={undefined}`, save clicks silently no-op'd, "Number of calls: 0". Tests setting `mockImplementation` INSIDE the test body keep working — only creation-time impls die.
- Diagnosis trick: render-probe `typeof onClick` inside the component-mock factory (ButtonV2 mock logging) — shows the prop actually delivered to the mocked component.
- Fix: re-arm implementations in `beforeEach` (`mock.mockImplementation(...)` after `jest.clearAllMocks()`).

## mf-cfw local jest: custom env `src/test-utils/jest-environment-jsdom-compat.js` fails to LOAD locally but works on CI (2026-10-01)

- Local: "TypeError: Class constructor JSDOMEnvironment cannot be invoked without 'new'" at a bogus line (transformed output), stack line > file length. Any suite whose docblock uses `<rootDir>/src/test-utils/jest-environment-jsdom-compat.js` cannot run locally; CI loads it fine (same lockfile, Node 20). Only NetworkLocationAddEdit.test.tsx uses it.
- Workaround for local verification: temp-swap docblock to `/** @jest-environment jsdom */` (default env loads fine locally — 54-test suites in same repo pass), run, then RESTORE the compat docblock before committing. Note CLI `--testEnvironment=jsdom` does NOT override a docblock (docblock wins).

## Deleting a component usage: grep other consumers before removing its jest.mock (2026-10-01)

- Removed the `@netskope-ui/select` mock from SimulateInputForm.test.tsx because the removed Scope select looked like its only user; `AttributeValueRow` enum fields also render `Select.Root`, so the enum-options test received `[]`. Fix: `grep -rn "@netskope-ui/select" <dir>` first; restored the mock.

## Real-tenant browser validation of a local mf-cfw build (2026-10-15)

- Recipe that worked: TEMP `devServer` function in `craco.config.ts` (proxy `/api` -> tenant, `changeOrigin`, header `x-npe-env`), tenant session cookies (`ci_session`, `auth_session`) injected as localhost cookies via `context.addCookies`, mock only the write (`page.route` POST) so no tenant data is added. Revert craco with `git checkout --` afterwards.
- Port 8014 is often taken by a sibling worktree: start with `PORT=8030 WDS_SOCKET_PORT=8030` (the `.env` pins WDS_SOCKET_PORT).
- `playwright-cli cookie-list` prints cookie VALUES in plain text; never let it reach the conversation (write to a file, parse in a script).
- playwright-cli login: after `open /locallogin` wait ~8s and `snapshot` before `fill`; filling immediately left the page on /auth/login. `page.route` handlers registered in one `run-code` call persisted into later calls and across `reload` in the same session -- `page.unroute` them before the "recovery" check.
- Forcing a real render error without code edits: mock the API with a field of the wrong type (e.g. `action` as an object); `traffic_patterns: [null]` did NOT throw.

## OpenAPI with no `required` list: type every field optional, or live tenants crash render (2026-10-21, mf-cfw PR #605)

- Spec v50 (Confluence 8036483474) lists NO `required` on any policyanalyzer schema. FE typed Simulate match fields required; live `POST /simulate` returned `{policy_order, policy_name, enabled, action}` only, and `MatchCardBody` `match.users.length` threw in render (per-tab boundary hid all results). I had also told the user "users/tags are required in spec" from reading the property list — wrong; parse the schema with PyYAML and check `required` explicitly before claiming it.
- Fix pattern: optional types (tsc then lists every reader), guard arrays at the ONE shared renderer, hide absent rows/pills rather than defaulting (absent `enabled` rendered "Disabled" = a lie).
- Also: `/tmp/claude/` got wiped between days — a page generator script and its input JSON vanished. Keep re-runnable generators next to the report (or edit the HTML directly) when a doc will be iterated over several days.

## `yarn test` in sandbox: "Failed to load native binding" (@swc/core) (2026-10-22)

- Worktree `node_modules` symlinks to another worktree; craco/ts-node loads `@swc/core` darwin-arm64 `.node` → sandbox blocks dlopen. `tsc`/`eslint` fine in sandbox; jest not. Rerun `yarn test <path>` with `dangerouslyDisableSandbox: true` — passes (21 suites/239 tests for trafficSimulator).
- Sandbox Bash also can't write to sibling worktrees or `~/.claude/knowledge` (`operation not permitted`); use Edit/Write tools for those.

## Side-panel fetch UI + lint/preview traps (ENG-1270527, 2026-10-22)

- `SidePanelV2` does not forward `data-testid` to the DOM — `getByTestId('…-panel')` fails even while open. Assert on an element inside the panel (e.g. the TopBar refresh button) instead.
- `t('key')` returns `DefaultTFuncReturn` (includes `null`): fine on `@netskope-ui` components, but a plain `<div aria-label={t(…)}>` fails tsc TS2322. Use `t(…) ?? undefined`.
- `npx eslint .` piped to `grep error` shows nothing (default formatter). Use `npx eslint . -f unix | grep "\[Error"` to list errors; `yarn lint` runs theme check + tsc first, so tsc errors mask eslint ones until fixed.
- `prefer-destructuring` fires on `const x = new AbortController().signal` and `mock.calls[0][0]` in tests: use `const { signal } = …` / `const [[url]] = mock.calls`.
- `mf-cfw-preview-harness` skill template assumes a clean worktree + throwaway route + revert. When the preview route is already committed and the worktree is intentionally dirty with the feature, tell the sub-agent explicitly: no dirty-stop, no route edit, no revert, `git status` must be unchanged.
- zsh: `npx prettier --write $files` with a newline-separated var does not split. Write the list to `$TMPDIR/files.txt` and use `xargs npx … < file`.
