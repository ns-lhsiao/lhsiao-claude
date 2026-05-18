# Learnings

## Check PR State Before Pushing Follow-up Commits

- Pushing a commit to a PR branch does NOT automatically update the PR if
  the PR has already been squash-merged. The commit lands on the topic
  branch, stays orphaned, and the `main` branch is missing the fix.
  Before pushing follow-up work, verify with
  `gh pr view <num> --json state` — if `MERGED`, open a new PR with the
  cherry-picked commit rebased onto current `main`, don't push to the old
  topic branch.
- Also happens when the user starts a squash-merge on GitHub *after* you've
  made further edits locally — any commit pushed between "merge clicked"
  and "squash completed" gets dropped from the squash. Rule of thumb:
  whenever adding more commits to an open PR, always `gh pr view` first.
  When in doubt, `gh api repos/OWNER/REPO/compare/main...<branch>` — if
  it reports "behind by N, ahead by 0" the branch has already merged.
- Failure signature: scheduled workflow still exhibits the bug you "just
  fixed" because the fix never reached `main`.

## Slack section.text With Newlines Can Collapse Rendering

- Joining multiple bullets into one `section.text` with `\n` separators
  (e.g., "Count: 4\n• (main)\n• npe-dev-email") sometimes renders as
  one line in Slack ("Count: 4• (main) • npe-dev-email"). This is
  Slack-client-dependent and not a Block Kit guarantee.
- Reliable fix: one `section` block per logical row. For a list of N
  items, emit N section blocks (optionally interleaved with `divider`
  blocks). This guarantees vertical separation and is also a prerequisite
  for attaching per-row `accessory` buttons later.

## Helm list Is Not Authoritative for ngweb-v2 Sidecar Inventory

- `helm list -n ngweb-v2` misses sidecars deployed via YAP — not every
  sidecar release is registered as a Helm release in-cluster. `kubectl
  get deploy -n ngweb-v2` is the ground truth. Query Deployment names
  and filter by the `<service>(-npe-<suffix>)?` convention:
  `kubectl get deploy -n ngweb-v2 -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | awk -v svc="mf-client" '$0 == svc || index($0, svc "-npe-") == 1'`.
- Corollary: the `app.kubernetes.io/instance` label works as a fallback
  only if the sidecar was deployed via helm; it's unreliable for
  YAP-deployed ones. Always prefer Deployment-name filtering.

## Transferred GitHub Repo: origin URL Lies, Pushes Still Land Upstream

- A fork that was later transferred into the upstream org still has the
  old `ns-lhsiao/<repo>.git` URL in the local `origin` remote. `git push`
  shows a "This repository moved. Please use the new location" notice,
  but the push actually succeeds and lands on the upstream repo
  (`netSkope/<repo>`). The PR head is already on upstream, not on a fork
  — despite what `git remote -v` says.
- Confirm which repo a PR's head branch lives on with
  `gh pr view <num> --json headRepositoryOwner,headRepository`. If
  `headRepositoryOwner.login = netSkope`, it's already a native
  upstream-branch PR even if your local remote says otherwise.
- To stop the misleading redirect notice:
  `git remote set-url origin git@github.com:netSkope/<repo>.git`.

## Multi-line jq Filter Needs Trailing Backslash After Closing Quote

