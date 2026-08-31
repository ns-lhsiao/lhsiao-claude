---
name: boot-bugfix
description: >-
  Bootstraps a bug fix workflow. Explores the bug WITH the user first to pin down
  root cause + validation criteria, then runs autonomously: OpenSpec fast-forward,
  apply the fix, validate with headless Playwright, emit an HTML report, archive the
  change, and ship the PR. Triggers on "/boot-bugfix" or when the user wants to fix
  a bug with a structured workflow.
argument-hint: "<ENG-1234 | issue# | bug description>"
allowed-tools: Bash(*), Bash(playwright-cli:*), Read, Write, Edit, Grep(*), Glob(*), Task, WebFetch, AskUserQuestion, Skill
user-invocable: true
---

# Boot Bugfix

**Emit "Skill activated: boot-bugfix"**

Bug fixes need understanding before committing to a fix. This skill front-loads ALL
human collaboration into a single explore gate, then runs the fix autonomously
through to a shipped PR. One conversation up front; hands-off after.

Flow: **explore (human) → ff → apply → validate → report → archive → PR (autonomous)**

## Context

$ARGUMENTS

---

## PHASE 1: Identify the Bug

Parse `$ARGUMENTS` for context:

| Input | Action |
|-------|--------|
| Jira ticket (`ENG-1234`) | Fetch details via Atlassian MCP tool |
| GitHub Issue (`#N`, URL, `org/repo#N`) | Fetch via `gh issue view` |
| Plain description | Use as-is, may need clarification |

Gather:
- **Symptoms**: error messages, unexpected behavior, affected users/environments
- **Reproduction steps**: if known
- **Affected area**: service, module, file paths if mentioned

---

## PHASE 2: Explore (the ONLY human gate) — REQUIRED

Invoke **`/opsx:explore`** with the bug context. This is the single collaborative
checkpoint; do not skip it. Explore mode is thinking-only — no code written here.

**If the affected area is in the `webui` repo** (paths under `src/webui/...`), invoke
`/graphify-webui "<bug context>"` FIRST, before any manual Grep/Glob tracing — it queries
the persistent Angular/PHP knowledge graphs for graph-grounded orientation (existing
components/controllers/services touching the area, call relationships) and is cheaper than
cold-grepping the tree. Use its answer to seed the root-cause hypothesis below, then
confirm/refine with direct Read (graph may be up to 7 days stale — verify anything load-bearing).

Drive the exploration to lock down, WITH the user:

1. **Root cause** — trace the code path (`Grep`/`Glob`/`Read`), check recent changes
   (`git log --oneline -20 -- <files>`), and state the hypothesis for the triggering
   condition and the minimal fix.
2. **Development detail** — which files change, the approach, base branch (check Jira
   `fixVersion` → release branch vs `develop`), any serialization/parity concerns.
3. **Validation detail** — the concrete pass/fail criteria the fix must satisfy:
   - Unit/coverage targets.
   - For UI fixes: the exact route, selector, and observable pass condition to drive
     with Playwright in Phase 5.

Confirm root cause + dev detail + validation detail with the user before leaving
explore. This confirmation is the LAST human gate — everything after runs autonomously.

**Gate exit criteria:** the user has agreed on root cause, the change approach, and the
validation criteria. Capture the validation criteria verbatim — Phase 5 and the HTML
report both consume them.

---

## PHASE 3: Fast-Forward Artifacts — autonomous

Invoke **`/opsx:ff`** with a kebab-case change name derived from the bug (e.g.
`fix-auth-token-expiry`). This creates the OpenSpec change and generates ALL artifacts
(proposal, specs, tasks) needed to implement.

Feed `ff` the root cause, dev detail, and validation criteria settled in Phase 2 so the
tasks encode them. Do NOT stop for confirmation — the explore gate already covered intent.

If the repo has no `openspec/` directory, stop and ask the user whether to
`openspec init` first (per global CLAUDE.md); do not silently skip OpenSpec.

---

## PHASE 4: Set Up Workspace + Apply — autonomous

1. **Workspace**: if a Jira ticket exists, invoke `/start-task <ticket>` (branch +
   worktree). Otherwise create a worktree per `~/.claude/CLAUDE.md` conventions with a
   descriptive slug. All edits happen inside the worktree.
   > After `git worktree add`, re-grep every target symbol INSIDE the worktree before
   > any Read-by-offset or Edit — line numbers from the primary checkout do not transfer.

