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

### 2b.1: Origin commit & affected-version trace

Always determine **when each defective code path was first introduced**, not just
when it was last touched. The Jira `affectsVersion` is what QA observed — it
is **not** authoritative for root cause. Verify this independently before
calling anything a regression.

For each defective surface (file + symbol/markup), run:

1. **Pickaxe by code symbol or marker** — finds the commit that added it,
   regardless of file moves:
   ```bash
   git log --reverse --oneline -S '<distinctive-string>' -- <path>
   ```
   Use a token unique to the defective markup (e.g. `errorSettingsTemplate`,
   `id="error-settings"`, `showManageErrorSettingsModal`). The first row is the
   introducing commit.

2. **Confirm with `git blame` and `git log --follow --reverse`** for the file —
   the introducing commit is usually the first entry. Disambiguate when a
   later commit *re-added* the code (e.g. a framework revert that restored
   the prior shape but did not author it).

3. **Map commit → first shipping release** by walking sorted release branches:
   ```bash
   for r in $(git branch -r | grep -E 'origin/Release[0-9]+$' | sort -V); do
     if git merge-base --is-ancestor <sha> "$r" 2>/dev/null; then
       echo "FIRST CONTAINING: $r"; break
     fi
   done
   ```
   Substitute the project's release-branch naming (`Release<N>`,
   `release/YYYYMM.N`, `cfw-release/N.0`, etc.) — derive from `git branch -r`.

4. **Build an introduction timeline** — one row per defective surface, columns
   `surface | introducing commit (sha + ticket + author + date) | first
   shipping release`. If multiple defects accreted across multiple commits
   (common: original feature + later partial-fix-that-papered-over), record
   each wave separately. The reported affectsVersion should reflect the
   **earliest** introducing release among them, not the latest.

5. **Validate against current release branches** — confirm the defect is
   byte-identical across the relevant `Release<N-1>`, `Release<N>`, and
   `develop` (or equivalents). If identical, it's not a regression in `N`;
   the earlier introducing release is the correct affectsVersion.

Phase 4 must report:
- The earliest **correlated affected version** (with introducing sha + ticket).
- Whether the bug is a **regression** in the QA-reported version, or
  pre-existing debt re-surfaced by recent testing. State this explicitly.
- If the QA-reported `affectsVersion` differs from the traced one, surface the
  delta so the user can decide whether to update the ticket.

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
3. **Origin & affected version** — introducing commit(s) (sha, ticket, author,
   date) and the **first release branch** that shipped each defective surface.
   State explicitly whether this is a regression in the QA-reported version
   or pre-existing debt. If the traced affectsVersion differs from the Jira
   ticket's, surface the delta.
4. **Suggested fix** — concrete next steps, referencing specific files and lines
5. **Confidence** — how confident you are, and what gaps remain

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

## PHASE 6: Document to Confluence

Ask the user: **"Would you like the findings documented to Confluence?"**

If yes, use the `/confluence-updater` skill to create or update a page under the
troubleshooting folder:
`https://netskope.atlassian.net/wiki/spaces/~712020f420f5c3a46f4564a0597ec1ac2bfb78/folder/7508558363`

The page should include:
- Ticket summary and metadata (status, priority, assignee, tenant)
- Problem description
- Root cause analysis with evidence (DB queries, code references, log excerpts)
- User-side mitigation / workaround (if any)
- Recommended fix options
- Key code references (file paths and line numbers)

Use the Jira ticket key as the page title (e.g., `ENG-974628`). If a page with
that title already exists under the folder, update it rather than creating a new one.

---

## PHASE 7: Capture Learnings

Invoke the `/learn` skill to harvest any learnings from the investigation,
regardless of the outcome chosen in Phase 5.