- When pipelining `kubectl ... | jq -r '...multi-line filter...' | sort)`,
  put a trailing `\` on the line that closes the jq single quote, not just on
  lines inside the quote. Bash tolerates raw newlines INSIDE `'…'` (they're
  part of the filter string), but once the closing `'` appears, the outer
  shell-parser is active again — and a bare `|` on the next line is a syntax
  error. Failure signature: `syntax error near unexpected token |` at the line
  below the closing `'`. Fix: `] | @tsv' \` then `| sort)`.
- Before pushing multi-line shell steps in YAML, extract the `run:` block and
  run `bash -n` on it. Logic dry-runs (e.g., running jq standalone) do not
  catch this — the bug is in the bash line-continuation, not the jq itself.

## mf-client Branch Naming: pr/ENG-XXXXXX/slug (Not ns-lhsiao/…)

- mf-client uses the same `pr/ENG-XXXXXX/kebab-slug` branch convention
  as webui — not the global CLAUDE.md default of `<user>/<ticket>/<slug>`.
  Apply this whenever pushing to `netSkope/mf-client`, including worktrees.

## mf-client Push to origin (netSkope), Not lhsiao Fork

- Always push feature branches to `origin` (`netSkope/mf-client`), NOT
  the `lhsiao` fork remote. The team workflow opens PRs from branches
  on the upstream repo (shared CI, reviewer access, CODEOWNERS apply).
  `git push -u lhsiao …` creates cross-fork PRs that have to be
  recreated. Default command: `git push -u origin <branch>`.

## mf-client Worktrees Need .husky/_/husky.sh Copied from Primary

- New git worktrees of mf-client fail `git commit` with
  `.husky/pre-commit: line 2: .husky/_/husky.sh: No such file or directory`.
  The `_/husky.sh` shim is created by husky's `prepare` script during
  `npm install` in the primary checkout and is not tracked in git.
  Before the first commit in a worktree, copy it over:
  `mkdir -p .husky/_ && cp ../mf-client/.husky/_/husky.sh .husky/_/husky.sh`.
  Do NOT bypass hooks with `-c core.hooksPath=/dev/null` — lint-staged
  runs eslint/prettier fixes during commit, and skipping it can let
  formatting errors slip into the PR.

## Webui Kubernetes Namespace Convention for MP-Prod POPs

- The Rancher/kubectl namespace for webui pods follows the pattern
  `<dc>-mp-prod--webui` (e.g., `dfw3-mp-prod--webui`), NOT `c4-<dc>`.
  The `c4-am2` style used in older CMs is AM2-specific or outdated.
  Always confirm with the engineer before writing namespace names into a CM.

## mf-client Is a Separate Git Repo Inside netskope-ng-base

- `netskope-ng-base/frontends/mf-client` has its own `.git` with remote
  `git@github.com:netSkope/mf-client.git`. It is NOT a subdirectory of
  `netskope-ng-base` for git purposes. Always `cd` into the mf-client
  directory and check `git remote -v` before running git/gh commands.
  Release branches (e.g., `release/202605.2`) exist on the mf-client
  remote, not on netskope-ng-base.

## gh pr edit Requires read:project Scope

- `gh pr edit <number> --body "..."` (and `--base`) fails with
  "authentication token is missing required scopes [read:project]".
  Use the REST API instead:
  `gh api repos/OWNER/REPO/pulls/N -X PATCH -f body="..."` (or `-f base="branch"`).
  The `-X PATCH` is required — the default method won't work.

## mcp.json Contains Secrets — Never Track in Git

- `~/.claude/mcp.json` stores API tokens (e.g., `ATLASSIAN_API_TOKEN`) in
  plaintext under `mcpServers.*.env`. This file must NEVER be committed.
  The `.gitignore` in the config repo explicitly excludes it.

## Atlassian MCP Server May Not Expose Direct Tools

- Even when `~/.claude/mcp.json` configures an Atlassian MCP server, the
  tools may not be available in the session. Fallback: use `curl` with the
  Jira REST API v3 directly:
  `curl -s -u "USER:TOKEN" "https://SITE/rest/api/3/issue/KEY?fields=summary,description,status"`
  where credentials are read from `mcp.json` via
  `jq -r '.mcpServers.atlassian.env.ATLASSIAN_API_TOKEN' ~/.claude/mcp.json`.
- The env var names are: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_USER_EMAIL`,
  `ATLASSIAN_SITE_URL`. Do NOT guess `ATLASSIAN_EMAIL` or `ATLASSIAN_SITE`
  — those produce silent empty responses.

## mf-client Default Branch Is `master`

- `git fetch origin main` fails — the default branch is `master`.
  Always verify with `git remote show origin` before assuming.

## mf-client Commitlint Requires Jira Task ID Format

- Conventional Commits style (`fix: ...`) is rejected by the
  `commitlint-plugin-jira-rules` hook. Required format:
  `ENG-XXXXXX: description` (project key prefix, not `fix:`/`feat:`).
  See `commitlint.config.js` for allowed prefixes: `ENG`, `NG`, `EP`.

## mf-client Uses Jest via craco, Not Vitest

- `npx vitest` pulls a standalone vitest that can't resolve `~/` path
  aliases. The project test runner is `craco test` (Jest wrapper).
  Run tests with: `npm test -- --testPathPattern='<pattern>'`.

## Check Jira fixVersion for Correct Base Branch

- When creating a worktree for a bug fix, check the Jira ticket's
  `fixVersion` field to determine the correct base branch (e.g.,
  `release/202605.2`). Do not default to `master`/`main` — basing on
  the wrong branch pollutes the PR diff with unrelated commits and
  requires a reset + cherry-pick to fix.

## mf-client PR Description Template

- PRs in mf-client follow a structured template with emoji-prefixed
  sections: `## 🎯 Jira Issue`, `## 📝 Description`,
  `## 🚧 Type of Change` (checkboxes), `## ✅ Checklist`,
  `## 🖼️ Screenshots`, `## 📌 Additional Notes`.
- Read `.github/pull_request_template.md` in the worktree and mirror
  the section headings and checkbox items **exactly** — do not invent
  your own structure or skip optional sections. Reviewers and tooling
  key off the template's wording.

## Playwright Not Available in mf-client node_modules

- `npx playwright --version` works (temp download) but
  `node -e "require('playwright')"` fails when run from the mf-client
  directory. Install playwright in a throwaway directory:
  `mkdir -p /tmp/pw-runner && cd /tmp/pw-runner && npm init -y && npm install playwright`
  then run scripts from there.

## Webui Hash Routing Uses /ns# Prefix

- The webui SPA routes under `/ns#/...`, NOT `/#/...`. Navigating to
  `/#/settings/device-management` returns 404. Correct pattern:
  `http://localhost:9797/ns#/settings/device-management`.
- After login at `/locallogin`, the app redirects to `/ns#/dashboard`.