2. **Apply**: invoke **`/opsx:apply`** for the change to implement the tasks. No human
   confirm. Then:
   - Add/update tests covering the bug scenario — must fail without the fix, pass with it.
   - Run tests + lint (detect from `Makefile`, `go.mod`, `package.json`, etc.).

3. **Coverage** (TS/TSX changes): ensure **>90% new-code coverage** (SonarQube gate).
   Identify changed source files (`git diff <base> --name-only -- '*.ts' '*.tsx'`,
   exclude tests), run coverage with `--coverageReporters=json`, cross-reference
   `coverage/coverage-final.json` maps against diff line numbers, add tests for
   uncovered lines, repeat until ≥90%.

### Failure policy — auto-iterate then stop

On any test/lint/coverage failure, iterate the fix (re-enter apply/edit) up to
**3 attempts per validation step**. If still failing after 3, **STOP** and surface the
failure to the human — do NOT proceed to report, archive, or PR.

---

## PHASE 5: Browser Validation (UI changes only) — autonomous

**Gate:** run only if the fix touches UI files (mf-client under
`netskope-ng-base/frontends/mf-client/`, mf-cfw under `mf-cfw/`, or webui2 under
`apps/`/`packages/`). Non-UI fixes skip this phase and rely on Phase 4 tests.

Delegate to **`/boot-playwright <recipe> <slug>`** — do NOT hand-roll dev-env
bootstrap or `playwright-cli` steps here; `boot-playwright` owns all of that.

1. **Pick the recipe** from the files touched in Phase 4 (do not guess if mixed —
   ask):

   | Touched path | Recipe |
   |---|---|
   | `netskope-ng-base/frontends/mf-client/` | `webui-angular-devbox-mf-client` |
   | `mf-cfw/` | `webui-angular-devbox-mf-cfw` |
   | webui2 `apps/`/`packages/` (Balkan hybrid) | `webui2-angular-shell-devbox` |
   | webui Angular Settings pages, no MFE involved | `webui-angular-devbox` |

2. **Invoke**: `/boot-playwright <recipe> <slug>`, using the SAME slug as the
   Phase 4 worktree, with the Phase 2 validation criteria as context (turned into
   a numbered plan: action, selector, pass condition — `boot-playwright` follows
   this format).
3. **Result**: `boot-playwright` reports PASS/FAIL per step with screenshot paths,
   using a `playwright-cli` session it leaves open (never closes) — capture both
   for Phase 6's report.

**Failure policy:** if any step FAILs, return to **Phase 4** and iterate (respecting the
3-attempt cap). If still failing, STOP and surface to the human — no report, no archive,
no PR.

---

## PHASE 6: HTML Report — autonomous

Only reached when all prior validation PASSED. Write an HTML report to
`/Users/lhsiao/ns/git/all-html/<project>/<name>.html` (`<project>` = kebab slug for the
bug/repo), per global CLAUDE.md. The report MUST include:

- **Fix detail**: root cause, the change made, files touched, base branch, OpenSpec
  change name, `git diff` summary.
- **Validation detail**: the Phase 2 criteria, unit/coverage results (new-code %), and
  for UI fixes the numbered Playwright plan with per-step PASS/FAIL and embedded/linked
  screenshots (`/tmp/bugfix-step-N.png`).

Then update `/Users/lhsiao/ns/git/all-html/index.html` in the SAME turn: add a `<li>`
under the matching `<project>` `<h2>` (create the group if new), bump its `(N)` count,
and include `data-tags`, a `.snippet` div, and 2–4 `.tags` chips (reuse existing tag
classes — e.g. `bugfix`, `validation`, `playwright-e2e` — or add a `.tag-<name>` CSS
rule if inventing one).

---

## PHASE 7: Archive — autonomous

Invoke **`/opsx:archive`** for the change to move it to the archived set now that the
fix is implemented and validated.

---

## PHASE 8: Commit + Ship PR — autonomous

### Commit
- Jira ticket: invoke `/git-jira-commit` (`fix(ENG-1234): ...`).
- GitHub Issue: commit manually with `fix: <description>` and a `#N` reference.

### Open PR
Invoke `/github-pr-creator` to create the PR (template + suggested reviewers). Link the
HTML report path in the PR body. Optionally invoke `/code-review <pr#>` for an automated
review pass.

Remind the user they can run `/finish-up <pr#>` once reviews + CI are green.

---

## PHASE 9: Capture Learnings

Invoke `/learn` to harvest learnings — bug investigations are the most valuable source of
new LEARNINGS.md entries.
