---
name: review-new-code-coverage
description: >-
  Reviews the **new-code test coverage** of a GitHub pull request — the lines
  added or modified by the PR — and writes additional unit tests to close the
  uncovered gaps. Mirrors SonarQube new-code coverage semantics: only the diff
  lines count, not whole-file %. Optionally cross-checks against SonarQube's
  authoritative per-file `new_coverage` (via the `webui-balkan/sonarqube-debug`
  plugin scripts) and surfaces non-coverage QG failures (code smells, bugs)
  before declaring done. Triggers on "review new code coverage", "improve PR
  coverage", "add tests for #N", or `/review-new-code-coverage`.
argument-hint: "[pr# | repo#pr | org/repo#pr | pr-url | --base <ref> | --vs <ref>]  (omit → infer from current branch)"
allowed-tools: Bash(gh:*), Bash(git:*), Bash(jq:*), Bash(npm:*), Bash(npx:*), Bash(node:*), Bash(pnpm:*), Bash(python3:*), Bash(bash:*), Bash(curl:*), Bash(find:*), Read, Edit, Write, Grep, Glob
user-invocable: true
---

# Review New-Code Coverage

**Emit "Skill activated: review-new-code-coverage"**

Audit the test coverage of the lines a PR actually changes, then write tests
to cover the gaps. Goal: the PR's **new code** — not the whole file — meets
the coverage bar before landing.

## Context

$ARGUMENTS

---

## SonarQube Cross-Check (optional, Mode A only)

Local coverage is the **primary** signal — fast, scoped to the diff, runs
without network. SonarQube is the **authoritative** signal — it owns the
quality gate verdict that blocks the PR. Both can disagree:

- Local says 100% but SQ flags a file < 80%: the scoped test glob excluded
  a file SQ counted (barrel re-export, lazy-loaded route, MSW handler the
  product code imports at runtime).
- SQ says 100% but local has gaps: scoped test set was narrower than the
  SQ analysis run.
- QG fails on **non-coverage** metrics (cognitive complexity, duplications,
  new code smells) that this skill would otherwise miss entirely.

When the PR is open and SQ has analysed it, prefer to reconcile both. The
`webui-balkan/sonarqube-debug` plugin provides three scripts:

```
${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-coverage-gap.sh <repo> <pr> [threshold]
${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-issues.sh        <repo> <pr> [type]
${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-precheck.sh      [pkg-pattern]   # Go only today
```

`${CLAUDE_PLUGIN_ROOT}` resolves at plugin runtime; if `sonarqube-debug` is
not installed, fall back to a `find ~/.claude/plugins/cache -path
'*sonarqube-debug/scripts/sq-coverage-gap.sh' -print -quit` lookup, and if
still missing skip the SQ phases (they are best-effort).

First run on a host: scripts source `_preflight.sh`, which guides the user
through `~/.claude/sonarqube.json` setup the first time and exits non-zero.
Surface that output verbatim — do not retry silently.

SQ project key convention: `ngweb-<repo-name>` (e.g. `ngweb-webui2`,
`ngweb-mf-client`, `ngweb-ms-webui`). Hard-coded in `sq_project_key`; if a
repo deviates, the script fails loud — do not fabricate a key.

QG threshold for new-code coverage is **80%** by default (the SQ gate value).
This skill's local goal is **100%** of `$DIFF_LINES`. Use 80% only as the
"red on CI" trigger; keep aiming for 100% locally so a single late-arriving
edit doesn't tip the file under threshold.

---

## PHASE 1: Resolve the Diff Surface

This skill supports **two modes** for determining what counts as "new code":

### Mode A — PR mode (default when args look like a PR reference)

Parse `$ARGUMENTS`. Accept the same input forms as `/finish-up`:

| Input | Example | Handling |
|-------|---------|----------|
| URL | `https://github.com/netSkope/mf-client/pull/1146` | Regex-extract org/repo/N |
| Fully qualified | `netSkope/mf-client#1146` | Split on `/` and `#` |
| Repo-scoped | `mf-client#1146` | Default `$ORG=netSkope` |
| Bare number | `1146` or `#1146` | `gh repo view --json owner,name` |
| **Empty** | _(no args)_ | `gh pr view --json number,headRepositoryOwner,headRepository,headRefName,baseRefName,state` for current branch |

