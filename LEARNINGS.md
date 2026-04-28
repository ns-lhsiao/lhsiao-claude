# Learnings

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

