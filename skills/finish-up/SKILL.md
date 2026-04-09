---
name: finish-up
description: >-
  Verifies a PR is ready to land (reviews resolved, CI green, approved, branch current),
  squash-merges it, cleans up local worktree and branch, and fast-forwards the trunk.
  Triggers when the user wants to finish, land, merge, or close out a PR.
  Also triggers on "/finish-up".
argument-hint: "<pr# | repo#pr | org/repo#pr | pr-url>"
allowed-tools: Bash(gh:*), Bash(git:*), Bash(jq:*), Read, Grep, Glob
user-invocable: true
---

# Finish Up

**Emit "Skill activated: finish-up"**

Fully autonomous PR landing workflow — from pre-merge verification through squash-merge
and local cleanup. No user interaction at any point.

## Context

$ARGUMENTS

---

## PHASE 1: Argument Parsing

Parse `$ARGUMENTS` into `$ORG`, `$REPO`, `$PR_NUMBER` using the first matching form:

| Input Form | Example | Parsing |
|------------|---------|---------|
| URL | `https://github.com/netSkope/helios/pull/42` | Regex extract org, repo, number |
| Fully qualified | `netSkope/helios#42` | Split on `/` and `#` |
| Repo-scoped | `helios#42` | Default `$ORG=netSkope` |
| Bare number | `42` or `#42` | Infer org/repo from local git remote (see below) |

### Bare Number Inference

```bash
gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
```

If not in a git repo or remote is ambiguous, bail: "Cannot infer repository from current
directory. Use `org/repo#N` or full URL."

### Validation

- `$PR_NUMBER` must be a positive integer
- `$ORG` and `$REPO` must match `^[a-zA-Z0-9_.-]+$`

Bail on any validation failure with a clear error message.

### Fetch PR Metadata

```bash
gh pr view $PR_NUMBER --repo $ORG/$REPO \
  --json headRefName,baseRefName,title,state,body,reviewDecision
```

Store `headRefName` as `$HEAD_BRANCH`, `baseRefName` as `$BASE_BRANCH`.

- **Closed** -> exit: "PR #$PR_NUMBER is already closed."
- **Merged** -> exit: "PR #$PR_NUMBER is already merged."
- **404** -> exit: "PR #$PR_NUMBER not found in $ORG/$REPO."

---

## PHASE 2: Pre-Merge Verification

Four checks, all must pass. Run in sequence.

### Step 2a: Unresolved Review Threads

Query for unresolved review threads:

```bash
gh api graphql -f query='
{
  repository(owner: "'$ORG'", name: "'$REPO'") {
    pullRequest(number: '$PR_NUMBER') {
      reviewThreads(first: 50) {
        nodes {
          isResolved
          path
          line
          comments(first: 1) {
            nodes {
              body
              author { login }
            }
          }
        }
      }
    }
  }
}'
```

Filter to threads where `isResolved` is `false`. If any exist, report each with file, line,
author, and first comment body, then bail:

```
Cannot merge — N unresolved review thread(s):

  path/to/file.go:42 (@reviewer): "Summary of comment..."

Resolve these threads before landing.
```

### Step 2b: Approval Check

Check `reviewDecision` from Phase 1 metadata:

- `APPROVED` -> continue
- `CHANGES_REQUESTED` -> bail: "Cannot merge — changes requested."
- `REVIEW_REQUIRED` -> bail: "Cannot merge — no approving review."
- Empty/null -> bail: "Cannot merge — review status unclear."

### Step 2c: CI Checks

```bash
gh pr checks $PR_NUMBER --repo $ORG/$REPO
```

All checks must show `pass`. If any are `pending` or `in_progress`, poll with exponential
backoff: 10s -> 20s -> 40s -> 80s -> 120s (cap). Maximum total wait: 10 minutes.

If any check fails after polling completes, report the failing check names and bail.

### Step 2d: Branch Freshness

Check whether the PR branch is behind the base branch.

**If in a local checkout of the PR branch:**

```bash
git fetch origin $BASE_BRANCH
BEHIND_COUNT=$(git rev-list --count HEAD..origin/$BASE_BRANCH)
```

If behind:
1. Attempt `git merge origin/$BASE_BRANCH --no-edit`
2. If clean merge -> push and re-poll CI (back to Step 2c)
3. If conflict -> bail with conflicted file list

**If not in a local checkout of the PR branch:**

```bash
gh api repos/$ORG/$REPO/compare/$BASE_BRANCH...$HEAD_BRANCH --jq '.behind_by'
```

If behind -> bail: "Cannot merge — branch is $N commit(s) behind $BASE_BRANCH."

---

## PHASE 3: Squash Merge

Use the API method — `gh pr merge` fails with worktrees (see LEARNINGS.md protocol).

**IMPORTANT**: Use `-X PUT`, not POST. POST returns 404 on this endpoint.

### Step 3.1: Prepare Commit Message

Extract the PR body and strip the closing keyword line:

```bash
PR_BODY=$(gh pr view $PR_NUMBER --repo $ORG/$REPO --json body --jq .body)
PR_TITLE=$(gh pr view $PR_NUMBER --repo $ORG/$REPO --json title --jq .title)

# Extract closing keyword line for appending at the end
CLOSING_LINE=$(echo "$PR_BODY" | grep -iE '^\s*(Fixes|Closes|Resolves)\s+#[0-9]+' | head -1)

# Strip closing keyword from body for commit message
COMMIT_BODY=$(echo "$PR_BODY" | grep -viE '^\s*(Fixes|Closes|Resolves)\s+#[0-9]+' | sed '/^$/N;/^\n$/d')
```