## Devices Page Playwright Selectors and Load Time

- The Devices page loads in **Basic** filter mode. Click
  `[data-testid="filter-toggle-advanced"]` to switch to Advanced mode,
  then the query input is `[data-testid="filters-advanced-filter-input"]`.
- The mf-client micro-frontend takes 30–60 s to load via module
  federation. Wait for `[data-testid="filter-toggle-advanced"]` as the
  readiness signal, not for the filter input directly.
- "Save as..." button: `[data-testid="saved-filters-save-as"]`.

## DevicesFilters.test.tsx Mocks Entire devices.helper Module

- `DevicesFilters.test.tsx` uses `jest.mock('~/pages/devices-page/helper/devices.helper', () => ({...}))`
  which replaces the **entire** module. Adding a new export from `devices.helper`
  to `DevicesFilters.tsx` will fail at test time unless the mock is updated to
  include it. Even then, partial mocks can produce `undefined` in assertions.
  Safer approach: compose new logic into an already-mocked function (e.g.,
  call `escapeSqsBackslashes` inside `normalizeQueryString`) so the component
  doesn't need a new import.

## showErrorToast First Arg Must Not Be null

- `showErrorToast` in `src/utils/helper/api.helper.ts` accesses
  `error.message` without a null guard. Passing `null` as the first
  argument throws `TypeError: Cannot read properties of null`.
  Always pass `{}` (empty object) when there is no real error object.

## mf-client test:coverage Needs 8 GB Heap and --forceExit

- The default `--max-old-space-size=4096` is insufficient for ~2450 tests
  with coverage instrumentation in `--runInBand` mode. The process gets
  OOM-killed before tests complete. Use `--max-old-space-size=8192`.
- Jest hangs after all tests pass due to leaked async handles (valtio
  devtools, MSW). Add `--forceExit` to the test:coverage command for CI.

## Always Lint Changed Files Before Committing in mf-client

- Tests passing does not mean lint passes. Prettier formatting errors
  (e.g., multi-line args that should be single-line) are only caught by
  ESLint/Prettier, not by Jest. Always run
  `npx eslint <changed-files>` before committing, especially when
  `core.hooksPath=/dev/null` bypasses the pre-commit hook.

## SonarQube New-Code Coverage Measures Only Diff Lines

- SonarQube quality gate checks coverage on lines changed in the PR, not
  whole-file coverage. To verify locally: run tests with
  `--coverageReporters=json`, parse `coverage/coverage-final.json`, and
  cross-reference statement/branch maps against `git diff` line numbers.
  Overall file coverage percentages are misleading for the quality gate.

## Jira /rest/api/3/search Has Been Removed

- The `POST /rest/api/3/search` endpoint has been deprecated and removed.
  Use `POST /rest/api/3/search/jql` instead. Same request body format
  (jql, maxResults, fields, etc.), just a different path.

## CM Ticket Creation: security Field Not on Create Screen

- When creating CM (Change Management) tickets via REST API, the `security`
  field cannot be set — it's "not on the appropriate screen." Omit it from
  the create payload; it gets set to the default automatically.

## CM Ticket Type of Change Is a Cascading Select

- The `customfield_16792` (Type of Change) field in CM tickets is a
  cascading select. Must use `{"id": "PARENT_ID", "child": {"id": "CHILD_ID"}}`
  format, not just `{"id": "CHILD_ID"}`. For Software > Feature Flag:
  parent=13191, child=28422.

## Investigate on the Deployed Branch, Not the Primary Checkout

- When troubleshooting environment-specific bugs (e.g., qa01 vs prod),
  always confirm which branch is deployed to that environment and analyze
  code on THAT branch (`git show <branch>:<file>`). The primary checkout
  may be on a different branch (e.g., a feature branch or `master`) that
  lacks the relevant changes. In mf-client, `staging` is deployed to qa01.

## webui Branch Naming Convention

- The webui repo enforces branch names via CI. The global CLAUDE.md
  convention `<username>/<ticket>-<slug>` is rejected. Required format:
  `pr/ENG-XXXXXX/kebab-slug`. See `https://nsgo.to/branchingstrategy`
  for the full spec. Always defer to the webui CLAUDE.md `PR Workflow`
  section which documents this.

## webui Worktree Needs npm ci and phpunit Config

- The worktree has no `node_modules/` or `vendor/`. For Angular tests:
  `cd src/webui/neo && npm ci`, then `./node_modules/.bin/jest --testPathPattern=...`.
  Do NOT use `npx jest` — it pulls jest 30 which rejects `--testPathPattern`
  (renamed to `--testPathPatterns`). The project pins jest 29.
- For PHP tests: symlinking `vendor/` from the primary checkout causes
  `Cannot redeclare` errors (bootstrap loads helpers from both paths).
  Instead, copy changed files to the primary checkout, run
  `cd tests && php ../vendor/bin/phpunit --configuration phpunit.xml --filter='...'`,
  then restore. The `--configuration phpunit.xml` is required for the
  `APPPATH` constant bootstrap.

## Playwright: Headless Chromium Rejected by Webui

