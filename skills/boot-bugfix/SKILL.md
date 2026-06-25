---
name: boot-bugfix
description: >-
  Bootstraps a bug fix workflow. Investigates the bug first, then implements the
  fix, self-reviews, opens a PR, and lands it. Always collaborative since bugs
  require understanding before fixing. Triggers on "/boot-bugfix" or when the
  user wants to fix a bug with a structured workflow.
argument-hint: "<ENG-1234 | issue# | bug description>"
allowed-tools: Bash(*), Bash(playwright-cli:*), Read, Write, Edit, Grep(*), Glob(*), Task, WebFetch, AskUserQuestion
user-invocable: true
---

# Boot Bugfix

**Emit "Skill activated: boot-bugfix"**

Bug fixes are always collaborative — you need to understand the problem before
committing to a fix. This skill guides a structured investigate-then-fix workflow.

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

If insufficient detail, ask the user for clarification before proceeding.

---

## PHASE 2: Investigate

### 2a: Trace the Code Path

- Use `Grep` and `Glob` to find relevant code based on error messages, function
  names, or symptoms.
- Read the source files. Trace the logic path that leads to the bug.
- Check for recent changes: `git log --oneline -20 -- <relevant files>`

### 2b: Form Hypothesis

Based on code reading, state your hypothesis for the root cause:
- What specific condition triggers the bug?
- Why does the current code produce the wrong behavior?
- What is the minimal fix?

Present the hypothesis to the user for confirmation before proceeding to fix.

---

## PHASE 3: Set Up Workspace

Once root cause is understood and the user agrees on the approach:

- If a Jira ticket exists: invoke `/start-task <ticket>` to create branch + workspace
- If a GitHub Issue exists: create worktree manually following `~/.claude/CLAUDE.md` conventions
- If no ticket: create worktree with a descriptive slug

---

## PHASE 4: Implement the Fix

1. Make the minimal change that addresses the root cause.
2. Add or update tests to cover the bug scenario — the test should fail without
   the fix and pass with it.
3. Run tests and lint (detect from `Makefile`, `go.mod`, `package.json`, etc.).
4. Fix any test/lint failures (max 3 attempts per validation step).

---

## PHASE 4b: Coverage Verification

Ensure new code has **>90% test coverage** (SonarQube quality gate).

1. Identify changed files: `git diff <base-branch> --name-only -- '*.ts' '*.tsx'`
   (exclude test files themselves).
2. Run tests with JSON coverage for each changed source file:
   ```bash
   npm test -- --testPathPattern='<relevant-test>' \
     --coverage --collectCoverageFrom='<changed-file>' \
     --watchAll=false --coverageReporters=json
   ```
3. Parse `coverage/coverage-final.json` and cross-reference statement/branch
   maps against the diff line numbers. Only lines that appear in the diff
   count as "new code".
4. If new-code coverage is below 90%, add tests targeting uncovered lines
   and re-run. Repeat until the gate passes.
5. Report new-code coverage to the user before proceeding.

---

## PHASE 5: Self-Review

Before opening a PR, do a quick self-review:

1. `git diff` the changes.
2. Check for:
   - Unintended side effects
   - Missing edge cases
   - Test coverage of the fix
   - Any secrets or debug artifacts accidentally included
3. Report the self-review findings to the user.

---

## PHASE 5b: Browser Validation (UI changes only)

**Gate:** Only run this phase if the fix touches UI files (mf-client under
`netskope-ng-base/frontends/mf-client/`, or webui2 under `apps/`/`packages/`).

Drive the validation yourself with **`playwright-cli`** — do NOT launch a headed
browser. Headed mode steals window focus and interrupts the user. Every command
runs headless by default; never pass `--headed`.

### 1. Ensure dev environment is running

Check for the local stack (ports `9797`/`8017` for mf-client, `3000` for webui2).
If not running, invoke `/init-dev-env` first.

### 2. Plan validation steps

Produce a numbered validation plan from the changed files and bug description
(what to check, selector, pass condition). Present it before executing.

### 3. Reuse a persistent session

`playwright-cli` keeps a browser session alive across invocations via its daemon.
Use a stable session name so repeat runs reuse the same browser instead of
spawning orphans:

```bash
playwright-cli list                      # show live sessions
playwright-cli -s=bugfix open            # headless by default; reuses if exists
```

### 4. Read credentials and log in (only if needed)

```bash
source /Users/lhsiao/.claude/skills/mf-client-playwright/.env
```

Check the current URL; only run the login flow when on `about:blank`/`/login`/
`/locallogin`. SPA navigation uses hash assignment, NOT `goto` (a full reload
loses the session and re-bootstraps the micro-frontend for 30–60s):

```bash
playwright-cli -s=bugfix eval "() => { window.location.hash = '#/<route>'; }"
```

Wait for a known readiness element before asserting (micro-frontend load is slow).

### 5. Assert and capture proof

For each planned step, perform the action/assertion, then capture a screenshot
as evidence:

```bash
playwright-cli -s=bugfix screenshot --filename /tmp/bugfix-step-N.png
```

Use `--full-page` when the assertion target may be below the fold.

### 6. Report with proof

Present a PASS/FAIL summary to the user and **attach the screenshots** as proof
of the validated behavior (Read each `/tmp/bugfix-step-N.png` so it renders).
Leave the session alive for reuse; do not `close`.

If any step fails, return to **Phase 4** to iterate.

---

## PHASE 6: Commit and PR

### Commit
- If Jira ticket: invoke `/git-jira-commit` (generates `fix(ENG-1234): ...` message)
- If GitHub Issue: commit manually with `fix: <description>` and `#N` reference

### Open PR
Invoke `/github-pr-creator` to create the PR with template and suggested reviewers.

Invoke `/code-review <pr#>` for an automated review pass if the user wants one.

---

## PHASE 7: Land

Remind the user they can run `/finish-up <pr#>` once reviews and CI are green.

---

## PHASE 8: Capture Learnings

Invoke `/learn` to harvest any learnings — bug investigations are often the most
valuable source of new entries for LEARNINGS.md.
