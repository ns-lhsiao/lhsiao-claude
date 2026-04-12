---
name: boot-bugfix
description: >-
  Bootstraps a bug fix workflow. Investigates the bug first, then implements the
  fix, self-reviews, opens a PR, and lands it. Always collaborative since bugs
  require understanding before fixing. Triggers on "/boot-bugfix" or when the
  user wants to fix a bug with a structured workflow.
argument-hint: "<ENG-1234 | issue# | bug description>"
allowed-tools: Bash(*), Read, Write, Edit, Grep(*), Glob(*), Task, WebFetch, AskUserQuestion
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

## PHASE 5b: Manual Validation (mf-client changes only)

**Gate:** Only run this phase if the fix touches files under
`netskope-ng-base/frontends/mf-client/`.

1. Check if the dev environment is already running (look for processes on ports
   `9797`, `8017`, or the webui watch build). If not running, invoke
   `/init-dev-env` to start the full local stack.
2. Once the dev environment is up, invoke `/mf-client-playwright` to launch a
   headed browser, auto-login, and pause for manual testing.
3. Ask the user to verify the fix in the browser and confirm it works before
   proceeding to commit.

If the user reports the fix doesn't work, return to **Phase 4** to iterate.

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
