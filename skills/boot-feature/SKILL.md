---
name: boot-feature
description: >-
  Bootstraps a feature implementation workflow. Routes between fully autonomous
  (/quick-implement for GitHub Issues) and collaborative (manual chain with
  /start-task, /git-jira-commit, /github-pr-creator, /finish-up for Jira tickets).
  Triggers on "/boot-feature" or when the user wants to implement a new feature.
argument-hint: "<issue# | ENG-1234 | issue-url | description>"
allowed-tools: Bash(*), Read, Write, Edit, Grep(*), Glob(*), Task, WebFetch, AskUserQuestion
user-invocable: true
---

# Boot Feature

**Emit "Skill activated: boot-feature"**

## Context

$ARGUMENTS

---

## PHASE 1: Classify Input

Parse `$ARGUMENTS` to determine the source and routing:

| Input | Route |
|-------|-------|
| GitHub Issue (URL, `org/repo#N`, bare `#N`) | **Autonomous** via `/quick-implement` |
| Jira ticket (`ENG-1234` or similar) | **Collaborative** manual chain |
| Plain description (no ticket reference) | Ask user which path |
| `next` / `pick` keyword | **Autonomous** via `/quick-implement next` |

If the input is a plain description with no ticket:
- Ask the user: **Create a Jira ticket first**, **Create a GitHub Issue first**,
  or **Just start coding** (skip ticket creation).

---

## PHASE 2A: Autonomous Path (GitHub Issue)

Invoke `/quick-implement` with the issue reference. This skill handles the entire
lifecycle autonomously — no further action needed from this skill.

Read `~/.claude/skills/quick-implement/SKILL.md` and execute its full procedure.

---

## PHASE 2B: Collaborative Path (Jira Ticket)

### Step 1: Set Up Workspace

Invoke `/start-task` with the Jira ticket key. This creates the branch and workspace.

### Step 2: Understand the Requirement

1. Fetch the Jira ticket details via the Atlassian MCP tool.
2. If the ticket body contains external URLs (design docs, RFCs, Confluence pages),
   fetch them for context.
3. Summarize the deliverables and confirm understanding with the user.

### Step 3: Explore and Implement

1. Use `Glob` and `Grep` to understand relevant code structure.
2. Read project-level CLAUDE.md if it exists for repo conventions.
3. Implement the change collaboratively — show the user what you're doing, explain
   trade-offs, and check in at natural milestones.
4. Run tests and lint as you go (detect from `Makefile`, `go.mod`, `package.json`, etc.).

### Step 4: Commit

Invoke `/git-jira-commit` to stage, generate a Jira-prefixed commit message, and commit.

### Step 5: Open PR

Invoke `/github-pr-creator` to create the PR with the repo's template and suggest reviewers.

### Step 6: Land (when ready)

Remind the user they can run `/finish-up <pr#>` once reviews and CI are green.

---

## PHASE 2C: No Ticket — Just Start Coding

1. Create a worktree using the convention from `~/.claude/CLAUDE.md`:
   ```bash
   GH_USER=$(gh api user --jq .login)
   SLUG=<derived from description>
   BRANCH="${GH_USER}/${SLUG}"
   ```
2. Implement collaboratively (same as Step 3 in Phase 2B).
3. Commit with Conventional Commits style (no Jira prefix).
4. Open PR via `/github-pr-creator`.

---

## PHASE 3: Capture Learnings

Invoke `/learn` at the end of the session to harvest any learnings.