- Default headless Chromium returns "Browser Not Supported" page title.
  Must use `channel: 'chrome'` (real Chrome) in `chromium.launch()`.
  Also set a real Chrome user-agent via `browser.newContext({ userAgent: '...' })`.

## Playwright: Login Flow for Dev Proxy

- After clicking `#btn-sign-in`, do NOT use a fixed `waitForTimeout`.
  Login can take variable time. Use:
  `await page.waitForFunction(() => !window.location.hash.includes('/login'), { timeout: 30000 })`
- Fresh/unconfigured tenants show a **welcome wizard** after login that
  blocks all SPA routes. Must dismiss via `text=skip this step` before
  navigating to target pages.
- Credentials are in `~/.claude/skills/mf-client-playwright/.env`
  (`NS_TEST_USERNAME`, `NS_TEST_PASSWORD`). Source before launching.

## Playwright: Use Hash Assignment for SPA Navigation

- When the base path is the same (e.g., `/ns`), `page.goto()` triggers
  a full page reload even for hash-only changes. This can lose session
  cookies if the login hasn't fully propagated, and forces the SPA to
  re-bootstrap (30–60 s for mf-client).
- Instead, use `page.evaluate(() => { window.location.hash = '#/settings/device-management'; })`
  to navigate within the SPA without reloading. This preserves session
  state and is near-instant.

## development-proxy Location and Config

- The development proxy lives at `/Users/lhsiao/ns/git/development-proxy`,
  NOT inside netskope-ng-base. Start with `npm run dev` (listens on :9797).
- Tenant config: `src/config.ts` → `fallbackServer.host`. Uncomment/change
  the host line and restart to switch tenants.
- Custom route mocks can be added as `app.get()`/`app.post()` handlers
  in `src/main.ts` **before** the main proxy middleware to intercept
  specific API endpoints with mock data.

## mf-client Staging PR Pattern

- When a fix PR targets `release/YYYYMM.N`, create a separate staging
  counterpart PR for QA validation. Cherry-pick the commits onto a new
  branch based on `origin/staging`, push, and open a PR targeting
  `staging`. Use branch name `pr/ENG-XXXXXX/<slug>-staging` to match
  the mf-client/webui branch-naming convention.

## npm install in Worktrees Mutates package-lock.json

- Running `npm install` (instead of `npm ci`) in a worktree on a
  different base branch often produces large `package-lock.json` diffs
  due to dependency resolution differences. Always run
  `git checkout -- package-lock.json` before committing to avoid
  polluting the PR with unrelated lockfile changes.

## mf-client Worktree node_modules: Symlink, Don't npm install

- Running `npm install` or `npm ci` in a fresh worktree mutates
  `package-lock.json` and wastes several minutes. Symlink node_modules
  from the primary checkout instead:
  `ln -s ../mf-client/node_modules node_modules`. Tests, eslint,
  prettier, and craco all resolve through the symlink. Zero lockfile
  churn, zero install time.

## Moving a Branch Across Remotes Requires Closing the PR

- Once a PR is open with its head branch on one repo (e.g. the
  `ns-lhsiao` fork), you cannot retarget it to a branch on a different
  repo (e.g. `netSkope/mf-client`). Even pushing the same branch to
  the new remote leaves the PR pinned to the original head. Workflow:
  `gh pr close <num>` → `git push origin <branch>` →
  `gh pr create --head <branch>` to reopen against the correct repo.
  Also delete the branch from the old remote to avoid confusion.

## webui PHP Model: Use $this->callService() for Testability

- `Client_configuration_model::getClientVersions()` originally called the
  global `callService()` function, which is not mockable in PHPUnit.
  `NS_Model::callService()` is a protected wrapper that delegates to the
  global via `call_user_func_array`. Changing to `$this->callService()`
  is functionally identical but allows `getMockForModel('...', ['callService'])`
  to intercept the call. This pattern is already used elsewhere in the
  codebase (e.g., `notifyProvisionerService` tests).

## webui PR Description Template

- PRs in webui follow a structured template at
  `.github/pull_request_template.md`. Section headings are **H4 (`####`)**,
  NOT H2 like mf-client. Exact section list (mirror verbatim):
  `#### 🎯 Jira Issue`, `#### 📝 Change Description`,
  `#### 🚧 Type of Change` (checkboxes), `#### ✅ Checklist`,
  `#### 🧪 Manual Testing Done`, `#### 🖼️ Screenshots/Videos`,
  `#### 📌 Additional Notes`.
- Read the template in the worktree before opening a PR and copy the
  headings/checklist items exactly — reviewers and tooling key off the
  wording.

## webui Commit Message Format: ENG-XXXXXX: Subject

- webui commits use `ENG-XXXXXX: Subject` (project-key prefix with colon),
  matching mf-client's commitlint requirement. NOT Conventional Commits
  (`fix:`/`feat:`) from the global CLAUDE.md. Confirm via
  `git log origin/develop` before writing a commit. Not documented in
  webui's CLAUDE.md — inferred from history.

## webui fixVersion Maps to develop Until Release Branch Is Cut

