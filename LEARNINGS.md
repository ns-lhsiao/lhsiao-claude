# Learnings

Topical reference. Each bullet is a self-contained lesson: what failed, why, and the correct approach.

## Caveman Comments in Source Files

- **Rule exists in global CLAUDE.md §Source Code Comments but kept drifting.** Symptom: wrote full-prose `#` comments in `.github/workflows/pr-sidecar.yaml` while caveman full was active. Fix: before writing ANY file with comments, explicitly apply caveman compression to comment prose — drop articles/filler/hedging, fragments OK. Code identifiers (function names, paths, flags) stay exact. Applies to all file types: TS `//`, YAML `#`, JSDoc bodies. Commit messages and PR bodies stay normal prose regardless.

## Git show redirect / RTK hook

- **`git show <branch>:<file> > /tmp/out` can silently produce a 0-byte file** under the RTK shell hook (the rewrite mangles the redirect target). Symptom: `wc -l /tmp/out` shows 0 while the same `git show` piped works. Fix: use process substitution for cross-branch file compares — `diff <(git show origin/A:path) <(git show origin/B:path)` — instead of writing temp files. Confirmed 2026-07 during ENG-1127021 triage.

## Worktrees, node_modules, Lockfiles

- **mf-client worktree**: symlink `node_modules` from primary (`ln -s ../mf-client/node_modules node_modules`). `npm install`/`npm ci` mutates `package-lock.json` and wastes minutes. Tests, eslint, prettier, craco all resolve through the symlink.
- **pnpm worktree**: symlink BOTH the root `node_modules` (hosts `lint-staged`) and each `apps/<app>/node_modules` (hosts `vitest`) to the primary checkout. Failure: `Command "lint-staged" not found` on commit, or `vitest: command not found`. If `pnpm install` ran in the worktree, `rm -rf` the real `node_modules` before re-linking.
- **pnpm add in a worktree** fails with `ERR_PNPM_UNEXPECTED_VIRTUAL_STORE` — the worktree's `node_modules` is a symlink to the primary's `.pnpm` store. Run `pnpm --filter <pkg> add <dep>` in the **primary** checkout instead. Edit `package.json` in the worktree first if you want it committed alongside the feature.
- **mf-client worktree husky**: `.husky/_/husky.sh` is created by `prepare` during `npm install` and not tracked. Before first commit: `mkdir -p .husky/_ && cp ../mf-client/.husky/_/husky.sh .husky/_/husky.sh`. Don't bypass with `core.hooksPath=/dev/null` — lint-staged runs prettier fixes during commit.
- **webui worktree**: For Angular tests, `cd src/webui/neo && npm ci`, then `./node_modules/.bin/jest --testPathPattern=...`. Don't use `npx jest` (pulls jest 30 which renamed to `--testPathPatterns`; project pins jest 29).
- **webui PHP tests**: symlinking `vendor/` from primary causes `Cannot redeclare` errors. Copy changed files INTO primary, run `cd tests && php ../vendor/bin/phpunit --configuration phpunit.xml --filter='...'`, restore. The `--configuration` flag is required for `APPPATH` bootstrap. **WARNING**: only safe when primary is on the same base commit as worktree — otherwise the file copy silently reverts adjacent code (e.g. tests added by a recent PR). Failure signature: `git diff origin/develop` shows tests being deleted that you never touched.
- **webui PHP tests — `git worktree add --detach` also fails**: creating a detached worktree at the branch tip and symlinking vendor from primary still triggers `Cannot redeclare rangeMatch()`. Root cause: vendor's internal autoloader resolves helper paths relative to primary's filesystem root, so both the detached worktree's `application/helpers/` AND primary's are loaded. Same failure as direct symlink in a named worktree. No workaround — copy-into-primary is the only viable approach. Do NOT retry worktree-based phpunit runs for webui PHP.
- **`npm install` in worktrees** produces large `package-lock.json` diffs from dependency re-resolution. Always `git checkout -- package-lock.json` before committing.
- **webui2 worktree recovery when primary checkout deleted**: dangling `node_modules` symlinks (worktree → `/Users/lhsiao/ns/git/balken/webui2/...`) break Vite with `vite: command not found`. Fix: `rm node_modules apps/shell/node_modules` → `pnpm install` in worktree (becomes self-contained) → `pnpm --filter @ns/api build` (required after fresh install or `apps/shell` errors with `@ns/api/* could not be resolved`). pnpm's post-install script also rewrites `apps/shell/.env.local` to the default React-only template — re-write hybrid config (`PUBLIC_LOCAL_API_PATHS=/api/v2/balkan,/api/v2/rbac`, `PUBLIC_PATH_PREFIX=/mf/shell`, `ANGULAR_DIST_DIR=...`) before restarting Vite.

