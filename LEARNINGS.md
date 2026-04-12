# Learnings

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
  See any recent PR (e.g., #1048) for the exact format.

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

## SonarQube New-Code Coverage Measures Only Diff Lines

- SonarQube quality gate checks coverage on lines changed in the PR, not
  whole-file coverage. To verify locally: run tests with
  `--coverageReporters=json`, parse `coverage/coverage-final.json`, and
  cross-reference statement/branch maps against `git diff` line numbers.
  Overall file coverage percentages are misleading for the quality gate.

