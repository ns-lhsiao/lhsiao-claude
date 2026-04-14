---
name: boot-troubleshoot
description: >-
  Bootstraps a structured troubleshooting session. Scopes the problem, gathers
  evidence from code/logs/config, forms and tests hypotheses, and captures
  learnings. Triggers on "/boot-troubleshoot" or when the user wants to
  investigate, debug, or diagnose an issue systematically.
argument-hint: "<problem description or Jira ticket>"
allowed-tools: Bash(*), Read, Grep(*), Glob(*), WebFetch, Task, AskUserQuestion
user-invocable: true
---

# Boot Troubleshoot

**Emit "Skill activated: boot-troubleshoot"**

## Context

$ARGUMENTS

---

## PHASE 1: Scope the Problem

Parse `$ARGUMENTS` for context. If a Jira ticket is referenced, fetch it via the
Atlassian MCP tool for details. If a PR or GitHub issue is referenced, fetch via `gh`.

Ask the user to confirm or refine:
1. **What is the observed behavior?** (error message, unexpected output, failure mode)
2. **What is the expected behavior?**
3. **When did it start?** (deploy, config change, recent PR)
4. **What has already been tried?**
5. **GitHub context** — which branch, PR, or environment is affected? (e.g., `staging`,
   `release/YYYYMM.N`, a specific PR number). If the bug is environment-specific (qa01
   vs prod), the correct branch must be identified before code analysis begins — do NOT
   default to the primary checkout or `master`.

If the user provided enough detail in `$ARGUMENTS`, skip the questions and proceed.
If the user specified a repo but not a branch, ask which branch or environment to
investigate before starting Phase 2.

---

## PHASE 2: Gather Evidence

Run these in parallel where independent:

### 2a: Code Analysis
- Use `Grep` and `Glob` to find relevant code paths based on error messages,
  function names, or config keys mentioned in the problem description.
- Read the relevant source files to understand the logic.

### 2b: Recent Changes
- Check `git log` for recent commits touching the relevant files.
- Check for recent PRs that may have introduced the issue.

### 2c: Configuration & Environment
- Check relevant config files, environment variables, feature flags, or
  control flags that may affect the behavior.

### 2d: External Context
- If the problem references external services, APIs, or documentation,
  use `WebFetch` to gather context.

For complex investigations with multiple independent threads, spawn parallel
`Explore` sub-agents via `Task` to cover more ground.

---

## PHASE 3: Hypothesize and Test

1. Form **2-4 working hypotheses** based on the evidence gathered.
2. For each hypothesis:
   - State what would be true if this hypothesis is correct.
   - Identify a concrete check that would confirm or refute it.
   - Run the check (read code, grep for patterns, trace logic).
3. Eliminate hypotheses that don't match the evidence.
4. If all hypotheses are eliminated, gather more evidence and form new ones.

---

## PHASE 4: Report Findings

Present results to the user:

1. **Root cause** — what is actually happening and why (with file paths and line numbers)
2. **Evidence** — the specific code, logs, or config that confirms the root cause
3. **Suggested fix** — concrete next steps, referencing specific files and lines
4. **Confidence** — how confident you are, and what gaps remain

If the root cause is unclear, be honest about it. State what was ruled out and
what avenues remain unexplored.

---

## PHASE 5: Act on Findings

Ask the user:
- **Fix it now** — proceed to create a worktree and implement the fix (follows
  the manual bug-fix workflow: worktree -> fix -> commit -> PR)
- **File a ticket** — create a Jira ticket with the findings using `/jira-ticket-creator`
- **Just the analysis** — stop here, the user will handle next steps

---

## PHASE 6: Capture Learnings

Invoke the `/learn` skill to harvest any learnings from the investigation,
regardless of the outcome chosen in Phase 5.