## Branch & Commit Conventions

- **mf-client + webui branches**: `pr/ENG-XXXXXX/kebab-slug`. CI rejects the global `<user>/<ticket>-<slug>` default. See `https://nsgo.to/branchingstrategy`.
- **mf-client + webui commits**: `ENG-XXXXXX: Subject` (project-key prefix with colon). NOT Conventional Commits. Allowed prefixes per `commitlint.config.js`: `ENG`, `NG`, `EP`.
- **mf-client default branch is `master`** — `git fetch origin main` fails. Verify with `git remote show origin`.
- **mf-client push target**: always `origin` (`netSkope/mf-client`), NOT a personal fork. CODEOWNERS / shared CI assume upstream-branch PRs.
- **Check Jira fixVersion for base branch**: a fix targeting `release/202605.2` must be based on that release branch, not `master`. Wrong base pollutes the PR diff and forces a reset+cherry-pick.
- **webui in-flight fixVersion → `develop`**: a `Release<N>` branch is only cut at code-freeze. Before that, basing on `develop` is correct; track the SHA for later cherry-pick.
- **mf-client staging PR pattern**: when fix targets `release/YYYYMM.N`, also cherry-pick onto `origin/staging` and open a separate PR named `pr/ENG-XXXXXX/<slug>-staging` for QA validation on qa01.
- **mf-client is a separate git repo** inside `netskope-ng-base/frontends/mf-client`. Always `cd` in and `git remote -v` before running git/gh commands. Release branches exist on the mf-client remote, not the parent.
- **Investigate on the deployed branch**, not the primary checkout. For env-specific bugs, confirm which branch is deployed (e.g. mf-client `staging` → qa01) and analyze code via `git show <branch>:<file>`.

## PR & GitHub Workflow

- **Check PR state before pushing follow-up commits**. `gh pr view <num> --json state` — if MERGED, the commit becomes orphaned. Also when the user starts a squash-merge mid-edit, anything pushed between "merge clicked" and "squash completed" gets dropped. Confirm via `gh api repos/OWNER/REPO/compare/main...<branch>` — "behind by N, ahead by 0" = already merged. Failure: scheduled workflow still has the bug you "just fixed."
- **Transferred-repo origin URL lies**: a fork transferred to upstream still shows the old URL but pushes land upstream. Confirm with `gh pr view <num> --json headRepositoryOwner,headRepository`. Stop the redirect notice via `git remote set-url origin git@github.com:netSkope/<repo>.git`.
- **`gh pr edit` needs `read:project` scope**. Use REST instead: `gh api repos/OWNER/REPO/pulls/N -X PATCH -f body="..."`. The `-X PATCH` is required.
- **Moving a branch across remotes** can't retarget an open PR. Workflow: `gh pr close <num>` → `git push origin <branch>` → `gh pr create --head <branch>`. Delete the old-remote branch.
- **mf-client PR template**: H2 sections with emoji prefixes — `## 🎯 Jira Issue`, `## 📝 Description`, `## 🚧 Type of Change`, `## ✅ Checklist`, `## 🖼️ Screenshots`, `## 📌 Additional Notes`. Mirror `.github/pull_request_template.md` exactly.
- **webui PR template**: H4 sections (NOT H2) — `#### 🎯 Jira Issue`, `#### 📝 Change Description`, `#### 🚧 Type of Change`, `#### ✅ Checklist`, `#### 🧪 Manual Testing Done`, `#### 🖼️ Screenshots/Videos`, `#### 📌 Additional Notes`.

