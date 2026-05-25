---
name: review-new-code-coverage
description: >-
  Reviews the **new-code test coverage** of a GitHub pull request — the lines
  added or modified by the PR — and writes additional unit tests to close the
  uncovered gaps. Mirrors SonarQube new-code coverage semantics: only the diff
  lines count, not whole-file %. Triggers on "review new code coverage",
  "improve PR coverage", "add tests for #N", or `/review-new-code-coverage`.
argument-hint: "[pr# | repo#pr | org/repo#pr | pr-url | --base <ref> | --vs <ref>]  (omit → infer from current branch)"
allowed-tools: Bash(gh:*), Bash(git:*), Bash(jq:*), Bash(npm:*), Bash(npx:*), Bash(node:*), Read, Edit, Write, Grep, Glob
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
   `@ns/shell` — `pnpm --filter @ns/shell` returns "No projects matched". Two
   working invocations:
   - `pnpm --filter shell test -- --coverage --reporter=json --coverage.reporter=json --testPathPattern=<glob>`
   - `cd apps/shell && npx vitest run <pattern> --coverage --coverage.reporter=json`
   Coverage JSON lands at `apps/shell/coverage/coverage-final.json`.
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
- Pure-comment / blank-line additions
- Generated files (e.g., `*.gen.ts`, OpenAPI clients in `src/utils/api/generated/`)

Store the resulting set as `$DIFF_LINES`. This is the **denominator** for
new-code coverage. Empty set → exit "No source-code changes to cover."

---

## PHASE 4: Run Coverage

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

---

## PHASE 8: Lint & TypeCheck

Before reporting done:

```bash
npx tsc --noEmit
npx eslint <changed-test-files>
```

Fix any errors the new tests introduced. **Don't** bypass with `--no-verify`
or `// eslint-disable-next-line` unless absolutely necessary — the project's
pre-commit hooks will catch the same issues.

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
- MSW server starts globally via `vitest.setup.ts`; per-test handlers go
  through `server.use(...)`.
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
| Pre-commit hook would fail | Run `tsc --noEmit` and `eslint` proactively in Phase 8. |

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
- **Defer to project-level CLAUDE.md** when present.
