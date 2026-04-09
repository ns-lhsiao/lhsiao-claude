---
name: quick-implement
description: >-
  Implements a GitHub Issue end-to-end: creates a worktree and topic branch,
  writes the code, opens a PR, monitors CI with iterative fixes, squash-merges
  via API, and cleans up local artifacts. Fully autonomous — no user interaction.
argument-hint: "<issue# | repo#issue | org/repo#issue | issue-url | next>"
allowed-tools: Bash(*), Read, Write, Edit, Grep(*), Glob(*), Task, WebFetch
user-invocable: true
---

# Quick Implement

**Emit "Skill activated: quick-implement"**

Fully autonomous end-to-end implementation of a GitHub Issue — from branch creation through
merged PR and cleanup. No user interaction at any point. Every exit path cleans up the
worktree and local branch.

## Context

$ARGUMENTS

---

## PHASE 1: Argument Parsing

Parse `$ARGUMENTS` into `$ORG`, `$REPO`, `$ISSUE_NUMBER` using the first matching form:

| Input Form | Example | Parsing |
|------------|---------|---------|
| URL | `https://github.com/netSkope/helios/issues/42` | Regex extract org, repo, number |
| Fully qualified | `netSkope/helios#42` | Split on `/` and `#` |
| Repo-scoped | `helios#42` | Default `$ORG=netSkope` |
| Bare number | `42` | Infer org/repo from local git remote (see below) |
| Pick keyword | `next`, `whichever`, `whatever`, `pick one`, `any` | Auto-select an open issue (see below) |

### Pick Keyword Detection

If `$ARGUMENTS` (case-insensitive, trimmed) matches any of: `next`, `whichever`, `whatever`,
`something`, `pick one`, `pick`, `any`, `surprise me` — treat the input as **auto-select mode**.

1. Infer `$ORG/$REPO` from the local git remote:
   ```bash
   gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
   ```
   If not in a git repo, bail: "Cannot infer repository from current directory."

2. The argument may optionally be prefixed with a repo qualifier (`helios next`,
   `netSkope/helios next`). If present, parse the qualifier for `$ORG`/`$REPO`,
   then treat the trailing keyword as the pick trigger.

3. Fetch open issues sorted by creation date (oldest first):
   ```bash
   gh issue list --repo $ORG/$REPO --state open -S "sort:created-asc" \
     --json number,title,labels,assignees --limit 20
   ```
   Iterate through results. Skip issues where `assignees` is non-empty (already claimed).

   Classify each unassigned issue into a **priority bucket**:
   - **Bucket 1 (highest)**: any label is `task` — already decomposed, immediate value
   - **Bucket 2**: no `task` or `plan` label — simple standalone work
   - **Bucket 3 (lowest)**: any label is `plan` — requires decomposition overhead

   Select the first issue from the highest-priority non-empty bucket as `$ISSUE_NUMBER`.

4. If no qualifying issue is found, bail: "No unassigned open issues found in $ORG/$REPO."

5. Log the selection: "Auto-selected issue #$ISSUE_NUMBER: <title>"

### Bare Number Inference

```bash
gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
```

If not in a git repo or remote is ambiguous, bail with a clear error message.

### Validation

- `$ISSUE_NUMBER` must be a positive integer
- `$ORG` and `$REPO` must match `^[a-zA-Z0-9_.-]+$`

---

## PHASE 2: Issue Fetch

```bash
gh issue view $ISSUE_NUMBER --repo $ORG/$REPO --json title,body,labels,state
```

- **Closed** -> exit: "Issue #$ISSUE_NUMBER is already closed."
- **404** -> exit: "Issue #$ISSUE_NUMBER not found in $ORG/$REPO."
- **Empty body** -> warn "Issue body is empty; proceeding with title-only guidance.", continue.

### Derive Slug

Derive `$SLUG` from the issue title:
1. Lowercase, replace non-alphanumeric with hyphens, collapse consecutive hyphens
2. Strip leading/trailing hyphens
3. Truncate to 40 characters (break at hyphen boundary if possible)

---

## PHASE 2.5: Plan Triage

If none of the issue's labels is `plan`, skip to Phase 3.

If the issue **is** labeled `plan`, determine whether it can be implemented as a single
unit or needs decomposition into task issues.

### Triage Criteria

Two independent axes. Either one is sufficient to force decomposition; both must be
satisfied for the plan to remain a single unit.

#### Axis 1: Logical Boundaries

Assess whether the plan's objectives are **sufficiently disjoint** to warrant separate
tasks. Indicators: changes spanning independent packages with no coupling, multiple
deliverables that could be merged in any order, or numbered steps mapping to separate
code changes. Tightly coupled files serving a single logical change should stay together.

