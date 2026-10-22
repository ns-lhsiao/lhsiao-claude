# Frontend Patterns

## Webui neo Angular HTTP Interceptors

- **`PayloadInterceptor` (neo/src/app/http-interceptors/payload-interceptor.ts) strips the `{status,data}` envelope on every `status:'success'` response** — it does `resp.clone({ body: body.data })` before the subscriber runs. So a component subscribing to `this.http.post<{status,data:{...}}>()` receives ONLY `data`, not the envelope. Reading `resp.data.count` in the `next` handler yields `undefined`; the correct read is `resp.count`. Failure signature (ENG-1149041): raw wire body shows `{"status":"success","data":{"rows":[...],"count":62}}` (Playwright `response` listener sees pre-interceptor bytes), backend 200, yet the bound field stays 0 and the `*ngIf` gate never fires. Unit tests PASS because they mock the service method directly (`jest.spyOn(service,'x').mockReturnValue(of(...))`), bypassing the interceptor — so the mock must return the UNWRAPPED shape `{rows,count}` to match runtime, not the enveloped `{status,data}`. Service `.spec.ts` using `HttpTestingController` is exempt: `httpMock.flush(envelope)` runs no interceptors, so it round-trips the raw envelope. Verify component data-flow bugs IN-BROWSER via `window.ng.getComponent(el)` state probes — jest can't catch this class of interceptor-shape drift. Confirmed 2026-08-03.
- **Neo theme button classes are `ns-btn ns-btn-primary|secondary|gray`, NOT Bootstrap `btn btn-secondary`.** A `class="btn btn-secondary"` button renders as unstyled plain text (no border/bg). Grep the surrounding feature dir for the `ns-btn` convention before adding buttons. Only visible in-browser; jest DOM assertions on `textContent` pass regardless.

## @netskope-ui/core named imports failing under TypeScript 4.9

- **`@netskope-ui/core`'s shipped `.d.ts` uses TypeScript 5.0's inline `export { type X, Y }` specifier syntax; a repo pinned to TypeScript <5.0 (e.g. mf-cfw's 4.9.5) mis-parses it**, silently dropping export bindings positioned adjacent to a `type`-modified specifier from the resolved symbol table. Symptom: `import { TagLabel, Sentiments } from '@netskope-ui/core'` fails with `TS2305: Module has no exported member 'TagLabel'` (and same for `Sentiments`) even though both exist at runtime (`exports.TagLabel` present in `dist/cjs/index.js`) and are textually present in `dist/index.d.ts`'s export list — `skipLibCheck: true` doesn't help since this is an export-list parse issue, not a type-check issue. Other names in the same barrel not adjacent to an inline `type` specifier (e.g. `Tag`, `ToggleGroup`) import fine. Fix: avoid the broken names — pass children/text directly into the parent component (`Tag`'s own prop type accepts `children?: ReactNode` with no `TagLabel`-specific requirement) and declare a local literal-union type instead of importing `Sentiments`; TS structurally validates the local type against the component's internally-resolved (correctly parsed at its own declaration site) prop type regardless. Confirmed 2026-09-16 (ENG-1266586, mf-cfw, `@netskope-ui/core@12.2.2` + `typescript@4.9.5`).

## React, React Query, TanStack Table