Fail fast if the PR is `MERGED` or `CLOSED` — adding tests post-merge is a
separate workflow (open a follow-up).

Record:

- `$ORG`, `$REPO`, `$PR_NUMBER`
- `$HEAD_BRANCH`, `$BASE_BRANCH` (from `gh pr view`)
- `$BASE_SHA` — `git merge-base origin/$BASE_BRANCH HEAD`

If the local checkout isn't on `$HEAD_BRANCH`, bail. Switching branches
mid-skill risks discarding unstaged work.

### Mode B — Local-branch-compare mode (skip PR/GitHub entirely)

Use this mode when:

- The user passes `--base <ref>` or `--vs <ref>` (e.g. `--base origin/staging`,
  `--vs main`, `--base release/202605.2`).
- No PR exists yet (pre-push, draft work, fork-and-iterate).
- `gh` is unavailable, offline, or auth is broken.
- The user explicitly says "compare against `<branch>`" or "review my local changes".

Procedure:

1. Determine the base ref:
   - Explicit `--base`/`--vs` → use it verbatim.
   - Else, **auto-detect** in this order:
     - The branch's tracked upstream's merge-base (`git rev-parse --abbrev-ref @{u}` → `git merge-base @{u} HEAD`).
     - `origin/staging` if it exists (mf-client convention from LEARNINGS).
     - `origin/master` or `origin/main` (whichever the repo uses — check `git symbolic-ref refs/remotes/origin/HEAD`).
     - `origin/develop` for webui (LEARNINGS: in-flight fixVersion → develop).
   - If still ambiguous, ask the user once.
2. Refresh: `git fetch origin <base-branch> --quiet`.
3. Compute `$BASE_SHA = git merge-base origin/<base-branch> HEAD`. Using
   `merge-base` (not the branch tip) is critical — it ignores commits that
   landed on the base after this branch forked, so the diff matches what
   the eventual PR would show.
4. Set `$HEAD_BRANCH = $(git branch --show-current)`. Leave `$ORG`, `$REPO`,
   and `$PR_NUMBER` unset (subsequent phases must not assume PR metadata).
5. Sanity check: `git diff --shortstat $BASE_SHA...HEAD` must be non-empty.
   If empty, bail: "No changes vs `<base>`. Nothing to review."

The rest of the skill (Phases 2–9) works identically regardless of mode —
both produce a `$BASE_SHA` and a working tree. Reporting (Phase 9) labels
the run as either `PR #N` or `local: $HEAD_BRANCH vs <base>`.

---

## PHASE 2: Detect Test Tooling

Read project signals **in this order** and stop at the first match:

1. **mf-client recipe** — `package.json` contains `"craco test"` and the repo
   path matches `mf-client`. Use Jest via craco. Run via `npm test`.
   - Coverage flags: `--coverage --coverageReporters=json --watchAll=false`
   - Heap: prefix with `NODE_OPTIONS='--max-old-space-size=8192'`
   - Add `--forceExit` to avoid hung handles from valtio devtools / MSW
2. **webui Angular** — `src/webui/neo/package.json` exists. Run `./node_modules/.bin/jest`
   from `src/webui/neo`. Don't use `npx jest` (jest 30 vs project's jest 29).
3. **webui2 monorepo** — `turbo.json` at repo root and `apps/shell/package.json`
   exists. Use Vitest scoped to the shell app. Package name is **`shell`**, not
   `@ns/shell` — `pnpm --filter @ns/shell` returns "No projects matched".
   **Vitest does NOT accept Jest's `--testPathPattern`** — pass a positional
   path or directory instead. Working invocation (run from `apps/shell`):
   - `cd apps/shell && npx vitest run <dir-or-file-glob> --coverage --coverage.reporter=json --coverage.reportsDirectory=./coverage-ncc`
   Use a dedicated `--coverage.reportsDirectory` (e.g. `coverage-ncc`) so the
   run doesn't clobber the repo's normal `coverage/`; clean it up afterward
   (`rm -rf coverage-ncc`). Despite the v8 provider, `coverage-final.json` is
   **istanbul-shaped** (`statementMap` + `s` counters) — Phase 5 parsing applies
   as written.