#### Axis 2: Context Window Budget

Each implementing agent has an effective context window budget of **80,000 tokens**.
Estimate token cost by considering source files to read, code to write, tests to produce,
and tool-call overhead. If the plan as a single unit risks exceeding 80k tokens, split
into tasks that each fit within budget.

#### Decision Rule

| Logical Boundaries | Context Budget | Decision |
|---------------------|----------------|----------|
| Single boundary | Fits within 80k | **Implement as-is** — continue to Phase 3 |
| Single boundary | Exceeds 80k | **Decompose** — split along natural sub-units |
| Multiple disjoint | Fits within 80k | **Decompose** — one task per boundary |
| Multiple disjoint | Exceeds 80k | **Decompose** — split further if needed |

**Default**: if ambiguous on both axes, treat as implementable as-is.

### Implementable As-Is

Treat the issue as a normal implementable unit and continue to Phase 3.

### Needs Decomposition

#### Task Issue Creation

For each decomposed task:
```bash
gh issue create \
  --repo $ORG/$REPO \
  --label task \
  --title "Plan #$ISSUE_NUMBER: Task $N: <task description>" \
  --body "$(cat <<'EOF'
<Prose description of what this task should accomplish.
Include relevant context from the parent plan.>

Parent plan: #$ISSUE_NUMBER
EOF
)"
```

Store the created issue numbers in `$TASK_ISSUES` (ordered array).

#### Dependency Analysis

Classify tasks into **tiers** based on dependency ordering:
- **Tier 0**: no dependencies (can run in parallel)
- **Tier 1**: depend on Tier 0 completing first
- **Tier N**: depend on Tier N-1

Determine tiers by analyzing overlapping files or output/input dependencies.
When in doubt, serialize.

Proceed to Phase 2.6.

---

## PHASE 2.6: Task Orchestration

Executes only for decomposed plan issues. For each tier, from 0 to N:

### Step 2.6.1: Fast-Forward Trunk

```bash
git -C $REPO_DIR pull --ff-only
```

### Step 2.6.2: Create Worktrees Sequentially

For each task in the current tier, create the worktree from trunk. Do this
**sequentially** to avoid git lock contention.

### Step 2.6.3: Spawn Sub-Agents in Parallel

Spawn one `Task` tool call per task, all in the same message. Each sub-agent prompt:

```
Implement GitHub issue #$TASK_ISSUE in $ORG/$REPO autonomously.
Read ~/.claude/skills/quick-implement/SKILL.md for the full procedure.
Execute Phases 5 through 9 (skip Phases 3-4 — worktree is already prepared).

Parameters:
- $ORG, $REPO, $ISSUE_NUMBER = <task issue number>
- Worktree path: <path> (already created, cd into it)
- Trunk path: <trunk path>
- $DEFAULT_BRANCH = <branch>
- $BRANCH = <branch name>

The issue title is: <title>
The issue body is: <body>

Follow all conventions from the skill and from ~/.claude/CLAUDE.md.
```

### Step 2.6.4: Wait and Advance

Wait for all sub-agents in this tier to complete. Then fast-forward trunk before
starting the next tier.

### Step 2.6.5: Close Plan Issue

After all tiers complete successfully:
```bash
gh issue close $ISSUE_NUMBER --repo $ORG/$REPO \
  --comment "All tasks implemented and merged."
```

If any task failed, do **not** close the plan. Comment with a summary of successes
and failures.

### Plan Mode Summary Output

```
Plan:      $ORG/$REPO#$ISSUE_NUMBER — <title>
Tasks:     N created, M merged, K failed
  Task #A: <title> — merged (PR #X)
  Task #B: <title> — failed (PR #Z open)
Plan:      closed | open (partial failure)
```

---

## PHASE 3: Repo Setup

### Step 3.1: Find or Clone Repo

The trunk clone lives in the current working directory as `$REPO-trunk`.

```bash
REPO_DIR="${REPO}-trunk"

if ! gh repo view $ORG/$REPO &>/dev/null; then
  echo "Error: Repository $ORG/$REPO not found"
  exit 1
fi

if [ ! -d "$REPO_DIR" ]; then
  git clone git@github.com:$ORG/$REPO.git $REPO_DIR
fi
```

### Step 3.2: Fetch and Detect Default Branch

```bash
cd $REPO_DIR
git fetch origin
```

Detect `$DEFAULT_BRANCH`:
```bash
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
if [ -z "$DEFAULT_BRANCH" ]; then
  DEFAULT_BRANCH=$(gh repo view $ORG/$REPO --json defaultBranchRef --jq '.defaultBranchRef.name')
fi
```

---