## Jira & CM API

- **`POST /rest/api/3/search` is removed** — use `/rest/api/3/search/jql` (same body).
- **Jira `assignee` on create gets overridden** by component default assignee. Always follow create with `PUT /rest/api/3/issue/<KEY>/assignee -d '{"accountId":"..."}'` (HTTP 204).
- **QA Test Recommendations field** is `customfield_12503`, accepts ADF doc (not plain text). Discover field IDs with `GET /issue/<KEY>?expand=names`.
- **CM `security` field** can't be set on create ("not on appropriate screen"). Omit it.
- **CM `customfield_16792` (Type of Change)** is a cascading select: `{"id":"PARENT","child":{"id":"CHILD"}}`. Software > Feature Flag = `13191` / `28422`.
- **Atlassian MCP fallback to curl**: tools may not be exposed even when `mcp.json` configures the server. Use `curl -s -u "USER:TOKEN" "https://SITE/rest/api/3/..."`. Env vars: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_USER_EMAIL`, `ATLASSIAN_SITE_URL` (NOT `ATLASSIAN_EMAIL`/`ATLASSIAN_SITE`).
- **Those `ATLASSIAN_*` vars are NOT exported into the shell** — they exist only inside `~/.claude/mcp.json` at `mcpServers.atlassian.env`. Symptom: `curl -u "$ATLASSIAN_USER_EMAIL:$ATLASSIAN_API_TOKEN"` returns non-JSON HTML → `json.decoder.JSONDecodeError: Expecting value: line 1 column 1`; `env | grep ATLASSIAN` returns nothing; `${!v}` gives zsh `bad substitution`. Fix: read the values inside a `python3 -c` one-liner (`json.load(open(os.path.expanduser('~/.claude/mcp.json')))['mcpServers']['atlassian']['env']`) and build the Basic auth header there. Never echo them.
- **Confluence page fetch by ID**: `GET /wiki/api/v2/pages/<id>?body-format=storage` with the Basic header above. The `/wiki/rest/api/content/<id>?expand=body.storage` v1 path also works.
- **`~/.claude/mcp.json` contains plaintext tokens** — never commit. The config repo's `.gitignore` excludes it.

## Webui PHP & Testing

- **`webui` worktree has no `vendor/` and no working symlink fix for PHPUnit.** `composer` isn't installed on this machine; `brew install composer` drags in 28 unrelated dependency upgrades — don't. Instead `php -r "copy('https://getcomposer.org/installer','composer-setup.php');"` then `php composer-setup.php --install-dir=/tmp --filename=composer.phar` gets a clean `composer.phar` with zero brew footprint. But primary's `composer.lock` (`src/webui/system_framework/composer.lock`) pins packages needing PHP ≥8.2 (`symfony/filesystem` v7.4.8, `finder`, `process`) alongside one needing ≤7.x (`cache/cache` 2.0.x-dev) — no single PHP satisfies the whole lock file's platform check, and the repo's stated runtime is 8.1 (`php@8.1` via homebrew, at `/opt/homebrew/opt/php@8.1/bin/php` — bare `php` on this machine resolves to 8.5.8, NOT 8.1, despite `which php`/`php -v` in a plain shell showing 8.1.32 elsewhere in the session; the two didn't agree, don't trust one check). Separately, symlinking primary's already-installed `vendor/` into the worktree (the usual node_modules-style fix) causes `PHP Fatal error: Cannot redeclare rangeMatch()` — the same helper file loads once via the worktree's own `application/helpers/` and once through a path that resolves back through the symlink into primary, so CodeIgniter's helper loader double-includes it. Copying files into primary and running there (the documented fallback for webui PHP tests) is unsafe when primary's checked-out commit predates the worktree's base by any meaningful margin — silently reverts adjacent files. Net effect: as of 2026-07, there is no clean way to execute PHPUnit for a `develop`-based webui worktree on this machine; fall back to `php -l` + static review and say so explicitly rather than claiming tests ran.
- **Use `$this->callService()` for testability**, not the global `callService()`. `NS_Model::callService()` delegates via `call_user_func_array` and is mockable via `getMockForModel('...', ['callService'])`.
- **Tenant migrations don't ship with PHPUnit tests**. Files under `system_framework/application/migrations_ui/tenant/` have no companion tests by convention. Validation is operational; record the matrix in QA Test Recommendations on the ticket.
- **`showErrorToast` first arg must not be `null`** — accesses `error.message` without a guard. Pass `{}` when there's no real error.
- **`DevicesFilters.test.tsx` mocks the entire `devices.helper` module** — adding a new export will fail at test time. Compose new logic into an already-mocked function instead of adding a new import.
- **mf-client uses Jest via craco**, not vitest. `npx vitest` can't resolve `~/` aliases. Run `npm test -- --testPathPattern='<pattern>'`.
- **mf-client `test:coverage` needs `--max-old-space-size=8192` and `--forceExit`**. Default 4 GB OOMs at ~2450 tests with `--runInBand`. Jest hangs after passing due to leaked async handles (valtio devtools, MSW).
- **Always lint changed files before committing** — Prettier multi-line formatting errors aren't caught by Jest. Run `npx eslint <files>` especially when bypassing pre-commit.
- **SonarQube new-code coverage = diff lines only**, not whole-file %. Verify locally with `--coverageReporters=json` against `git diff` line numbers.

## Playwright & Dev Proxy

- **Default headless Chromium is rejected** by webui ("Browser Not Supported"). Use `chromium.launch({ channel: 'chrome' })` and a real Chrome user-agent.
- **Webui hash routing uses `/ns#/...`** — `/#/...` is 404. After login at `/locallogin`, the app redirects to `/ns#/dashboard`.
- **SPA navigation**: `page.goto()` triggers a full reload even for hash-only changes (loses session, re-bootstraps mf-client for 30–60s). Use `page.evaluate(() => { window.location.hash = '#/...'; })` instead.
- **Login flow**: don't `waitForTimeout` after `#btn-sign-in`. Use `page.waitForFunction(() => !window.location.hash.includes('/login'), { timeout: 30000 })`. Fresh tenants show a welcome wizard — dismiss via `text=skip this step`. Credentials in `~/.claude/skills/mf-client-playwright/.env`.
- **Devices page selectors**: loads in **Basic** mode; click `[data-testid="filter-toggle-advanced"]` (also the readiness signal — mf-client takes 30–60s) then `[data-testid="filters-advanced-filter-input"]`. "Save as..." = `[data-testid="saved-filters-save-as"]`.
- **Playwright not in mf-client `node_modules`** — `npx playwright --version` works (temp download) but `require('playwright')` fails. Install in `/tmp/pw-runner` with `npm init -y && npm install playwright`.
- **dev proxy lives at `/Users/lhsiao/ns/git/development-proxy`**, NOT inside netskope-ng-base. `npm run dev` listens on `:9797`. Tenant config: `src/config.ts` → `fallbackServer.host`. Custom mocks: `app.get()`/`app.post()` handlers in `src/main.ts` BEFORE the proxy middleware.

