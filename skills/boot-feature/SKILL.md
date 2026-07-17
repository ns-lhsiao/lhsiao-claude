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

### Step 2.5: OpenSpec Proposal (Design Planning)

Before writing any code, produce a spec-driven design proposal:

1. Check whether the worktree root contains an `openspec/` directory.
   - If **yes**, invoke `/opsx:new "<short feature description derived from the Jira summary>"`.
   - If **no**, ask the user: "This repo isn't initialized for OpenSpec. Run
     `openspec init` now, or skip OpenSpec for this task?" Proceed based on the answer.
2. Review the generated proposal/specs/design/tasks artifacts with the user before
   implementation. Confirm scope and approach.

### Step 3: Explore and Implement

1. Use `Glob` and `Grep` to understand relevant code structure.
2. Read project-level CLAUDE.md if it exists for repo conventions.
3. Implement the change collaboratively — show the user what you're doing, explain
   trade-offs, and check in at natural milestones.
4. Run tests and lint as you go (detect from `Makefile`, `go.mod`, `package.json`, etc.).

### Step 3.5: Playwright Validation (UI features only)

After implementation, validate the changed UI flow end-to-end using Playwright with `headless: false, channel: 'chrome'` (devbox WebUI rejects headless Chromium).

**Playwright is not in `mf-client node_modules`** — install in `/tmp/pw-runner`:
```bash
cd /tmp && mkdir -p pw-runner && cd pw-runner && npm init -y && npm install playwright
```

**Key patterns** (from LEARNINGS.md):
- Webui uses hash routing: `/ns#/settings?view=...` (not `/#/...`)
- SPA navigation: use `page.evaluate(() => { window.location.hash = '#/...'; })` — never `page.goto()` for hash changes (triggers full reload + 30–60s mf-client bootstrap)
- Login: `waitForFunction(() => !window.location.hash.includes('/login'), { timeout: 30000 })` after clicking sign-in button; dismiss welcome wizard with `text=skip this step`
- Click Angular components via `page.mouse.click(x, y)` at `getBoundingClientRect()` coords — raw `element.click()` doesn't fire Angular `(click)` bindings
- Confirm modals: match button text case-insensitively (e.g. `/^continue$/i`)
- XHR ordering: wait for status-check XHR response before clicking confirm button

**Skip this step** if the change has no UI surface (model/helper/controller-only changes with no new UI flow to exercise).

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
2. **OpenSpec proposal**: if the worktree has `openspec/`, invoke
   `/opsx:new "<description>"` before implementing. Otherwise ask whether
   to run `openspec init` or skip.
3. Implement collaboratively (same as Step 3 in Phase 2B).
4. Commit with Conventional Commits style (no Jira prefix).
5. Open PR via `/github-pr-creator`.

---

## PHASE 3: Capture Learnings

Invoke `/learn` at the end of the session to harvest any learnings.