## PHASE 4: Worktree + Branch

### Step 4.1: Compute Names

```bash
GH_USER=$(gh api user --jq .login)
BRANCH="${GH_USER}/${ISSUE_NUMBER}-${SLUG}"
WORKTREE_DIR="${REPO}-${SLUG}"
```

### Step 4.2: Check for Conflicts

Bail if the branch already exists locally or on the remote:
```bash
if git show-ref --verify --quiet refs/heads/$BRANCH; then
  echo "Error: Local branch $BRANCH already exists."
  exit 1
fi
if git ls-remote --exit-code --heads origin $BRANCH &>/dev/null; then
  echo "Error: Remote branch $BRANCH already exists."
  exit 1
fi
```

Also check if the worktree directory already exists:
```bash
if [ -d "../$WORKTREE_DIR" ]; then
  echo "Error: Worktree directory $WORKTREE_DIR already exists."
  exit 1
fi
```

### Step 4.3: Create Worktree

```bash
git worktree add ../$WORKTREE_DIR -b $BRANCH origin/$DEFAULT_BRANCH
cd ../$WORKTREE_DIR
```

### Step 4.4: Read Project CLAUDE.md

If a project-level `CLAUDE.md` exists in the worktree root, read it to absorb repo-specific
conventions (commit style, test commands, lint config, directory layout, etc.).

---

## PHASE 5: Implementation

This phase has **high degrees of freedom**. The goal is to produce a correct, tested,
lint-clean implementation that satisfies the issue requirements.

### Step 5.1: Understand the Issue

1. Re-read the issue title and body carefully.
2. If the issue body contains external URLs (docs, RFCs, design documents), fetch them
   via `WebFetch` to gather context.
3. Identify the concrete deliverables: files to create, modify, or delete.

### Step 5.2: Explore the Codebase

Use `Glob` and `Grep` to understand the repo structure. For complex repos, spawn
`Explore` sub-agents via the `Task` tool to parallelize discovery.

Key questions:
- Where does similar functionality live?
- What patterns does the codebase use (naming, error handling, testing style)?
- Are there existing abstractions to build on?

### Step 5.3: Implement the Change

Use `Write` and `Edit` tools. Follow conventions from Steps 4.4 and 5.2. Keep changes
minimal — implement exactly what the issue asks for.

### Step 5.4: Detect Language and Validate

Detect the project's language/tooling from marker files and run validation:

| Marker File | Language | Test Command | Lint Command |
|-------------|----------|-------------|-------------|
| `go.mod` | Go | `go test ./...` | `golangci-lint run` |
| `package.json` | Node.js | `npm test` | `npm run lint` |
| `pyproject.toml` | Python | `pytest` | `ruff check .` |
| `Cargo.toml` | Rust | `cargo test` | `cargo clippy` |

**Makefile overrides**: If a `Makefile` exists, check for `test` and `lint` targets.
Prefer `make test` / `make lint` over the language-specific defaults.

**No markers found**: Log "No recognized language markers — skipping automated
validation." and proceed.

### Step 5.5: Fix Failures

If tests or lint fail, fix the code and re-run. Maximum **3 attempts** per validation step.

If still failing after 3 attempts:
1. Revert all uncommitted changes: `git checkout -- .`
2. Remove the worktree and branch (see Phase 9 cleanup)
3. Exit with: "Unable to produce a passing implementation after 3 attempts. Issue left open."

---

## PHASE 6: Commit + Push + PR

### Step 6.1: Infer Commit Type

Map issue labels to Conventional Commit types:

| Label | Type |
|-------|------|
| `bug` | `fix` |
| `enhancement` | `feat` |
| `documentation` | `docs` |
| `refactor` | `refactor` |
| _(default)_ | `feat` |

Use the first matching label. If multiple labels match, prefer `fix` > `feat` > others.

### Step 6.2: Commit

```bash
git add -A
git commit -m "$(cat <<'EOF'
<type>: <concise subject derived from issue title>

<1-2 sentence explanation of why this change was made.>

#$ISSUE_NUMBER
EOF
)"
```

### Step 6.3: Push

```bash
git push -u origin $BRANCH
```

### Step 6.4: Open PR

```bash
gh pr create \
  --repo $ORG/$REPO \
  --base $DEFAULT_BRANCH \
  --head $BRANCH \
  --title "<type>: <subject>" \
  --body "$(cat <<'EOF'
<Concise prose paragraph explaining why this change was made.
High signal-to-word ratio. No bullet lists.>

Fixes #$ISSUE_NUMBER
EOF
)"
```

Store `$PR_NUMBER` from the output.

---

## PHASE 7: CI Monitoring Loop

### Step 7.1: Initial Wait