## Feature Flags

- **`_enabled` suffix is an Angular `NsConstants` artifact, NOT the real flag key**. The raw PHP key (e.g. `nplan4224_jit_provisioning`) is what `/api/v2/ui/platform/featureflags/<name>` accepts. webui2's `useFlag(name)` and mf-client's `default-flag.constant.ts` use the unsuffixed name. Confluence design docs sometimes write the suffixed Angular view — verify against `default-flag.constant.ts` or the PHP model. Failure: `useFlag` returns false; devtools shows 404 on `/featureflags/<name>_enabled`.

## v2 / API Contract Hygiene

- **Tenant edge does NOT publish OpenAPI specs**. All discovery paths return 404 (`/apidocs/swagger.json`, `/v2/api-docs`, etc.). Workaround: `gh pr diff <num> --repo netSkope/api-gateway-endpoints` returns the YAML directly.
- **v2 live probe is a partial sample, not a schema**. Fields absent from sampled rows aren't necessarily rejected. Cross-reference Confluence §4.x schema and legacy Angular payload before dropping a field. v2 explicitly rejects unknowns with 422 `"unexpected property"`. Failure: 422 on create after "fixing" a payload, or fields silently disappear on edit round-trip.
- **Hand-rolled fetchers + hand-rolled MSW = silent contract drift**. TS sees the hand-typed response, MSW serves the hand-built shape, vitest passes, bug appears live. Mirror a proven legacy fetcher's exact request envelope and `data`/`result` wrapper.
- **Verify wire unit before refactoring on field name**. `maxTimeoutSeconds` may carry minutes. Don't multiply by 60 everywhere on a name alone — probe a live config first. Failure: a value of `30` displays "30 seconds" in v2 but "30 minutes" in v1.
- **Form unit dropdowns don't auto-convert**. `min` ↔ `hr` toggles are cosmetic unless `onChange` multiplies by 60 and `value` divides by 60. Keep storage normalized to one unit; translate at the input boundary; adjust `min`/`max` per unit.
- **bulkdelete request shape** (`/clientconfiguration/client/config/bulkdelete`): `{ action: "delete", scope: "selective", ids, idempotencyToken }`. Missing any → 422. Cap 250 ids/req; rate limit 4 req/sec (vs 50/sec for per-item CRUD).
- **bulkdelete 202 response**: only `jobId` is load-bearing. **bulkstatus response**: `{ jobId, status, action, totalAffected (int64), message, createdAt, completedAt }` — NO `processed`/`total`/`errors[]`. Status enum has 5 values: `accepted | in_progress | completed | failed | cancelled`. A poll loop terminating only on `completed|failed` spins until timeout on `cancelled`.
- **Idempotency token belongs at the call site**, not inside the HTTP function. Generating in the fetcher creates a new token per retry, defeating the purpose. Generate in `mutationFn` or via `useRef`, pass as parameter.
- **`/api/v2/users/getgroups` SAML field semantics are inverted**. For `collectionId: 'default'`: `row.id` is BOTH the wire id AND the user-visible group name (the substring filter `id.co` matches against it; legacy mf-client `searchV2UG` maps both label and value from `row.id`). `row.displayName` is NOT used for this collection — preferring `row.displayName` over `row.id` paints a non-name string into the picker and submits it as the wire id, triggering a misleading "OU/Group already exists" on save. For `collectionId: 'jit_default'` (SAML): `row.scimId` = wire id, `row.id` = display name. Also: scimId batch lookup MUST include `collectionId: 'jit_default'` in the filter or rows render as raw UUIDs.
- **Angular `processMonthlyVersions`**: legacy v1 `specificversions` is a SUPERSET of `goldenversions`. The monthly dropdown = `specificversions.filter(v => !goldenSet.has(v))`. v2 `/client/versions` flips the schema — each release carries `golden` and `specific` independently; the v2-equivalent is `release.specific && !release.golden`. Aliasing `monthly = specific` lists golden majors as monthly hotfixes.