4. **Generic Jest** — `package.json` declares `jest` as dep/devDep.
5. **Vitest** — `package.json` declares `vitest`. Use `vitest run --coverage`.
6. **Other** — bail with: "Unsupported test runner. Add support to skill or
   run coverage manually and paste the JSON path."

Project-level CLAUDE.md or LEARNINGS.md may override — read them first.

---

## PHASE 3: Compute the Diff Surface

Compute new/modified lines for the PR:

```bash
git diff --unified=0 $BASE_SHA...HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx' \
  ':(exclude)**/*.test.ts' \
  ':(exclude)**/*.test.tsx' \
  ':(exclude)**/*.spec.ts' \
  ':(exclude)**/*.spec.tsx' \
  ':(exclude)**/__tests__/**' \
  ':(exclude)**/__mocks__/**'
```

Parse `+` hunks into `(file_path, line_number)` pairs. Exclude:

- Test files themselves (already excluded above)
- Pure-comment / blank-line additions (lines whose stripped body starts with
  `//`, `*`, or `/*`, or is empty)
- Generated files (e.g., `*.gen.ts`, OpenAPI clients in `src/utils/api/generated/`)
- **Type-only declarations** — lines inside `interface`/`type` bodies, bare
  `import type` lines, and `as const` map *type* annotations. These emit **no
  executable statements**, so the coverage provider produces no `statementMap`
  entry for them. Counting them as "diff lines" inflates the denominator and
  surfaces them as permanently-uncovered noise. In Phase 5 a diff line with **no
  intersecting statement at all** (not merely count 0) is "untracked" — treat as
  not-applicable, never as uncovered. Whole files that are pure types
  (`*.types.ts`, `*.constants.ts` of literal maps) typically contribute zero
  executable lines; expect them to drop out entirely.

Prefer a small script (Python/node) over hand-parsing: walk `git diff
--unified=0`, track the `@@ +start` line counter, collect added non-comment
lines per file. Hand-counting hunks across 20+ files is error-prone.

Store the resulting set as `$DIFF_LINES`. This is the **denominator** for
new-code coverage. Empty set → exit "No source-code changes to cover."

---

## PHASE 4: Run Coverage

**Pre-step (Mode A only, best-effort): pull SQ's per-file gap list**. If the
PR has been analysed, this seeds the work list with SQ's authoritative view
before local coverage runs:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-coverage-gap.sh \
  $ORG/$REPO $PR_NUMBER 100
```

Threshold `100` so any file with even one uncovered new line is listed.
Capture the file paths into `$SQ_GAP_FILES`. If the script fails (preflight,
no SQ analysis yet, network), record the reason and continue — local
coverage remains the primary signal. Do not block on SQ availability.

Resolve the **minimal** set of test files to run:

1. For each changed source file `src/foo/bar.ts`, look for the conventional
   sibling test: `bar.test.ts(x)`, `bar.spec.ts(x)`, or `__tests__/bar.test.ts(x)`.
2. Also include any test that imports the changed file (`grep -l "from '~/foo/bar'"`).
3. Build a `--testPathPattern` regex covering all matched test files.

Run coverage scoped to changed sources:

```bash
NODE_OPTIONS='--max-old-space-size=8192' npm test -- \
  --coverage \
  --coverageReporters=json \
  --collectCoverageFrom='<changed-file-glob>' \
  --testPathPattern='<resolved-test-files>' \
  --watchAll=false \
  --forceExit