```bash
sleep 10
```

Allow checks to register.

### Step 7.2: Poll with Exponential Backoff

Poll `gh pr checks $PR_NUMBER --repo $ORG/$REPO` with intervals:
10s -> 20s -> 40s -> 80s -> 120s (cap).

**Exit conditions:**

| Condition | Action |
|-----------|--------|
| No checks registered after 5 minutes | Assume no CI. Proceed to merge. |
| All checks pass | Proceed to merge. |
| Any check fails | Attempt fix (Step 7.3). |
| 30 minutes elapsed | Bail — leave PR open, exit with message. |

### Step 7.3: Fix CI Failures

On failure:
1. Identify the failed check run ID from `gh pr checks` output.
2. Read logs: `gh run view <run-id> --log-failed --repo $ORG/$REPO`
3. Fix the code locally.
4. Run local validation (Step 5.4).
5. Commit and push the fix.
6. Re-enter the polling loop.

Maximum **3 fix attempts per failing check**. After 3 failures on the same check,
bail: leave PR open, exit with message.

---

## PHASE 8: Squash Merge (via API)

**IMPORTANT**: Use `-X PUT`, not POST. POST returns 404 on this endpoint.

```bash
gh api repos/$ORG/$REPO/pulls/$PR_NUMBER/merge \
  -X PUT \
  -f merge_method=squash \
  -f commit_title="<type>: <subject> (#$PR_NUMBER)" \
  -f commit_message="$(cat <<'EOF'
<Consolidated paragraph explaining why this change was made.>

Fixes #$ISSUE_NUMBER
EOF
)"
```

**On failure** (merge conflicts, branch protection, required reviews not met):
- Log the error.
- Leave the PR open.
- Proceed to cleanup (worktree removal only — do not delete the branch).

---

## PHASE 9: Cleanup

**Cleanup invariant**: worktree removal runs on **every exit path** — success or bail.

### Success Path (PR merged)

```bash
cd $REPO_DIR                                    # return to trunk
git worktree remove ../$WORKTREE_DIR --force    # remove worktree
git branch -d $BRANCH 2>/dev/null || git branch -D $BRANCH
git checkout $DEFAULT_BRANCH
git pull --ff-only                              # fast-forward trunk
```

### Bail Before PR Creation

```bash
cd $REPO_DIR
git worktree remove ../$WORKTREE_DIR --force
git branch -d $BRANCH 2>/dev/null || git branch -D $BRANCH
```

### Bail After PR Creation (PR left open)

```bash
cd $REPO_DIR
git worktree remove ../$WORKTREE_DIR --force
# Do NOT delete the branch — the open PR still references it
```

### Summary Output

```
Issue:     $ORG/$REPO#$ISSUE_NUMBER — <title>
PR:        <PR URL> (merged | open | not created)
Branch:    $BRANCH (deleted | retained for open PR | deleted, no PR)
Worktree:  $WORKTREE_DIR (removed)
Trunk:     $DEFAULT_BRANCH (fast-forwarded | unchanged)
```

---

## PHASE 10: Retrospective

After cleanup, invoke the `/learn` skill to harvest any learnings from the session.
This runs on every exit path — success or bail — because failed attempts are often
the most valuable source of learnings.

Read `~/.claude/skills/learn/SKILL.md` and execute its instructions.

---

## Error Handling

All error handling is autonomous. Never prompt for user input.

| Error | Recovery |
|-------|----------|
| Cannot parse arguments | Exit with usage message |
| No qualifying issue (pick mode) | Exit: "No unassigned open issues found." |
| Issue not found / closed | Exit with status |
| Repo not found | Exit with error |
| Clone fails | Exit with error |
| Branch already exists | Exit with error (do not force-delete) |
| Implementation fails validation 3x | Revert, cleanup, exit |
| CI fails 3x on same check | Leave PR open, cleanup worktree, exit |
| Merge fails | Leave PR open, cleanup worktree, exit |
| Plan triage ambiguous | Default to "implementable as-is" |
| Sub-agent fails | Log which task failed, continue with others. Leave plan open. |
| API rate limit | Wait 60s, retry once. If still limited, exit gracefully. |
| Network failure | Retry 3x with 30s backoff. Then exit. |

---

## Critical Conventions

- **No user interaction.** This skill is fully autonomous start to finish.
- **Conventional Commits** for commit messages and PR titles.
- **Squash merge only**, via API with `-X PUT`.
- **Worktree cleanup on every exit path.**
- **`Fixes #N`** on its own line at the end of the PR body.
- Follow the project's CLAUDE.md conventions when they exist.
- Follow the global `~/.claude/CLAUDE.md` conventions.