## React, React Query, TanStack Table

- **TanStack Table `columns` memo must include closed-over data in deps**. A cell function closing over a prop/state without listing it freezes with the initial captured value — async lookups (scimId → name, user profiles) render the raw id forever. ESLint `exhaustive-deps` and React Compiler are often disabled around `useReactTable`.
- **React Query `isFetching` has a one-render gap when `enabled` flips true**. The render where `enabled: true` first evaluates is NOT the render where `isFetching: true` flips on. Gates like `hasData > 0 && !query.data && query.isFetching` let the stale value paint for one frame. Fixes: gate on `!query.data`, or track pending in local state, or fix the upstream memo-dep bug.
- **`ref.current` as a prop is an anti-pattern**. Refs don't trigger re-renders, so the value reflects the previous render. Use stable props derived from props/state for render-time decisions (e.g. a `mode` prop set once per modal-open cycle).
- **`aria-disabled` doesn't trigger CSS `:disabled`**. ntskui's Checkbox/Select/Combobox triggers render as `button[role=checkbox]` with `aria-disabled="true"`, NOT the HTML `disabled` attribute. Tailwind's `disabled:` variants don't match. Apply `opacity-50 cursor-not-allowed` to your wrapping container. Test trap: `toBeDisabled()` may not fire — assert `el.getAttribute('aria-disabled') === 'true'`.
- **`lodash.debounce(fn, ms)` defers ALL side effects in the body, including loading-flag flips**. If your fetcher writes `store.loading = true` inside the debounced function and the caller renders against `store.loading`, the flag stays `false` for the first `ms`. UI gates that read `!loading` will permit interaction during that window. Fix: flip the loading flag synchronously at the call site (or in a thin wrapper), and reset stale per-entity slices of the store on entity change so a previous entity's "ready" data can't render against the new one. Failure signature: feature works after waiting; broken on immediate click. Repro: ENG-1029558 (`useDeviceLogCollectAndDownloadState` + debounced `loadDeviceDownloadInfo`).