- **TanStack Table `columns` memo must include closed-over data in deps**. A cell function closing over a prop/state without listing it freezes with the initial captured value — async lookups (scimId → name, user profiles) render the raw id forever. ESLint `exhaustive-deps` and React Compiler are often disabled around `useReactTable`.
- **React Query `isFetching` has a one-render gap when `enabled` flips true**. The render where `enabled: true` first evaluates is NOT the render where `isFetching: true` flips on. Gates like `hasData > 0 && !query.data && query.isFetching` let the stale value paint for one frame. Fixes: gate on `!query.data`, or track pending in local state, or fix the upstream memo-dep bug.
- **`ref.current` as a prop is an anti-pattern**. Refs don't trigger re-renders, so the value reflects the previous render. Use stable props derived from props/state for render-time decisions (e.g. a `mode` prop set once per modal-open cycle).
- **`aria-disabled` doesn't trigger CSS `:disabled`**. ntskui's Checkbox/Select/Combobox triggers render as `button[role=checkbox]` with `aria-disabled="true"`, NOT the HTML `disabled` attribute. Tailwind's `disabled:` variants don't match. Apply `opacity-50 cursor-not-allowed` to your wrapping container. Test trap: `toBeDisabled()` may not fire — assert `el.getAttribute('aria-disabled') === 'true'`.
- **`lodash.debounce(fn, ms)` defers ALL side effects in the body, including loading-flag flips**. If your fetcher writes `store.loading = true` inside the debounced function and the caller renders against `store.loading`, the flag stays `false` for the first `ms`. UI gates that read `!loading` will permit interaction during that window. Fix: flip the loading flag synchronously at the call site (or in a thin wrapper), and reset stale per-entity slices of the store on entity change so a previous entity's "ready" data can't render against the new one. Failure signature: feature works after waiting; broken on immediate click. Repro: ENG-1029558 (`useDeviceLogCollectAndDownloadState` + debounced `loadDeviceDownloadInfo`).
- **Re-keying a selection/state field in a hook is incomplete until you re-key every DOWNSTREAM consumer of that field.** ENG-1129819: `useDevicesSelection` was re-keyed from `host_info__nsdeviceuid` → `ns_id` (the set `unselectedIds` now holds ns_ids), but 5 cross-page consumers still filtered `unselectedIds.has(row.host_info__nsdeviceuid)` — `DevicesTable.tsx` (`disabledBulkDelete`, `handleBulkActionClick`, `handleBulkDeleteConfirm`, `onOpenTagPanel`) and `DeviceTagBulkActionsPanel.tsx` (`onOperate`). With the set holding ns_ids, `.has(nsdeviceuid)` never matched, so in Select-All mode a deselected row was silently NOT excluded from the fetched bulk set — bulk enable/disable/delete/tag would act on unchecked rows. Existing tests PASSED because their `buildDataset` fixture had a 1:1 `ns_id`↔`nsdeviceuid` mapping, masking the drift; Copilot review caught it. Lesson: `grep -rn "<oldFieldName>\|<setName>"` across the whole feature dir before declaring a re-key done; a test that keys the fixture identically on both fields won't distinguish them.
- **Making an identity field unique: grep ALL identity surfaces, not just the Map (2026-10-05, mf-cfw PR #562 review).** Same lesson as the re-keying entry above, mf-cfw flavor: the A12 fix keyed only `groupFindingsByPolicyGroup`'s Map by the composite `order:name` — review caught that `Accordion.Item id`, `activeIds` (init/search/focus effects), collapsed-row React key, `data-policy-group` (geometry map), testids, and `PolicyDetailPanel`'s `displayNumberByGroup` Map ALL still keyed on the bare name, so the exact duplicate-name scenario stayed broken (both groups toggle together, wrong display numbers, duplicate DOM ids).
  Rule: when a fix changes how an entity is identified, grep every consumer of the OLD identity value (`grep -n groupName`) and switch them all in the same commit — a half-applied identity change is worse than none (it looks fixed).
  Self-inflicted trap in the same fix: `groupKeyOf(finding)` — helper typed `{groupOrder, groupName}` fed a finding (`policy_group_order`/`policy_group_name`) silently produced `"undefined:undefined"` and killed the focus cap-lift; the existing focus-lift test caught it. When a helper's param shape differs from the call site's object, tsc stays quiet if the fields are optional-compatible — always re-run the dependent tests after such a refactor.

## Vitest / Mocks

- **`vi.mock` for `new ClassName(...)` needs an actual class**, not `vi.fn().mockImplementation()`. The mock isn't constructable and emits a warning. Use `vi.mock('lib', () => ({ Foo: class { constructor(x) { this.field = ... } } }))`.
- **`vi.mock` factories are HOISTED above all top-level consts**. The factory body can't reference outer consts (e.g. `BAD_PEM`). Match on stable substrings like `pem.includes('malformed')` instead.
- **A `jest.mock` factory that RECORDS config needs a `globalThis` holder, not a module-level binding (2026-10-05, mf-cfw).** Extends the hoisting trap above: a test that captures `withAuthorization(Component, config)`'s config into `let captured` throws `Cannot access 'capturedConfig' before initialization` (TDZ — factory call happens at wrapper-import time, hoisted above the declaration); switching to `var` degrades to `Cannot set properties of undefined` (import still runs before the initializer).
  Fix: store inside the factory on `(globalThis as Record<string, unknown>).__name = config` — globalThis exists at every phase; read it back in the test body. Applies to any "assert the HOC/gate config" test.
- **Radix / `@ntskui/react` Select can't be driven by `fireEvent.click` in jsdom**. Pointer events + portaled `SelectContent` make `onValueChange` unreachable, so SonarQube branch coverage on `displayValue` / `onValueChange` arrows stays partial. Workaround: `vi.mock('@ntskui/react', ...)` and replace `Select`/`SelectContent`/`SelectItem`/`SelectTrigger`/`SelectValue` with a native `<select>`/`<option>` shim that calls the real `onValueChange` from a synthetic `change` event. Reference impl: `apps/shell/src/features/incidents/dlp/__tests__/StatusControl.test.tsx`. Pair with a sibling probe component reading `useFormContext().watch('field')` to assert form state mutations rather than spying on `onChange`.

## dnd-kit reorder testing in jsdom (webui2 ntskui DataGrid)

- **jsdom cannot complete a keyboard-driven sortable reorder with ntskui `DataGridTableDndRows`.** ntskui wires `KeyboardSensor` WITHOUT `sortableKeyboardCoordinates`, so ArrowDown moves by fixed px and never resolves an "over" droppable in a layout-less DOM. Symptom: aria-live announces "Draggable item N was dropped" (pickup + drop fire) but no "moved over droppable" and no reorder/PATCH — for BOTH broken and working code. So a "no PATCH fired" assertion via keyboard drag is a false positive for any drag bug; it's a jsdom artifact. Use a MouseSensor drag with a `getBoundingClientRect` override giving each `tbody tr` a distinct vertical rect, or test in a real browser.

## Feature Flags

- **`_enabled` suffix is an Angular `NsConstants` artifact, NOT the real flag key**. The raw PHP key (e.g. `nplan4224_jit_provisioning`) is what `/api/v2/ui/platform/featureflags/<name>` accepts. webui2's `useFlag(name)` and mf-client's `default-flag.constant.ts` use the unsuffixed name. Confluence design docs sometimes write the suffixed Angular view — verify against `default-flag.constant.ts` or the PHP model. Failure: `useFlag` returns false; devtools shows 404 on `/featureflags/<name>_enabled`.
- **The `NsConstants.<x>_enabled` name can differ completely from the raw flag alias, not just by suffix.** ENG-1178621 (NPLAN-6283 DNSSEC): the Angular-facing name is `nplan6283_dnssec_enabled`, but the PHP helper (`isNplan6283DnssecEnabled()` in `show_feature_helper.php`) checks `_isFeatureEnabled('dnssec')` — the actual flag/control-flag alias used by `webui-flag-cli` and CM tickets is just `dnssec`, not `nplan6283_dnssec_enabled` or any derivative of it. Always grep `show_feature_helper.php` for the literal string passed to `_isFeatureEnabled()`/`getControlConfigEnabled()` rather than guessing the alias from the NsConstants/JS-global name.
- **mf-client `withFlags` HOC layering: a flag read by a mount-time action must be in the OUTER layer's `requiredFlags`+`compute`, not just the inner one.** SteeringConfigModalV2 wraps `withFlags(Shell, shellCompute/shellRequiredFlags)` outside `withFlags(SteeringConfigContents, compute/requiredFlags)`. The Shell's mount effect calls `openModal()`, which reads `store.featureFlag.<flag>` from a snapshot to gate a side effect (device-tag refill via `fetchDeviceTagsByIds`). If the flag is only in the INNER layer's compute, it's still `false` (initial state) when the outer action runs → side effect skipped on FIRST open. `resetStore` preserves `featureFlag`, so the inner layer populates it and the SECOND open works — classic "works the second time" race. Symptom in ENG-1095443: device-tag chip rendered a ghost "X" (unresolved `field.value.map(...).find(...)` → `undefined`) on first open of an existing steering config; correct on reopen. Fix: add the flag to `shellRequiredFlags` (to fetch it) AND `shellCompute` (to derive the store key) so it's populated before `openModal` reads it. Reuse the shared `computeIsDeviceTagSupportEnabled<T>` helper; `ShellRawFlags` type must include the flag key to satisfy the `DeviceTagSupportRequiredFlags` constraint.

## npm / Yarn Packaging

- **`npm pack` for private scoped packages needs `--registry`**. Default npmjs returns silent exit 1. Pass `--registry https://artifactory-rd.netskope.io/artifactory/api/npm/npm-dev`.
- **npm→Yarn lock migration silently upgrades semver-range deps**. Fresh `yarn.lock` re-resolves all `^x.y.z` ranges. mf-client's `@netskope-ui/match-logic@^1.0.2` jumped to `1.5.0` in PR #1104 with no version-bump PR. Trace via `git log --oneline -- yarn.lock` then `git show <sha> -- yarn.lock | grep -A3 "pkg-name"`.
- **`@netskope-ui/match-logic` `allowMultiple:false` behavior changed in 1.5.0**. In 1.0.6, only individual dropdown items were disabled; the "+" button respected `maxCount`. In 1.5.0, "+" disables after the first entry regardless of `maxCount`, breaking the `allowMultiple: false, maxCount: 16` pattern. Fix: change to `allowMultiple: true` wherever `maxCount` is set. Affected files: `AVCriteria`, `ProcessCriteria`, `FileCriteria`, `RegistryCriteria`, `OsCriteria`, `DeviceTagCriteria`.

## webui2 Monorepo

- **`pnpm --filter @ns/shell` fails** with "No projects matched the filters". The shell app's package name is plain `shell`, not `@ns/shell`. Use `pnpm --filter shell test|lint|typecheck` or `cd apps/shell && npx vitest run <pattern>` directly. Same applies to other apps under `apps/<name>` — package names are unscoped.

## Computed z-index cannot detect a stacking-context cap (2026-09-24)
- Copilot dropdown-clip fix (webui2 PR #2920): reading `getComputedStyle(el).zIndex` showed the
  override applied (100020) yet `elementFromPoint` in the overlap region still hit the covering
  panel. Cause: an ancestor (the floating-ui portal div, z-index 50000 via the Angular host's CSS,
  applied because `body` is `display:flex` so the static div's z-index counts as a flex item) was a
  stacking context below the panel — inner z can never escape an ancestor context.
- Verification pattern for z-index fixes: hit-test a GRID of points over the element's rect
  (`document.elementFromPoint` per point, classify hit as menu/panel/other) — computed-style reads
  alone give false greens. Also verify BOTH mount modes (embedded Angular host vs standalone):
  embedded hid a cascade-specificity loss (prefixwrapped `:is(..., html.balkan-standalone) .x` rule
  is (0,2,1) — the type selector inside `:is()` counts) that standalone exposed.
- Live stacking experiments: setting `position:relative` on a portal container re-anchors its
  absolutely-positioned children (containing-block change) — breaks floating-ui placement. Set
  z-index only; or scope with `:has(> .child-class)` to avoid raising sibling portals.

## Radix Tabs: `fireEvent.click` gives a FALSE PASS; `activationMode:'auto'` selects on focus (2026-09-24)
- mf-cfw ENG-1270524 `TrafficSimulatorPage` (`@netskope-ui/tabs`, Radix-backed): switching the test
  from `await userEvent.click(tab)` to RTL `fireEvent.click(tab)` (to dodge React-18 act warnings)
  made the History-tab test fail with `aria-selected="false"`. Radix `TabsTrigger` defaults to
  `activationMode: 'auto'`, selecting on **focus** via its mousedown→focus handling — a bare
  `fireEvent.click` dispatches only `click`, so no tab change. Worse: the "swaps back to Simulator"
  test still *passed* because Simulator was already selected, i.e. `fireEvent` produces vacuously
  green tab tests. Don't trust a passing Radix-tab test written with `fireEvent.click`.
- Fix that satisfies both: keep `userEvent` (v13 is sync) and wrap it yourself —
  `await act(async () => { userEvent.click(screen.getByRole('tab', { name })); })`. For the initial
  render, `await act(async () => { render(...) })` silences the Radix `Presence` layout-effect act
  warning that plain `render()` emits.

## mf-cfw eslint: `export { default } from './X'` is banned; alias the default import instead (2026-09-24)
- A page-folder `index.ts` written as `export { default } from './TrafficSimulatorPage';` failed
  `no-restricted-exports`: `'default' is restricted from being used as an exported name`. The
  obvious alternative `import TrafficSimulatorPage from './TrafficSimulatorPage'` *also* errors
  (`import/no-named-as-default`) when the module additionally exports that same name.
- Working form: import the default under a **different** local name, then re-export it —
  `import TrafficSimulator from './TrafficSimulatorPage'; export default TrafficSimulator;`
- Also note mf-cfw's `import/order` group order is
  `['index','sibling','parent','internal','external','builtin','object','type']` — so `./x` first,
  `~/x` next, npm packages after that, and **all `import type` lines last**.

## @netskope-ui/table interaction hooks for tests: sort = mouseDown, pagination testids, no row-click prop (2026-09-28)
- Header sort toggles fire on **`mouseDown`** of the th content div (`data-testid="table-column-<accessorKey>"`),
  not click — `fireEvent.click` on the header text silently does nothing (and 'Action'-style labels also appear
  as BasicFilter chip text, so `getByText` is ambiguous anyway). Use
  `fireEvent.mouseDown(screen.getByTestId('table-column-action'))`.
- Pagination controls come from `@netskope-ui/pagination` with `id="table"`: testids are
  `table-pagination-move-next`/`-move-prev`, `table-pagination-page-N`, `table-pagination-select`,
  `table-pagination-container`. The next/prev "buttons" are SVG icons with `role='button'` +
  `aria-disabled` — `toBeEnabled()` passes vacuously on them; assert `aria-disabled="false"` instead, and
  re-query at click time (the node is re-created when pageCount lands via effect).
- The Table has **no row-level click prop** (only `rowActions`/`activeRow`). Repo convention for clickable rows
  is a clickable primary cell (`cursor-pointer font-bold text-action-text` + onClick in the cell renderer) —
  see NetworkLocationHome / DnsProfilesInheritanceGroupsHome. `@netskope-ui/core` Text passes through
  onClick/onKeyDown/role/tabIndex (CommonHTMLAttributes), so the cell can be the affordance directly.

## mf-cfw ApiQueryClientProvider holds a module-level singleton QueryClient — cache leaks across tests (2026-09-28)
- `src/common/providers/ApiQueryClientProvider.tsx` creates ONE `new QueryClient(...)` at module scope. In a
  jest file with several tests, earlier tests' query results stay cached under their param-keyed queryKeys, so a
  later test that reuses the same key can skip the fetch entirely (a pagination test that expects a second call
  with `offset: 10` sees "Number of calls: 1"). Symptom is flaky order-dependent failures.
- Fix for tests exercising refetch/pagination behavior: render with your own fresh
  `new QueryClient({ defaultOptions: { queries: { retry: false } } })` per test instead of ApiQueryClientProvider.
- Related: react-query **structural sharing** clones response objects — a "hands the exact row object through"
  assertion must be `toStrictEqual`, not `toBe`; reference identity is lost at the query layer, not in your code.

## mf-cfw: bare `npx jest` breaks on @netskope-ui ESM; always run `craco test` (2026-09-28)
- `npx jest <path>` fails with `SyntaxError: Unexpected token 'export'` in `@netskope-ui/*/dist/es/*.js` —
  package.json's jest config only registers an @swc/jest transform for `.ts|.tsx`; the `.js` babel transform
  (which handles the transformIgnorePatterns @netskope-ui exceptions) is injected by craco/CRA at runtime.
  Use `CI=true npx craco test --watchAll=false --testPathPattern="<pattern>"`.
- Also: with a symlinked node_modules chain across worktrees, jest stack traces show the *realpath* of the donor
  worktree (`../mf-cfw-eng-XXXX/node_modules/...`) — cosmetic, not a resolution bug.

## mf-cfw dev-preview harness for a fetching component: request-time axios adapter (2026-09-28)
- The `__preview__` route pattern (PolicyGroupListPreview precedent) works for fetching components too: register
  an `api.interceptors.request.use` at the preview module scope (lazy route → only installs when visited) that
  RETURNS `{ ...config, adapter: (cfg) => Promise.resolve({ data: fixture(cfg.params), status: 200, ... }) }`
  for the one URL. eslint `no-param-reassign` bans `config.adapter = ...` — spread a new config instead.
  Fixture honoring offset/sortby/jql makes pagination/sort/filter genuinely interactive in the browser with no
  tenant and no MSW (mf-cfw's MSW dev-server race makes it unreliable; see knowledge/mf-cfw.md).
- **SonarQube `typescript:S4624` (nested template literals) is a MAJOR smell that alone flips webui2's quality gate to ERROR on `new_maintainability_rating`.** 2026-09-29 (PR #3039): `` `${name}${loc ? ` - ${loc}` : ''}` `` — a template inside a template's `${}`. Build optional-suffix labels as `[name, loc ? `- ${loc}` : null, day ? `(${day})` : null].filter(Boolean).join(' ')` (templates only inside the ternaries, never inside another template). Check with `bash ~/.claude/skills/sonarqube-debug/scripts/sq-issues.sh netSkope/<repo> <pr> ALL` — creds now live in `~/.claude/connections/sonarqube.json` with `project_key_template: "ngweb-{repo}"`. Also: a red "SonarQube Scan" check-run whose log says `scan did not succeed (result: cancelled)` is just a superseded run (concurrency cancel from a newer push), not a gate failure.

## mf-cfw / Periskope gotchas from ENG-1338904 (2026-10-08)
- `@netskope-ui/side-panel-v2` 1.2 `topOffset` only sets `top` on the fixed drawer; it stays `h-full`, so the bottom `topOffset` px fall below the viewport. Size panel content `calc(100% - offset)` yourself (NetworkLocation/DNS consumers carry the same latent bug).
- CRA jest treats EVERY file under `__tests__/` as a suite — a shared fixture there fails "must contain at least one test". Put fixtures in `__fixtures__/` (and import types via `~/` alias; relative parent imports are lint errors outside test files).
- In a suite that mocks axios, `jest.requireActual('@netskope-ui/utils')` crashes at load (`C.default.create is not a function`). Mock only the used export: `jest.mock('@netskope-ui/utils', () => ({ useFeatureFlag: () => mockFF() ?? DEFAULT }))` (the `??` default survives CRA resetMocks).
- Backend may list one `policy_id` in several Analyze categories — never use policy_id alone as a finding identity (use `category:policy_id`).

## Embedded MFE layout shift: margin-right on abs-pos `.ns-wrapper` is ignored (2026-09-25)
- webui2 copilot widget embedded in Angular shell: tried `margin-right: 400px` on `#ns-content-wrapper`
  (child, `width:100%` → overflows, no shrink) then on `.ns-wrapper` (computed margin applied but
  rect unchanged). Root cause: `.ns-wrapper.authenticated` is `position:absolute; left:200px;
  width:calc(100% - 200px)` (app.component styles) — over-constrained abs-pos ignores margin-right
  and `right`. Only lever: rewrite `width` inline as `calc(100% - 200px - 400px)`.
- Also: `flex: 1 1 auto` from `body .ns-wrapper` does NOT make it a flex item for sizing once
  `position:absolute` removes it from flow. Computed width mid-transition (300ms) looked like the
  margin "worked" — always re-probe AFTER transition ends before concluding.
- jsdom normalizes `calc(100% - 200px - 400px)` → `calc(100% - 600px)`; assert the normalized form.

## CSS: `h-full` inside a `<td>` with no definite ancestor height resolves against the viewport, and native table row-height sharing spreads that to every sibling column (2026-09-26)
- webui2 IPSec/GRE Site tables: two cell wrapper `<div>`s (select checkbox, row-actions ellipsis) used
  Tailwind `h-full` (`height: 100%`). On pages with few rows and no scroll-container height, Chrome had no
  definite ancestor height to resolve the percentage against and fell back to the viewport height (~720px
  measured). Because a native `<tr>` forces ONE shared height across all its `<td>`s, the entire row —
  every column, not just the two offending ones — inflated to that viewport-derived height (measured
  768px on a real tenant for what should be a ~116px 2-row cell).
- Diagnosis pattern: `document.querySelector('table tbody tr').getBoundingClientRect()` to catch the
  inflated row, then walk each `<td>`'s `firstElementChild.getBoundingClientRect().height` to find which
  column(s) actually want the oversized height (`h-full` present) vs which render at their true natural
  size (no `h-full`, just `flex flex-col`) — the row height is the MAX across all cells, so only the
  culprit's own inner-div height differs from the rest.
- Fix: drop `h-full` from the offending divs; the `<td>`'s own `align-middle` (or `vertical-align`)
  already centers content once the row's height is correctly content-driven — no centering behavior is
  lost. When the offending wrapper is a widely-shared component (used by other tables that DO have a
  scroll container and don't hit this bug), scope the fix locally via `cloneElement` overriding
  `className` on the shared renderer's output, rather than editing the shared component itself.
- **This fix alone did NOT reproduce or fix the user's actually-reported visual bug** — see the next
  entry for the real cause and the "reproduced X, called it done" trap this created.

## `truncate` inside nested flex wrappers silently no-ops without `min-w-0` on EVERY flex-item ancestor (2026-09-28)
- webui2 tunnel POP column: master's #2999 added `truncate` + `min-w-0` to `PopNameDisplay`, but the caller's `renderPop` wrapper `div.flex items-center gap-1` kept default `min-width:auto` — stayed 216px in a 180px cell, text overlapped next column. User said "still not fixed" after rebase; my earlier SubRowCell fix had become moot post-rebase and I hadn't re-verified.
- Diagnose: walk up from the `.truncate` span printing `getBoundingClientRect().width` + computed `minWidth`; first ancestor wider than its container with `minWidth: auto` is the culprit. Fix: `min-w-0` there.
- Rule: after rebasing a visual fix onto a master that touched the same component, re-run the live repro (same interaction state) before re-claiming the fix.

## Deferred-promise jest mocks + chained `expect().rejects` re-invoke the fn; second call gets undefined (2026-10-05)
- `mockPost.mockResolvedValueOnce(body)` followed by TWO assertions (`await expect(fn()).rejects.toThrow(msg)` then `await expect(fn()).rejects.toBeInstanceOf(...)`) fails the second: each `expect(fn())` CALLS fn again, the Once-mock is consumed, second call resolves undefined → `resp.data.data` throws TypeError, not the guarded AxiosError.
- Fix: `mockResolvedValue` (non-Once) or catch once: `const caught = await fn().then(() => { throw new Error('expected reject') }, (e) => e)` then assert everything on `caught`. Mirrors trafficSimulator.api.test.ts's pattern.
- Also: error-dialect it.each rows need a per-row expected message — a body with no `errors` array falls through `parseErrorResponse` to the generic i18n "Something went wrong", so `toBe('Permission denied')` only holds for bodies that carry an errors array.

## Angular `*ngIf`-mounted MFE wrapper loses a same-tick window event — wait for the MFE's READY (2026-10-05, ENG-1338904)
- webui `openAnalyzePanelWithMode` set `showAnalyzePanel=true` and dispatched `ANALYZE_SIDE_PANEL_OPEN` synchronously; the wrapper renders on a later CD pass and React registers its listener in a `useEffect`, so the first click was lost (every reopen too, since CLOSE unmounts). mf-cfw already dispatched `ANALYZE_SIDE_PANEL_READY`; webui just never listened. Fix: park the mode, flush one OPEN on READY, reset on CLOSE (PR webui#19052). Grep for the counterpart event before inventing a `setTimeout` workaround.
- Jest spying `window.addEventListener`/`dispatchEvent` to fire the real listener was flaky in that spec; assert `addEventListener` was called with the bound ref and invoke `component.boundOnX(event)` directly.
- Devbox gotchas: `ns.globals.nplan6460_policy_analyzer_enabled` (from `isNplan6460PolicyAnalyzerEnabled()`) AND `isRunAnalyzeCfwEnabled()` both gate the button, read at bootstrap, so a full reload is needed after a flag edit. A worktree's `dev-lazy` bundle can be stale vs HEAD (verify the served button label before using it as a baseline). The ns-selector dropdown often needs two clicks after reload. Real CLOSE needs the results panel, so with `/analyze` 403 dispatch CLOSE by hand. `mkdir -p /tmp/claude` before redirecting background logs there.
- Background sub-agent `$TMPDIR` is per-sandbox: a log written unsandboxed lives under `/var/folders/.../T/`, not the sandbox `$TMPDIR` (grep found "No such file"). Use `/tmp/claude/` for logs you need to read back.

## @netskope-ui/dropdown closes by UNMOUNTING menu content — reset menu-local UI state via an unmount-cleanup sentinel (2026-10-18)
- AddCriteriaMenu's search reset on the trigger's `onClick` never fired on reopen (live repro: type, Escape, reopen — filter still applied). `Dropdown.Root` has no `onOpenChange`, but it unmounts its content children when closed, so a tiny `<ResetSearchOnClose reset={fn} />` rendered inside the menu whose `useEffect(() => reset, [reset])` cleanup fires exactly at close is the reliable reset point (state itself lives in the always-mounted parent).
- Testing it needs a STATEFUL dropdown mock that actually unmounts content on toggle; nesting depth must come from React context — a module-level depth counter re-runs on re-render and mislabels the outer Root ("Found multiple elements by dd-outer-trigger").
- "Why not a useUnmountReset hook?" (user asked): a hook borrows the LIFECYCLE OF THE COMPONENT THAT CALLS IT. Calling it in the always-mounted parent (where the state lives) means cleanup never fires on menu close; the only correct host is a component rendered INSIDE the menu content — which is the sentinel itself. The hook version still needs the sentinel to call it from, so with one usage site it's pure indirection. One-liner: unmount lifecycle is a property of a component, not of a hook.

## @netskope-ui/core Popover: root onClose does NOT wire the header X — Popover.Header has its own onClose (2026-10-19)
- The X button in Popover.Header is rendered by the Header subcomponent and fires the HEADER's `onClose` prop; the root `Popover onClose` only handles outside-press dismissal. Passing onClose only at the root leaves the X dead (live-caught on the simulator history View All popover). Pass the same handler to both. Verified from dist: Header defaults `showCloseButton` to true and renders the X itself.

## MSW `server.use` overrides are LIFO — register AFTER the default handlers or the fixture wins silently (2026-10-19)
- In a vitest suite that calls a `setup()` helper doing `server.use(...featureHandlers)`, an override registered BEFORE setup (e.g. `server.use(http.patch(..., 412))` then `setup()`) is PREPENDED-BY-ORDER-OF-REGISTRATION such that the later feature handlers take precedence: the PATCH hit the fixture 200, mutateAsync resolved, modal closed, and the assertion on the conflict banner got `undefined`. Looked exactly like a product-code bug (error state never set) — cost a debug round before a state probe showed `state.kind === 'closed'` (success path ran).
- Fix: always register route overrides AFTER the setup that installs the base handlers (matches the existing "Register the 500 AFTER setup() so it prepends and wins" comment pattern in useConfigModalController.test.tsx). Quick discriminator for "did my override even fire": probe post-submit state — success/close vs error means fixture won.