```

Output lands at `coverage/coverage-final.json`. If the run **fails** (red
test, type error), fix or report before continuing — coverage data from a
failed run is unreliable.

**Flag-gated / conditionally-mounted code:** a changed component may be dark
not because no test exists, but because every existing test's setup gates it
off (a feature flag left `false`, a parent that never renders it, a mode the
suite doesn't exercise). Before concluding "no coverage," check the render
predicate: `useFlag(...)`, `if (!flags.x) return null`, a `<TabsContent>` whose
parent gates on a flag. The fix is usually a new test that flips the gate on,
not a rewrite. (Repro: webui2 client-config — `AiSecurityTab` and the
auto-reenable field were entirely uncovered because the two PR flags
`mvpAiDiscovery` / `autoReenable` were absent from every `allFlagsOn` mock.)

**Files with no coverage entry at all:** a changed source file may be absent
from `coverage-final.json` because **no test in the scoped run imports it**
(common for MSW handlers, mock factories, barrel files, test-infra). Don't
report these as "0% uncovered product code" — distinguish three buckets:
covered, uncovered-but-tracked, and **no-entry**. No-entry test-infra files
(handlers, fixtures) are out of scope; no-entry *product* files mean the scoped
test set is too narrow — widen `<dir-or-file-glob>` to pull in a test that
imports them, or note that the file genuinely has no test yet.

---

## PHASE 5: Compute Uncovered New Lines

Load `coverage/coverage-final.json`. For each file in `$DIFF_LINES`:

1. Map the file to its coverage entry (key match by absolute path).
2. For each line `L` added/modified by the PR, look up `statementMap` /
   `s` counters covering line `L`.
3. A line is **covered** iff every statement intersecting it has count > 0.
4. Otherwise mark `(file, L)` as **uncovered**.

Produce a report grouped by file:

```
src/pages/devices-page/action.ts
  +112  if (!response?.result) return [];        ← uncovered
  +118  showErrorToast(error, '...');            ← uncovered

src/pages/devices-page/components/DeviceTagBulkActionsPanel.tsx
  +145  if (!isMounted()) return;                ← uncovered
```

If everything is covered → print "✅ New-code coverage: 100%. Nothing to add."
and exit Phase 6+.

---

## PHASE 6: Plan the New Tests

For each file with uncovered new lines:

1. **Read the file** to understand what those lines do — branch condition,
   error handler, edge case, etc.
2. **Read existing tests** for the file to match style, mocks, and helpers.
3. **Group uncovered lines into test cases** by the behavior they represent
   (one test per branch/path, not one test per line).
4. Draft a short plan and present it to the user **before** writing tests:

```
Plan to add 3 tests:

  action.test.ts
    - returns [] when API responds without `result` field
    - logs and toasts when getDevices throws a non-Error rejection

  DeviceTagBulkActionsPanel.test.tsx
    - early-returns from onOperationChange when component unmounted