- An in-flight fixVersion (e.g., 138.0.0 while still open) integrates to
  `origin/develop`. A `Release<N>` branch only gets cut at code-freeze —
  before that, searching `git branch -r | grep Release<N>` returns
  nothing and basing a PR on `develop` is correct. Track the commit SHA
  in case a cherry-pick to the release branch is needed later.

## NetSkope Flag Names: _enabled Suffix Is an Angular NsConstants Artifact

- NetSkope flag keys appear with and without an `_enabled` suffix across
  sources. The **raw PHP key** (e.g. `nplan4224_jit_provisioning` in
  `Admin_userdata_model.php`) is what the featureflags endpoint
  `/api/v2/ui/platform/featureflags/<name>` accepts. Angular's
  `NsConstants` layer materializes the flag onto a global with an
  `_enabled` suffix — so `NsConstants.nplan4224_jit_provisioning_enabled`
  is the Angular-side view, NOT the real LD/PHP key.
- webui2 consumes flags via `@ngweb/runtime` `useFlag(name)` which hits
  the raw endpoint — use the unsuffixed name. mf-client's
  `default-flag.constant.ts` registers the unsuffixed name too.
- Confluence design docs sometimes write the suffixed Angular view; don't
  copy them verbatim into webui2. Verify against `default-flag.constant.ts`
  or the PHP model before writing a flag key.
- Failure signature: `useFlag` returns false for a flag the tenant has on;
  devtools shows a 404 on `/featureflags/<name>_enabled`.

## v2 Live Probe Is a Partial Sample, Not a Schema

- The v2 live-probe artifact in `migrations/pages/<page>/survey/` captures
  only fields that were populated on the sampled configs. Fields absent
  from every sampled row are NOT necessarily rejected by the API — they
  may just not have been set. Dropping a field from the payload builder
  "because the probe didn't show it" can introduce regressions.
- Cross-reference the Confluence design doc's §4.x schema table and the
  legacy Angular payload shape before concluding a field is out of scope.
  For ambiguous cases, submit the field and observe the 422 body — v2
  explicitly rejects unknown properties with `"unexpected property"`.
- Failure signature: API 422 on create after "fixing" a payload, OR
  populated fields silently disappear on edit round-trip.

## Hand-Rolled Fetchers + Hand-Rolled MSW = Silent Contract Drift

- When an upstream service has no OpenAPI spec and both the fetcher AND
  the MSW handlers are hand-authored, contract bugs are invisible:
  TypeScript sees only the hand-typed response, MSW serves the hand-built
  shape, vitest passes, and the bug surfaces only against a live tenant.
- Before landing a hand-rolled fetcher, verify request+response against
  the legacy source (e.g. mf-client's `userManager.api.ts`) OR a live
  devtools capture. Don't trust "compiles + tests pass" alone.
- Fix is usually to mirror a proven legacy fetcher's exact shape (request
  body envelope, response `data`/`result` wrapper, field names).

## TanStack Table `columns` Memo Must Include Closed-Over Data in Deps

- If a `columns` cell function closes over a prop/state (e.g. a lookup
  map passed from the parent), and that prop is NOT in the `useMemo` dep
  array, the column definition freezes with the initial captured value.
  The cell keeps rendering the stale/empty value indefinitely even after
  the parent re-renders with the populated prop.
- Failure signature: an async-resolved lookup (`scimId → name`, user
  profile map, etc.) appears to work on unit tests but never shows the
  resolved value in the live app — cells render the raw id forever.
- Fix: add every closed-over dependency (plain values, refs, resolved
  query data) to the `columns` memo's dep array. This is easy to miss
  because React Compiler and ESLint `react-hooks/exhaustive-deps` are
  often disabled around `useReactTable` in codebases.

## React Query `isFetching` Has a One-Render Gap When `enabled` Flips True

- The render in which `enabled: true` first evaluates is NOT the same
  render in which `isFetching: true` flips on. React Query observes the
  enabled flip on the next render tick. During the gap, a gate like
  `hasData > 0 && !query.data && query.isFetching` is false — so any
  conditional rendering driven by it lets the stale/default value paint
  for one frame.
- Fix options: (1) Gate on `!query.data` alone if you always want to
  hide until data lands (loses the "no rows = skip query" optimization
  unless combined with a length check). (2) Track pending via a local
  `useState` + `useEffect` that sets it true synchronously when the
  source data becomes non-empty. (3) If using TanStack Table or similar,
  the deeper fix is usually the memo-dep bug (see previous entry), not
  the gate predicate.
- Failure signature: a render-blocking gate "works in theory" but the
  raw value still flashes visibly on first load.

## pnpm Worktree Symlinks Need Different Targets for Tests vs. Commit Hooks

- A pnpm workspace root's `node_modules` hosts tools like `lint-staged`,
  while each app's `apps/<app>/node_modules` hosts tools like `vitest`.
  When symlinking a worktree's node_modules to save install time:
  - Root `node_modules` must link to a checkout that has pnpm-installed
    deps (e.g. the primary checkout): `ln -s /path/to/primary/node_modules`.
  - `apps/<app>/node_modules` needs the same — but a sibling worktree
    that ran `pnpm install` may not have the app-scoped bins if the
    resolver hoisted them. Symlinking to the primary is safest.