## Vitest / Mocks

- **`vi.mock` for `new ClassName(...)` needs an actual class**, not `vi.fn().mockImplementation()`. The mock isn't constructable and emits a warning. Use `vi.mock('lib', () => ({ Foo: class { constructor(x) { this.field = ... } } }))`.
- **`vi.mock` factories are HOISTED above all top-level consts**. The factory body can't reference outer consts (e.g. `BAD_PEM`). Match on stable substrings like `pem.includes('malformed')` instead.
- **Radix / `@ntskui/react` Select can't be driven by `fireEvent.click` in jsdom**. Pointer events + portaled `SelectContent` make `onValueChange` unreachable, so SonarQube branch coverage on `displayValue` / `onValueChange` arrows stays partial. Workaround: `vi.mock('@ntskui/react', ...)` and replace `Select`/`SelectContent`/`SelectItem`/`SelectTrigger`/`SelectValue` with a native `<select>`/`<option>` shim that calls the real `onValueChange` from a synthetic `change` event. Reference impl: `apps/shell/src/features/incidents/dlp/__tests__/StatusControl.test.tsx`. Pair with a sibling probe component reading `useFormContext().watch('field')` to assert form state mutations rather than spying on `onChange`.

## webui2 Monorepo

- **`pnpm --filter @ns/shell` fails** with "No projects matched the filters". The shell app's package name is plain `shell`, not `@ns/shell`. Use `pnpm --filter shell test|lint|typecheck` or `cd apps/shell && npx vitest run <pattern>` directly. Same applies to other apps under `apps/<name>` — package names are unscoped.

## npm / Yarn Packaging

- **`npm pack` for private scoped packages needs `--registry`**. Default npmjs returns silent exit 1. Pass `--registry https://artifactory-rd.netskope.io/artifactory/api/npm/npm-dev`.
- **npm→Yarn lock migration silently upgrades semver-range deps**. Fresh `yarn.lock` re-resolves all `^x.y.z` ranges. mf-client's `@netskope-ui/match-logic@^1.0.2` jumped to `1.5.0` in PR #1104 with no version-bump PR. Trace via `git log --oneline -- yarn.lock` then `git show <sha> -- yarn.lock | grep -A3 "pkg-name"`.
- **`@netskope-ui/match-logic` `allowMultiple:false` behavior changed in 1.5.0**. In 1.0.6, only individual dropdown items were disabled; the "+" button respected `maxCount`. In 1.5.0, "+" disables after the first entry regardless of `maxCount`, breaking the `allowMultiple: false, maxCount: 16` pattern. Fix: change to `allowMultiple: true` wherever `maxCount` is set. Affected files: `AVCriteria`, `ProcessCriteria`, `FileCriteria`, `RegistryCriteria`, `OsCriteria`, `DeviceTagCriteria`.

## ngweb_mf / Nginx