```

This is the only user checkpoint in the skill. Wait for confirmation.

---

## PHASE 7: Write the Tests

For each test in the approved plan:

- **Match existing conventions** in the sibling test file (mock factories,
  setup/teardown, helpers like `buildDataset`, etc.).
- **Use existing mocks** rather than inventing new ones — duplicate mocks
  drift quickly. Re-apply factory defaults in `beforeEach` after
  `jest.clearAllMocks()` (see `action.test.ts` for the canonical pattern).
- **One behavior per test** — keep `it` blocks focused. Multi-assertion
  blocks are fine if they assert the same behavior from different angles
  (e.g., return value AND side effect).
- **Cast carefully** at type boundaries — `DeviceData` in mf-client requires
  a full `DeviceDetailData` for `response`; use `as unknown as DeviceData`
  on minimal fixtures.

After each file is edited, re-run the same scoped coverage command to
confirm the lines are now covered. Iterate until 100% of `$DIFF_LINES` is
green or a line is genuinely unreachable (error path requires platform
failure, type-narrowing dead code, etc.) — note any unreachable line in
the summary.

**Assert the cheapest signal that exercises the line — coverage is the goal,
not a perfect end-to-end assertion.** A render branch is covered the moment the
element mounts; you do NOT need to assert its exact text. In particular:

- **Don't assert interpolated i18n strings or validation-error message text in
  jsdom.** RHF's `formState.errors` proxy + controlled number inputs have a
  one-render lag in jsdom, so an error `<span>` may mount empty or a frame late
  even when the schema rejected the value. The line is already covered by the
  branch that renders the span; asserting `findByText('Must be at most 1440
  minutes')` adds flakiness for zero coverage gain. Assert the element's
  presence by `data-testid`/`role`, or skip the assertion entirely if the
  show/hide branch is already exercised by a sibling test.
- **Prefer render-presence over behavior round-trips.** "Toggle on → nested
  input appears" and "toggle off → input absent" cover both arms of a
  conditional cheaply and deterministically.
- If a planned test fights the runner (portaled Radix content, debounced
  effects, RHF proxy timing) and the target line is **already green** from
  another test, drop the fighting test rather than `.skip` it — a lingering
  `.skip` reads as a real gap to the next reader. Confirm the line is covered
  first, then delete.

---

## PHASE 8: Lint & TypeCheck

Before reporting done, run the project's actual toolchain — do NOT assume
`tsc`/`eslint`:

- **mf-client / generic Jest projects:** `npx tsc --noEmit` + `npx eslint <files>`
- **webui2:** `npx tsgo --project tsconfig.app.json --noEmit` (not `tsc`),
  `pnpm exec oxlint <files>` (not eslint; run from `apps/shell` with paths
  relative to it — `oxlint` reports "No files found to lint" on a path that
  doesn't resolve from cwd), and `npx oxfmt --check <files>` from repo root.
  oxfmt failures are auto-fixable: `npx oxfmt <files>` then re-check. The
  pre-commit hook runs oxfmt, so an unformatted test will be reformatted on
  commit anyway — format it yourself first so the committed diff is clean.

Fix any errors the new tests introduced. **Don't** bypass with `--no-verify`
or an inline disable comment unless absolutely necessary — the project's
pre-commit hooks will catch the same issues.

**Shell-cwd caveat:** the Bash tool does not persist `cd` between calls (the
shell re-initializes each invocation). Writing a probe/temp test with a
relative path in one call and running it in the next will fail with "no such
file or directory." Either prefix each command with the `cd` (compound command)
or use absolute paths. Clean up any temp probe files in the same call that
created/ran them.

---

## PHASE 8.5: SonarQube Reconcile (Mode A only, best-effort)

After local coverage hits 100% of `$DIFF_LINES`, reconcile against SQ to
catch what local missed. Skip cleanly if `sonarqube-debug` is not installed
or SQ has not analysed the PR.

1. **Per-file coverage gap** at the QG threshold:
   ```bash
   bash ${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-coverage-gap.sh \
     $ORG/$REPO $PR_NUMBER 80
   ```
   Any file listed = SQ counts new lines that local did not. Common causes:
   - File imported transitively by a route the scoped test glob didn't load.
   - Scoped `--collectCoverageFrom` excluded the file. Widen the glob, re-run
     Phase 4, fill the gap.
   - SQ analysis includes files local excluded as "test-infra" (handler that
     also serves a non-test runtime path). Investigate before dismissing.
2. **Non-coverage QG issues** on new code:
   ```bash
   bash ${CLAUDE_PLUGIN_ROOT}/skills/sonarqube-debug/scripts/sq-issues.sh \
     $ORG/$REPO $PR_NUMBER ALL
   ```
   This skill's mandate is **coverage**, not refactoring — but flag findings
   on lines this skill **just modified** (new tests trip cognitive
   complexity, duplicate setup, etc.). Fix the ones the new tests caused,
   surface the rest in the Phase 9 report under "SQ findings (out of skill
   scope)" for the user to triage.
3. If `sq-coverage-gap.sh` returns `total: 0 file(s) below threshold` AND
   `sq-issues.sh` returns `total=0` for the new lines, log "SQ in agreement"
   in the Phase 9 report.

Disagreement between local 100% and SQ < 80% on a file is a real bug in the
scoped test glob, not noise. Resolve it before declaring done.

---

## PHASE 9: Report

Print a structured summary. The header line varies by mode:

- **Mode A (PR)**: `New-code coverage review for PR #1146 (netSkope/mf-client)`
- **Mode B (local)**: `New-code coverage review — pr/ENG-985201/devices-select-all-1k-limit vs origin/staging`

```
<header>

Diff surface:        148 new/modified lines across 6 files
Before:              123 / 148 covered (83.1%)
After:               148 / 148 covered (100%)

Tests added:
  src/pages/devices-page/action.test.ts            (+2)
  src/pages/devices-page/components/DeviceTagBulkActionsPanel.test.tsx (+1)

SonarQube cross-check (Mode A):
  new_coverage:      96.4% (overall, threshold 80%)
  files < 80%:       0
  agreement:         ✓ (local 100% on diff lines matches SQ per-file ≥80%)
  non-coverage QG:   0 new code smells / bugs / vulnerabilities
  (omit this block in Mode B or if SQ unreachable; flag mismatches loudly)

Unreachable / intentionally uncovered:
  src/pages/devices-page/action.ts:118  — non-Error reject branch (TS guards rule out runtime hit)

Next steps:
  - Review the new tests
  - Commit with: ENG-XXXXXX: add coverage for <area>
```

**Do not commit.** Per global rule: only commit when the user explicitly
asks. Surface the suggested commit subject in the summary so they can copy/paste.

---

## Project-specific Notes

### mf-client (`netSkope/mf-client`)

- Branch format: `pr/ENG-XXXXXX/kebab-slug` (commitlint enforced).
- Commit format: `ENG-XXXXXX: subject` (NOT Conventional Commits).
- Test runner: `npm test --` (Jest via craco). Add `--forceExit` for the
  `--coverage` run; otherwise it hangs on valtio/MSW handles.
- Heap: `NODE_OPTIONS='--max-old-space-size=8192'` for coverage runs above
  ~2.5k tests.
- DeviceData mocks: cast minimal fixtures with `as unknown as DeviceData`.
- `vi.mock` is **not** available — this is Jest. Use `jest.mock`.
- See `LEARNINGS.md → Vitest / Mocks` for hoisting pitfalls if migrating.

### webui (`netSkope/webui`)

- React tests: `cd src/webui/neo && ./node_modules/.bin/jest --testPathPattern=...`.
- PHP tests live in `tests/` and use a different harness — out of scope for
  this skill (no JS coverage report).

### webui2 (`netSkope/webui2`)

- Branch format: `pr/ENG-XXXXXX/kebab-slug`. Commit format: `ENG-XXXXXX: subject`.
- Test runner: Vitest. Use `pnpm --filter shell test -- ...` or
  `cd apps/shell && npx vitest run ...`. The shell package name is `shell`,
  not `@ns/shell`.
- Linter: oxlint (not eslint). Vitest globals are NOT recognized — always
  `import { describe, it, expect, vi } from 'vitest';` in test files.
- Typecheck: `npx tsgo --project tsconfig.app.json --noEmit` (prints `ok`).
  Format: `npx oxfmt --check <files>` (root) / `npx oxfmt <files>` to fix.
- Coverage: `npx vitest run <dir> --coverage --coverage.reporter=json
  --coverage.reportsDirectory=./coverage-ncc` from `apps/shell`. NO
  `--testPathPattern` (Jest-only). `coverage-final.json` is istanbul-shaped.
- **Flag-gated components are the usual coverage gap.** Existing suites share
  an `allFlagsOn` mock object passed to `vi.mock('../hooks/useClientConfigFlags')`;
  a newly-added flag-gated tab/field is dark until a test adds that flag key.
  The fix is a new `*.coverage.test.tsx` that spreads the standard mock plus the
  missing flags and drives the modal/page so the gated subtree mounts.
- MSW server starts globally via `vitest.setup.ts`; per-test handlers go
  through `server.use(...)`. The `@ngweb/runtime` `http` client needs an
  absolute-URL shim in jsdom — copy the `vi.mock('@ngweb/runtime', ...)` block
  from a sibling `ConfigModal.*.test.tsx` verbatim.
- MSW handler files / mock factories often have **no coverage entry** (no test
  imports them directly) — that's expected test-infra, not a product gap.
- **Radix / `@ntskui/react` Select branch coverage**: trigger components
  (`Select`, `Combobox`, `Checkbox` rendered as `button[role=...]`) cannot be
  driven by `fireEvent.click` reliably in jsdom — pointer events + portaled
  content make `onValueChange` arrows partially covered (SonarQube flags
  `displayValue && matchesX ? ... : SENTINEL` and the `onValueChange` arrow
  body). Workaround: in a separate `*.coverage.test.tsx` file, mock
  `@ntskui/react`'s Select primitives as a native `<select>` shim that
  forwards the change event to the real `onValueChange`. Reference impl:
  `apps/shell/src/features/incidents/dlp/__tests__/StatusControl.test.tsx`.
  Pair with a sibling probe component reading `useFormContext().watch(name)`
  to assert form-state mutations rather than spying on `onChange`.

---

## Error Handling

| Scenario | Action |
|----------|--------|
| Not on PR head branch (Mode A) | Bail: "Checkout `$HEAD_BRANCH` first." |
| PR merged/closed (Mode A) | Bail with status, suggest follow-up PR. |
| `gh` unavailable / not authenticated | Auto-fall back to Mode B against the tracked upstream base. |
| Mode B base ambiguous | Ask the user once for the base ref. |
| `git fetch` fails (offline) | Use the local copy of the base ref; warn that it may be stale. |
| No source-code diff | Exit cleanly: "No source-code changes to cover." |
| Test runner unsupported | Bail with the list of supported recipes. |
| Coverage run fails (test red) | Report the failure, do not write new tests on top of broken state. |
| Existing test file uses incompatible style | Surface the mismatch, propose the new style, ask before proceeding. |
| Genuinely unreachable line | Document in summary under "Unreachable" — don't add throwaway tests just to bump %. |
| Pre-commit hook would fail | Run the project's typecheck + linter + formatter proactively in Phase 8 (Phase 8 lists per-runner commands). |
| Changed file has no coverage entry | Distinguish test-infra (handlers/mocks — out of scope) from product code (widen the scoped test glob, or note no test exists). |
| Target line stays uncovered after a fighting test | If a sibling test already covers the line, delete the fighting test — don't leave a `.skip`. If it's the only path to the line, document why under "Unreachable / hard-to-test." |
| Type-only changed lines flagged uncovered | They emit no statements; reclassify as "untracked / N/A," never uncovered. |
| `sonarqube-debug` plugin not installed | Skip Phase 8.5. Note "SQ cross-check skipped (plugin not installed)" in Phase 9 report. |
| SQ preflight fails (missing `~/.claude/sonarqube.json`) | Surface the script's guided fix verbatim. Skip Phase 8.5 this run; do not auto-create the creds file. |
| PR not yet analysed by SQ | `sq-coverage-gap.sh` returns `new_coverage=?%`. Skip Phase 8.5; note in Phase 9. |
| SQ flags a file local marked covered | Widen the scoped test glob (`--collectCoverageFrom`), re-run Phase 4, then re-run `sq-coverage-gap.sh`. Treat as a real local-glob bug, not noise. |
| SQ project key not `ngweb-<repo>` | `sq_project_key` fails loud — do not fabricate. Skip Phase 8.5 and surface for the user. |

---

## Critical Conventions

- **Diff lines, not whole-file %.** SonarQube semantics. Don't waste effort
  covering already-merged code.
- **PR mode is optional.** Local-branch-compare (Mode B) is a first-class
  path — works pre-push, offline, or without `gh`. Compute `$BASE_SHA` via
  `git merge-base`, never the base branch tip.
- **One user checkpoint** at the plan stage (Phase 6). Otherwise autonomous.
- **Never commit** unless the user asks — surface the commit subject only.
- **Match existing test style** — duplicate mocks and divergent setup are
  an anti-pattern that compounds over time.
- **Coverage is the bar, not assertion fidelity.** Exercise the line with the
  cheapest deterministic signal (render-presence by testid/role). Don't chase
  interpolated-text or RHF-error-message assertions that flake in jsdom for
  zero coverage gain.
- **Type-only lines aren't coverable.** Drop `interface`/`type`/`import type`
  bodies from the denominator — they produce no statements.
- **SQ is authoritative for the gate, local is authoritative for "what to
  test next."** Run local first (fast, scoped, deterministic). Reconcile
  with SQ in Phase 8.5 only after local is green; SQ disagreement = real
  test-glob bug, not noise. SQ phases are best-effort — never block on them.
- **Aim for 100% locally, not 80%.** SQ's QG threshold is 80%; this skill's
  bar is 100% of `$DIFF_LINES`. The 20% buffer absorbs late edits without
  tipping the gate.
- **Defer to project-level CLAUDE.md** when present.