- Failure signatures: `Command "lint-staged" not found` on commit (root
  symlink broken/missing), or `vitest: command not found` on test (app
  symlink broken). Swap both to the primary checkout's node_modules.
- If the worktree was `pnpm install`ed at some point, there's a real
  `node_modules` directory, not a symlink — remove it first with `rm -rf`
  before re-linking.

## Stuck Debugging: Delegate to a Subagent With Full Context

- When two or three attempts at a bug fix miss the actual cause, stop
  iterating on hypotheses in the main thread. Launch a subagent with:
  the repro steps, every file the bug could touch, each hypothesis that
  was tried and rejected, and a constraint on output length (≤400 words).
- Subagents read files fresh without the main thread's framing bias and
  often find closure / memoization / cache issues that look invisible
  from "the current fix should have worked" perspective.
- Failure signature: three consecutive fix commits that don't change the
  user-visible behavior. Revert and delegate.

## Jira `assignee` On Create Gets Overridden By Component Default Assignee

- `POST /rest/api/3/issue` with `"assignee": {"accountId": "..."}` in the
  payload is NOT authoritative. If the specified component has a default
  assignee configured, Jira silently overrides the payload and assigns the
  ticket to the component default. Observed with the webui "Web UI"
  component auto-routing new tickets to that component's owner regardless
  of `accountId` in the create body.
- Fix: after create, always follow with a dedicated reassign:
  `PUT /rest/api/3/issue/<KEY>/assignee -d '{"accountId":"..."}'` (HTTP 204).
- Failure signature: ticket creation returns 201 with your `accountId` in
  the request body, but `GET /issue/<KEY>?fields=assignee` shows someone
  else as the assignee.

## Jira ENG "QA Test Recommendations" Lives On customfield_12503

- The field visible in the Jira UI as "Fix QA Test Recommendations" is
  `customfield_12503`. Accepts an ADF doc (not plain text). Set via
  `PUT /rest/api/3/issue/<KEY>` with body
  `{"fields":{"customfield_12503":{"type":"doc","version":1,"content":[...]}}}`.
  Returns HTTP 204 on success.