- **`ngweb_mf` upstream returns 401 (NOT 404) for missing `x-npe-env` builds**. The `@mf_npe_fallback` only fires on `error_page 404`, so env-prefixed paths are served as final 401 (auth-off paths) or rewritten to the 174 KB static `/error_pages/404.html` (via `error_page 401 =404`). `/npe-ngssl-check` Mode A/B audits only check static wiring — pair with a live curl to `/mf/<app>/build-info.json` (auth-off) comparing no-header vs `x-npe-env: npe-anything`. Real fix: widen `error_page 401 404 = @mf_npe_fallback` gated by `$http_x_npe_env`, or fix the upstream to return 404.
- **`auth_request` failures masquerade as 404** via chained `error_page`. An unauth'd curl to `/mf/<app>/remoteEntry.js` returns 404 with a 174 KB HTML body — that's `auth_request` 401 rewritten by `error_page 401 =404 /error_pages/404.html`. To isolate auth from upstream behavior, probe `/mf/<app>/build-info.json` (`auth_request off`). Tell: a 404 with multi-hundred-KB HTML; real upstream 404s are short.

## Ops: K8s, Helm, Slack, Bash

- **`helm list -n ngweb-v2` misses YAP-deployed sidecars**. Ground truth is `kubectl get deploy -n ngweb-v2`. Filter by Deployment-name convention `<service>(-npe-<suffix>)?`. The `app.kubernetes.io/instance` label only works for helm-deployed sidecars.
- **Webui MP-Prod namespace**: `<dc>-mp-prod--webui` (e.g., `dfw3-mp-prod--webui`). The `c4-<dc>` style is AM2-specific or outdated. Confirm with the engineer before writing namespace names into a CM.
- **Slack `section.text` with `\n` separators can collapse into one line** (client-dependent). For lists, emit one `section` block per row (optionally with `divider` blocks). Also a prerequisite for per-row `accessory` buttons.
- **Multi-line jq in shell needs trailing `\` on the closing-quote line**. Bash tolerates raw newlines INSIDE `'…'`, but once the closing `'` appears, a bare `|` on the next line is a syntax error. Fix: `] | @tsv' \` then `| sort)`. Validate with `bash -n` on the `run:` block before pushing YAML.

## Process: Debugging & Design

- **When stuck after 2–3 fix attempts, delegate to a subagent**. Pass repro steps, every relevant file, each rejected hypothesis, and a length cap (≤400 words). Subagents read fresh without main-thread framing bias and find closure/memo/cache issues. Failure signature: three consecutive fix commits that don't change user-visible behavior — revert and delegate.
- **Design before fixing parity bugs**. If the fix touches >2 files OR crosses a serialization boundary OR depends on a flag whose v1 wiring isn't already in front of you, spawn a sub-agent to surface v1 truth first. Cite v1 file:line in the commit. Failure: shipping then needing immediate follow-up because round-trip parity broke.
- **Customer-reported `affectsVersion` is observation-time, not introduction-time.** Tickets default to "the version where QA noticed it"; that may be years after the bug shipped. Before calling something a regression, pickaxe the defective code path AND verify the bug is byte-identical on `develop`, the prior `Release<N-1>`, and `Release<N>`. If identical across all three, it's pre-existing debt re-surfaced — flag the delta on the ticket. Repro: ENG-1031514 (reported affectsVersion 132.0.0; bug actually shipped with LBS column default in 2019, byte-identical on develop / Release132 / Release137 / Release138).
- **Pickaxe by symbol AND literal — strings get renamed.** `git log -S '<literal>'` misses commits where the literal was edited. ENG-1031514: writer's `notes` parameter changed `'added from app_info'` → `'default ssl pinned app'` in ENG-614741 (2025-04-08); customer rows seeded earlier still carry the old literal, but pickaxe on the new literal hides the writer's full history. Trace by function name (`addNewFromAppInfoToTenantDb`) plus a stable structural marker (the SQL skeleton, table name) and corroborate.

## Webui Steering Exceptions / bypass_settings_v2

- **`bypass_settings_v2.dynamic_steering_mode` defaults to `-1` (NOT NULL).** Any INSERT that omits the column lands as `-1`. UI list query for dynamic-steering configs filters `WHERE dynamic_steering_mode IN (0,1)` (`Steering_exception_model::getSSLAppsConfigNew`), so `-1` rows are invisible to the admin. Schema source: `migrations/166_location_based_steering.php:39`. Bug source: `Steering_exception_model::addNewFromAppInfoToTenantDb` INSERT lacks the column (file:line ~2105). Repro: ENG-1031514.
- **Webui list query and pycore/nsbypass.json consumer disagree on `ds_mode=-1`.** UI hides the row; pycore treats unknown ds_mode as off-prem and still emits it in `nsbypass.json`, so the client receives the bypass while the admin can't see/manage it. When investigating "customer says it's there but UI doesn't show it" for steering exceptions, suspect ds_mode mismatch first. Repro: ENG-1031514 — Fujifilm tenant 15724, 51 ssl_pinned_app rows in nsbypass.json absent from UI.

## PHPUnit Mocking

- **`getMockForModel` throws `MethodCannotBeConfiguredException` on `private` methods.** PHPUnit mock builder can only configure `public` or `protected` methods. Any method you want to stub/mock in a test MUST be `protected` (or `public`). When adding a new helper method that tests need to mock, declare it `protected`, not `private`. Pattern: `retainOldGroupScimId` (ENG-868833) was `private` → CI threw `MethodCannotBeConfiguredException` on every test using `resetSaveClientConfigMock` → fix: change to `protected`.

## RTK Proxy

- **RTK hook swallows grep output in some contexts.** Bare `grep` via the shell hook shows `"X matches in 0 files: [+N more]"` with no actual content. Fix: prefix with `rtk proxy` — e.g. `rtk proxy grep -n "pattern" file.php`. Same applies to other commands whose output RTK filters but shouldn't.

## OpenSpec (opsx) Slash Commands

- **`/opsx:propose` doesn't exist** — CLAUDE.md's Planning-with-OpenSpec section names `/opsx:propose`, `/opsx:apply`, `/opsx:archive`, but the actual installed skill set is `opsx:new` (start a change + generate artifacts), `opsx:continue`, `opsx:ff` (new + all artifacts in one go), `opsx:apply`, `opsx:archive`, `opsx:verify`, `opsx:sync`, `opsx:explore`, `opsx:onboard`, `opsx:bulk-archive`. Calling `Skill({skill: "opsx:propose"})` throws `Unknown skill`. Use `opsx:new` for the propose step (or `opsx:ff` for propose+artifacts combined) until CLAUDE.md is corrected.

## GitHub Actions: local action refs in reusable workflows

- **Step-level `uses: ./.github/actions/<x>` inside a REUSABLE workflow resolves to the CALLER's `$GITHUB_WORKSPACE`, not the reusable workflow's own repo.** Failure: `Can't find 'action.yml' ... under /home/runner/_work/<caller>/<caller>/.github/actions/<x>`. This differs from JOB-level `uses: ./.github/workflows/<x>.yaml` (calling another reusable workflow), which DOES resolve to the repo+ref of the workflow declaring the job. So composite/local actions invoked from a reusable workflow's steps MUST use an absolute `owner/repo/path@ref`. There is no built-in "same ref as this workflow" for `uses:` — hardcoding `@develop` is the common practice; to test a feature branch's action changes end-to-end, temporarily pin the absolute ref to the PR branch and revert to `@develop` before merge. Repro: ngweb-actions service_cicd.yaml manifest-and-deploy (ENG-1052961).

## dnd-kit reorder testing in jsdom (webui2 ntskui DataGrid)
- **jsdom cannot complete a keyboard-driven sortable reorder with ntskui `DataGridTableDndRows`.** ntskui wires `KeyboardSensor` WITHOUT `sortableKeyboardCoordinates`, so ArrowDown moves by fixed px and never resolves an "over" droppable in a layout-less DOM. Symptom: aria-live announces "Draggable item N was dropped" (pickup + drop fire) but no "moved over droppable" and no reorder/PATCH — for BOTH broken and working code. So a "no PATCH fired" assertion via keyboard drag is a false positive for any drag bug; it's a jsdom artifact. Use a MouseSensor drag with a `getBoundingClientRect` override giving each `tbody tr` a distinct vertical rect, or test in a real browser.