### Step 3.2: Merge

```bash
gh api repos/$ORG/$REPO/pulls/$PR_NUMBER/merge \
  -X PUT \
  -f merge_method=squash \
  -f commit_title="$PR_TITLE (#$PR_NUMBER)" \
  -f commit_message="$(cat <<EOF
$COMMIT_BODY

$CLOSING_LINE
EOF
)"
```

On merge failure -> log the error, bail, leave PR open, skip to Phase 5 (cleanup).

Store the merge commit SHA from the response: `jq -r '.sha'`

---

## PHASE 4: Linked Issue Lifecycle

### Step 4a: Extract Linked Issue

Parse `$PR_BODY` for `Fixes #N`, `Closes #N`, or `Resolves #N`. Extract `$ISSUE_NUMBER`.
Also check for Jira ticket references (e.g., `ENG-1234`).

If not found -> skip Phase 4 entirely, note "No linked issue" in summary.

### Step 4b: Verify GitHub Issue Closed (if applicable)

```bash
gh issue view $ISSUE_NUMBER --repo $ORG/$REPO --json state --jq .state
```

GitHub should auto-close via the `Fixes` keyword on merge. If still `OPEN`, close manually:

```bash
gh issue close $ISSUE_NUMBER --repo $ORG/$REPO
```

If the reference is a Jira key rather than a GitHub issue number, note it in the summary
but do not attempt to transition the Jira ticket automatically.

---

## PHASE 5: Local Cleanup

### Step 5a: Detect Local Context

Determine whether a local worktree exists for the PR branch.

1. Check if the current directory is a git worktree whose branch matches `$HEAD_BRANCH`:
   ```bash
   CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
   ```
   If `$CURRENT_BRANCH` equals `$HEAD_BRANCH` -> this is the worktree to remove.

2. If not, search sibling worktrees for a matching branch:
   ```bash
   git worktree list --porcelain | grep -B2 "branch refs/heads/$HEAD_BRANCH" \
     | grep "^worktree " | sed 's/^worktree //'
   ```

3. Identify the trunk directory (primary checkout, not a worktree) via `git worktree list`.

If no local worktree found -> skip local cleanup, note in summary.

### Step 5b: Remove Worktree

```bash
cd $TRUNK_DIR
git worktree remove $WORKTREE_PATH --force
git worktree prune
```

### Step 5c: Delete Local Topic Branch

```bash
git branch -d $HEAD_BRANCH 2>/dev/null || git branch -D $HEAD_BRANCH
```

### Step 5d: Fast-Forward Trunk

```bash
DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null \
  | sed 's|refs/remotes/origin/||')
if [ -z "$DEFAULT_BRANCH" ]; then
  DEFAULT_BRANCH=$(gh repo view $ORG/$REPO --json defaultBranchRef --jq '.defaultBranchRef.name')
fi

git checkout $DEFAULT_BRANCH
git pull --ff-only
```

---

## PHASE 6: Summary

Print a structured summary. Omit lines that don't apply.

```
Finished PR #42 — <PR title>

PR:        $ORG/$REPO#$PR_NUMBER — merged ($MERGE_SHA_SHORT)
Issue:     #$ISSUE_NUMBER — closed | ENG-1234 — noted
Branch:    $HEAD_BRANCH (local: deleted, remote: deleted)
Worktree:  $WORKTREE_DIR (removed)
Trunk:     $DEFAULT_BRANCH (fast-forwarded to $MERGE_SHA_SHORT)
```

Variations:
- No linked issue: omit Issue line
- No local worktree: omit Worktree line, Branch shows `(no local checkout)`
- Merge failed: `PR: $ORG/$REPO#$PR_NUMBER — merge failed (left open)`
- Trunk not updated: `Trunk: $DEFAULT_BRANCH (unchanged)`

---

## Error Handling

All error handling is autonomous. Never prompt for user input.

| Error | Recovery |
|-------|----------|
| Cannot parse arguments | Exit with usage message |
| PR not found | Exit with error |
| PR already merged/closed | Exit with status |
| Unresolved review threads | List them, exit |
| No approval / changes requested | Report, exit |
| CI check failures | Report failing checks, exit |
| CI checks pending > 10 min | Report, exit |
| Branch behind + merge conflict | Report conflicted files, exit |
| Merge API failure | Report error, skip to cleanup |
| No local worktree found | Skip cleanup, note in summary |
| Worktree removal fails | Log warning, continue |
| Fast-forward fails | Log warning, continue |
| API rate limit | Wait 60s, retry once |
| Network failure | Retry 3x with 30s backoff, then exit |

---

## Critical Conventions

- **No user interaction.** This skill is fully autonomous start to finish.
- **Squash merge only**, via API with `-X PUT`.
- **Closing keywords** preserved at the end of the commit message so GitHub auto-closes issues.
- Follow the global `~/.claude/CLAUDE.md` conventions.
- Follow any project-level CLAUDE.md conventions when they exist.