- To discover Jira custom-field IDs for an ENG ticket, hit
  `GET /issue/<KEY>?expand=names` and filter `.names` for keywords. Field
  labels in the UI differ subtly from the schema name ("Fix QA Test
  Recommendations" vs. "QA Test Recommendations"); grep case-insensitively.

## webui Tenant Migrations Don't Ship With PHPUnit Tests

- Files under `src/webui/system_framework/application/migrations_ui/tenant/`
  are not unit-tested in this repo. Verified by searching for companion
  tests for migrations 396, 397, 405, 406 — none exist. The webui
  CLAUDE.md post-change checklist implies tests for any PHP change, but
  in this directory the convention is "no tests." Validation is
  operational (staging dry-run + QA on a tenant via the QA Test
  Recommendations on the ticket).
- Rule of thumb: when a sibling migration on the same file's directory
  has no test, don't invent one. Add the case matrix to the ticket's QA
  Test Recommendations field instead.

## client-oppy-configuration bulkdelete Requires action/scope/idempotencyToken

- `POST /api/v2/clientconfiguration/client/config/bulkdelete` rejects with
  422 if `action`, `scope`, or `idempotencyToken` are missing. Required body:
  `{ action: "delete", scope: "selective", ids: string[], idempotencyToken: string }`.
- The MSW hand-rolled mock only modelled `{ ids }` — the real contract has
  three additional required fields that are invisible until tested against a
  live tenant. Lesson: for hand-rolled fetchers, verify the full request shape
  against a live 422 body, not just the happy-path response.

## Idempotency Token Belongs at the Call Site, Not Inside the API Function

- Generating `crypto.randomUUID()` inside the raw HTTP function (e.g.
  `bulkDeleteClientConfigs`) creates a new token on every call — including
  retries — which defeats the purpose of idempotency.
- Generate the token at the component level (e.g. in the mutation's
  `mutationFn` or via a `useRef` in the component) so the same token is
  reused for the lifetime of the user-initiated action. Pass it explicitly
  as a parameter to the API function.

## Passing ref.current as a Prop Is an Anti-Pattern

- `ref.current` read during render is stale: refs don't trigger re-renders,
  so the value passed as a prop reflects whatever `ref.current` was on the
  *previous* render cycle, not the current one.
- Fix: use a stable prop that derives from the component's own props/state.
  For modal-open-time decisions (e.g. whether to show a confirm dialog),
  prefer a stable `mode` prop that is set once per open cycle and doesn't
  change mid-session. Do NOT use `ref.current` to communicate render-time
  decisions to child components.

## npm pack for Private Scoped Packages Needs --registry

- `npm pack "@netskope-ui/match-logic@1.0.6"` fails silently (exit 1, no output)
  when the package lives on a private artifactory and the default registry is npmjs.
  Must pass `--registry https://artifactory-rd.netskope.io/artifactory/api/npm/npm-dev`.
  Works fine after that.

## npm→Yarn Lock Migration Silently Upgrades semver-Range Deps

- When a project migrates from npm to yarn and generates a fresh `yarn.lock`,
  all `^x.y.z` ranges re-resolve against the current registry. Packages can
  jump by minor or even major versions with no explicit version bump PR.
  In mf-client, `@netskope-ui/match-logic@^1.0.2` silently resolved to
  `1.5.0` when `yarn.lock` was first generated (PR #1104, commit `1a565ead`).
- To find when a dep was first locked to a specific version:
  `git log --oneline -- yarn.lock` then `git show <sha> -- yarn.lock | grep -A3 "pkg-name"`.

## @netskope-ui/match-logic allowMultiple:false Behavior Changed in 1.5.0

- In **1.0.6**, `allowMultiple: false` only disabled individual criterion dropdown
  items; the plain "+" button was gated solely by `maxCount`. So
  `allowMultiple: false, maxCount: 16` correctly allowed up to 16 entries.
- In **1.5.0**, `allowMultiple: false` immediately disables the plain "+" button
  after the first entry, regardless of `maxCount`. The
  `allowMultiple: false, maxCount: 16` pattern is now broken — button grays out
  after 1 item.
- Fix: change `allowMultiple: false` → `allowMultiple: true` wherever `maxCount`
  is also set. Affected in mf-client: `AVCriteria.tsx`, `ProcessCriteria.tsx`,
  `FileCriteria.tsx`, `RegistryCriteria.tsx`, `OsCriteria.tsx`, `DeviceTagCriteria.tsx`.

## Tenant Swagger/OpenAPI Endpoints Are Not Exposed at the Edge

- Even when an API is fully spec'd in `netSkope/api-gateway-endpoints`, the
  spec is NOT published at the tenant edge. All standard discovery paths
  return 404: `/apidocs/swagger.json`, `/apidocs/openapi.json`,
  `/apidocs/v3/api-docs`, `/apidocs/`, `/api/v2/swagger.json`, `/openapi.json`,
  `/v2/api-docs`, `/api-docs`, `/api/v2/<service>/{apidocs,openapi.json,
  swagger.json,docs,spec}`, `/.well-known/openapi.json`. Kong returns "no
  Route matched" or the tenant 404 page.
- Workaround: read the YAML spec directly from the api-gateway-endpoints PR
  via `gh pr diff <num> --repo netSkope/api-gateway-endpoints` (returns the
  full OpenAPI 3.1.0 file). This is the authoritative source.
- Failure signature: any auth header works, the path simply doesn't resolve.

## v2 /api/v2/users/getgroups SAML Field Semantics Are Inverted

- For `collectionId: 'default'` (regular user groups): row.id is the wire
  identifier (used as `targets.values[].id`), row.displayName is the label.
- For `collectionId: 'jit_default'` (SAML groups): row.scimId is the wire
  identifier, row.id is the **display name**. Sending the display name as
  the target id triggers "OU/Group already exists" — looks like a duplicate
  error but is actually a wire-format error.
- Fix: in the `jit_default` mapper, use `{ id: row.scimId, name: row.id }`.
  Confirmed by mf-client `userManager.helper.ts` /
  `getSAMLGroupsByScimIds`.
- Also: the scimId batch lookup (`scimId.in: [...]`) MUST include
  `collectionId: 'jit_default'` in the filter — without it the server
  returns no results and SAML rows render as raw UUIDs in the list table.

## bulkdelete / bulkstatus Wire Shape Has Non-Obvious Field Names

- The v2 `client-oppy-configuration` bulk endpoints diverge from intuition:
  - **bulkdelete request**: `{ action: "delete", scope: "selective", ids,
    idempotencyToken }`. `action` enum is just `["delete"]`; `scope` enum
    is just `["selective"]`. Missing any of these → 422.
  - **bulkdelete response 202**: `{ jobId, pollUrl, status, action,
    message }` — only `jobId` is load-bearing for the client.
  - **bulkstatus response**: `{ jobId, status, action, totalAffected
    (int64), message, createdAt, completedAt }`. NO `processed`, NO
    `total`, NO `errors[]`. Reading those returns `undefined` silently.
  - **Status enum is 5 values**: `accepted | in_progress | completed |
    failed | cancelled`. A poll loop that only terminates on
    `completed|failed` will spin until timeout on a `cancelled` job.
- Hard cap: 250 ids per bulkdelete request; chunk if exceeding. Rate
  limit: 4 req/sec (vs 50/sec for per-item CRUD).

## Angular processMonthlyVersions Subtracts Goldens From Specifics

- Legacy v1 `/getClientVersions` returns three flat string arrays:
  `goldenversions`, `specificversions`, `monthlyversions?`.
  `specificversions` is a SUPERSET that includes goldens. Angular's
  `processMonthlyVersions` produces the monthly-release dropdown via
  `specificversions.filter(v => !goldenSet.has(v))`.
- v2 `/client/versions` flips the schema: each `release` carries
  `golden: bool` and `specific: bool` independently. A "monthly" hotfix
  has `specific: true, golden: false`. The v2-equivalent filter is
  `release.specific && !release.golden` — NOT `release.specific` alone.
- Failure signature: a "Specific Monthly Release" dropdown that lists
  golden majors (e.g., `132.0.0`) as if they were monthly hotfixes.
  Aliasing `monthlyVersions = specificVersions` is the buggy shortcut.

## Verify Wire Unit Before Refactoring On Field Name Alone

- A field named `maxTimeoutSeconds` returned by the BE may actually
  carry **minutes**. Names lie; the live payload is the only authority.
  Before refactoring "the form is misnamed, multiply by 60 everywhere,"
  open devtools or `curl` a real config and confirm what the integer
  represents. v1's matching field stores minutes — that's a strong hint
  the BE inherited the same convention regardless of the v2 type name.
- Failure signature: a saved value of `30` displays as "30 seconds" in
  v2 but "30 minutes" in v1. Round-tripping a v1 record divides the real
  duration by 60 in v2 (or multiplies on save).
- Remediation pattern: do the probe FIRST. Only refactor units after a
  live datapoint disagrees with the type name. A single screenshot from
  the user showing `popPinning.maxTimeoutSeconds: 240` with "4 hours" in
  v1 settled the ambiguity faster than an entire sub-agent audit.

## Form Unit Dropdowns Need a Conversion Boundary

- An input bound to `clientOneTimeDurationMinutes` plus a sibling unit
  dropdown (`min` / `hr`) does NOT auto-convert. Typing `6` with `hr`
  selected stores `6` (minutes) unless the input's `onChange` multiplies
  by 60 when the unit is `hr` and the displayed `value` divides by 60.
  Otherwise the dropdown is purely cosmetic and the wire payload is
  wrong.
- Pattern: keep storage normalized to one unit (minutes), and translate
  at the input boundary based on the watched unit field. Update both
  `value={display}` and `onChange={n => durationUnit === 'hr' ? n*60 : n}`.
  Adjust `min`/`max` in tandem (24h cap = `1` and `24` in hr mode,
  `5` and `1440` in min mode).
- Failure signature: dropdown switches `min`→`hr` but the input value
  doesn't visually change, and the saved payload reflects the typed
  number as raw minutes regardless.

## vi.mock for `new ClassName(...)` Needs a Class, Not vi.fn()

- Mocking a constructor with
  `vi.mock('lib', () => ({ Foo: vi.fn().mockImplementation((x) => ({...})) }))`
  emits a vitest warning ("the mock did not use 'function' or 'class' in
  its implementation") and the resulting mock is NOT constructable —
  `new Foo()` either silently returns a plain object missing instance
  methods, or throws, depending on the runtime.
- Fix: declare an actual class. `vi.mock('lib', () => ({ Foo: class { constructor(x) { ... this.field = ... } } }))`.
  Works with both static `import` and dynamic `await import`.
- Also: `vi.mock` factories are HOISTED above all top-level `const`s
  (including in the same file). The factory body cannot reference outer
  consts like `BAD_PEM`. Match on stable substrings (`pem.includes('malformed')`)
  instead of `pem === BAD_PEM`.

## pnpm Adds in a Worktree Need to Install in the Primary Checkout

- `pnpm --filter <pkg> add <dep>` inside a git worktree fails with
  `ERR_PNPM_UNEXPECTED_VIRTUAL_STORE` because the worktree's node_modules
  is a symlink to the primary checkout's node_modules / .pnpm store.
  pnpm refuses to relink the virtual store to a different location.
- Workflow: `cd <primary checkout> && pnpm --filter <pkg> add <dep>`.
  Edit `package.json` in the worktree first if you want the version
  declaration committed alongside the feature; then run pnpm in the
  primary so the .pnpm store is updated.
- Failure signature: `pnpm add` inside the worktree exits non-zero with
  the virtual-store error and prints "If you want to use the new virtual
  store location, reinstall your dependencies with pnpm install" — do
  NOT take that suggestion (would mutate package-lock.json in the
  worktree).

## Design Before Fixing — Consult a Sub-agent for Non-trivial Reverse-Engineering

- For UI parity bugs that involve cross-layer guesses (UI ↔ schema ↔
  payload-builder ↔ wire), a 5-minute sub-agent audit (general-purpose
  or domain-specific) of v1 source pays for itself. Two real cases this
  session: (1) the POP-pinning unit ambiguity that required a two-step
  revert because I refactored on a name alone; (2) the OTD unit-dropdown
  fix that needed a follow-up because the unit-conversion boundary
  wasn't designed up front.
- Heuristic: if the fix touches more than two files OR crosses a
  serialization boundary OR depends on a flag/feature whose v1 wiring
  isn't already in front of you, spawn a sub-agent to surface v1 truth
  before writing v2 code. Cite v1 file:line in the resulting commit.
- Failure signature: shipping a fix, then immediately needing a
  follow-up commit because round-trip parity broke or a related field
  was missed. Each round-trip the user has to flag burns trust.

