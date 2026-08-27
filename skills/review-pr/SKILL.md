---
name: review-pr
description: >-
  Re-scans a GitHub PR's unresolved review comments (bot or human), evaluates each for
  validity (is the concern technically correct?) and relevance (does it still apply to
  the current head?), then takes the matching action: fix + reply + resolve, reply-only +
  resolve, or leave open and flag to the user. Triggers on "/review-pr", "re-scan PR
  comments", "check PR review comments", "address PR feedback", "resolve PR review
  threads".
argument-hint: "<pr# | repo#pr | org/repo#pr | pr-url>"
allowed-tools: Bash(gh:*), Bash(git:*), Read, Edit, Write, Grep, Glob
user-invocable: true
---

# Review PR

**Emit "Skill activated: review-pr"**

Re-scan a PR's unresolved review threads and dispose of each one on its actual merits —
not by rubber-stamping every bot comment, and not by silently resolving anything that
takes real judgment.

## Context

$ARGUMENTS

---

## PHASE 1: Argument Parsing

Parse `$ARGUMENTS` into `$ORG`, `$REPO`, `$PR_NUMBER` using the first matching form (same
rules as `finish-up`):

| Input Form | Example | Parsing |
|------------|---------|---------|
| URL | `https://github.com/netSkope/webui/pull/18694` | Regex extract org, repo, number |
| Fully qualified | `netSkope/webui#18694` | Split on `/` and `#` |
| Repo-scoped | `webui#18694` | Default `$ORG=netSkope` |
| Bare number | `18694` or `#18694` | Infer org/repo from local git remote |

Bare-number inference:
```bash
gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
```
If ambiguous, bail: "Cannot infer repository from current directory. Use `org/repo#N` or a full URL."

Fetch PR metadata:
```bash
gh pr view $PR_NUMBER --repo $ORG/$REPO --json headRefName,baseRefName,title,state,author,url
```
Store `headRefName` as `$HEAD_BRANCH`. Store `author.login` as `$PR_AUTHOR`.
Get the caller's identity: `gh api user --jq .login` → `$ME`.

- **Closed/Merged** → exit: report state, nothing to review.
- **404** → exit: "PR #$PR_NUMBER not found in $ORG/$REPO."

`$IS_OWN_PR = ($PR_AUTHOR == $ME)` — this gates the autonomy level in Phase 5.

---

## PHASE 2: Fetch Unresolved Threads

```bash
gh api graphql -f query='
{
  repository(owner: "'$ORG'", name: "'$REPO'") {
    pullRequest(number: '$PR_NUMBER') {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          path
          line
          comments(first: 20) {
            nodes {
              databaseId
              body
              createdAt
              author { login }
              path
              originalLine
            }
          }
        }
      }
    }
  }
}'
```

Filter to `isResolved: false`. If none, report "No unresolved review threads on #$PR_NUMBER." and stop.

For each unresolved thread, note:
- First comment (the actual concern) — author, body, path, line, `createdAt`.
- Any subsequent comments in the thread (replies already posted — by anyone, including a
  prior run of this skill). If the **last** comment in the thread is already a reply from
  `$ME` and no one has commented since, skip re-processing — it's just waiting on a
  manual resolve or a fresh reviewer response. Note it as "already replied, unresolved" in
  the final summary and move on.
- If the last comment is from the original reviewer *after* a reply from `$ME` (they
  pushed back or asked a follow-up), treat the thread as needing fresh evaluation against
  their latest comment, not the original one.

---

## PHASE 3: Get a Working Copy at PR Head

Check for an existing local worktree already on `$HEAD_BRANCH`:
```bash
git worktree list --porcelain | grep -B2 "branch refs/heads/$HEAD_BRANCH" | grep "^worktree " | sed 's/^worktree //'
```

- **Found** → `cd` into it, `git fetch origin $HEAD_BRANCH && git merge --ff-only origin/$HEAD_BRANCH` (or `reset --hard` only if the user confirms — prefer ff-only and bail to ask if it can't fast-forward).
- **Not found** → create one per `~/.claude/CLAUDE.md` convention, in the parent directory of the primary checkout: `git worktree add ../$REPO-review-pr$PR_NUMBER origin/$HEAD_BRANCH`.

All reads and any fixes happen inside this worktree — never in the primary checkout.
Re-grep target symbols inside the worktree before trusting any line numbers carried over
from GitHub's diff view; they can drift after rebases/merges.

Before assuming how to run this repo's tests/lint, check `~/.claude/LEARNINGS.md` and its
linked knowledge files for repo-specific quirks (vendor symlink traps, PHP version pins,
etc.) — don't rediscover them the hard way.

---

## PHASE 4: Evaluate Each Thread

For each unresolved thread (in order), work through:

**1. Validity** — is the concern technically correct *right now*, against the worktree's
current state at `$HEAD_BRANCH` tip? Read the flagged file at the flagged line (or its
current drifted location), trace the logic, and form an independent judgment. Don't defer
to the reviewer's framing — bots (Copilot, etc.) get things wrong too, and human
reviewers can be working from stale context.

**2. Relevance** — does it still apply?
- Check `git log --oneline <thread-created-at>..HEAD -- <path>` for commits touching the
  flagged file/lines after the comment's `createdAt`. If a later commit already changes
  the flagged logic, check whether it happens to resolve the concern (even if that wasn't
  its stated purpose).
- Check whether the concern falls inside an explicit **Non-Goal** or scope boundary in the
  PR's own `openspec/changes/<name>/design.md` or `proposal.md`, if one exists. A
  concern that's valid in isolation but explicitly out of scope is not something to fix
  here — but it does need a reply saying so.

**3. Classify** into one bucket:

| Bucket | Meaning | Signal |
|--------|---------|--------|
| **A. Already fixed** | Concern was valid; a later commit already addresses it | Later commit changes the exact flagged logic/lines in a way that resolves the concern |
| **B. Valid, fixable now** | Concern is real, still present, and the fix is small/mechanical | Typo, missing guard, missing test case, stale doc reference, off-by-one, wrong flag name — scoped to 1-2 files, no design decision required |
| **C. Not a concern** | Concern doesn't hold up, or is explicitly out of scope per the PR's stated Non-Goals | Misreads the code, describes a case that can't occur, or duplicates an already-answered thread |
| **D. Valid, needs a human call** | Concern is real but the fix requires a decision only the user can make | Touches production/tenant data, security-sensitive, spans a real design tradeoff, multi-file architectural change, or you're genuinely unsure |

When in doubt between B and D, choose D. A wrong auto-fix pushed to someone else's PR is
worse than a flagged item waiting for a human.

---

## PHASE 5: Act Per Bucket

### Bucket A — Already fixed
Reply on the thread citing the commit SHA that fixed it and a one-line explanation of
*why* it resolves the concern (not just "fixed"). Resolve the thread.

### Bucket B — Valid, fixable now
- If `$IS_OWN_PR` is false (this is someone else's PR): **do not push.** Downgrade to
  Bucket D — report the concrete fix you'd make, and let the user decide whether to push
  it themselves or authorize you to.
- If `$IS_OWN_PR` is true:
  1. Make the minimal fix in the worktree. Single-file mechanical fixes (typo, guard
     clause, doc reference) skip the `/opsx` gate per the trivial-fix carve-out in
     `~/.claude/CLAUDE.md`; anything touching real logic across multiple files should go
     through `/opsx:propose` first even mid-review — don't let "it's just a review reply"
     bypass the normal gate.
  2. Run the relevant tests/lint for the touched file(s). If they fail, iterate up to 3
     attempts; if still failing, stop, do not push, and report the failure — fall to
     Bucket D for that thread.
  3. Commit with a conventional-commit message referencing the ticket if one exists in
     the branch name/PR title.
  4. Push to `$HEAD_BRANCH` (the existing PR branch — never force-push here).
  5. Reply on the thread citing the new commit SHA and what changed. Resolve the thread.

### Bucket C — Not a concern
Reply explaining specifically why (cite the Non-Goal line, the code path that makes the
flagged case impossible, or the actual behavior). Be concrete — "not a concern" with no
reasoning is not a real reply. Resolve the thread.

### Bucket D — Needs a human call
Do **not** resolve. Do not push anything. Optionally post a reply acknowledging the point
is valid and that it's being tracked (only if it adds value — silence is fine too). Add it
to the escalation list for the final summary — this is what actually needs the user's
attention.

Resolve via GraphQL for A/B/C:
```bash
gh api graphql -f query='
mutation($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) { thread { id isResolved } }
}' -f id="$THREAD_ID"
```

Reply via REST (threads a reply under the original review comment):
```bash
gh api repos/$ORG/$REPO/pulls/$PR_NUMBER/comments/$COMMENT_ID/replies -f body="..."
```

---

## PHASE 6: Summary

Report per-thread outcome, most-actionable first:

```
Reviewed #$PR_NUMBER — $ORG/$REPO — N unresolved thread(s)

D — needs your call (N):
  path:line (@author): <one-line concern> — <why it needs you>

B — fixed (N):
  path:line (@author): <concern> — fixed in <sha>, replied, resolved

A — already fixed (N):
  path:line (@author): <concern> — superseded by <sha>, replied, resolved

C — not a concern (N):
  path:line (@author): <concern> — <why dismissed>, replied, resolved

Skipped (already replied, awaiting reviewer/resolve) (N):
  path:line (@author)
```

Omit empty buckets. If any Bucket D items exist, end with a direct question to the user
about how they want each one handled — do not guess.

---

## Guardrails

- **Never resolve a thread you didn't genuinely evaluate.** Re-scanning means re-reading
  the current code, not re-stating the bot's claim back as a reply.
- **Never push to a PR you don't own without explicit confirmation** (Bucket B on
  someone else's PR always downgrades to D).
- **Never resolve a security-flagged concern into silence.** If a comment raises a
  security issue (secrets, injection, auth bypass, etc.), it is always Bucket D at
  minimum, regardless of how the fix looks — flag it to the user explicitly, per the
  Sensitive Data policy in `~/.claude/CLAUDE.md`.
- **Never guess at data-remediation concerns.** If a comment is really about bad
  production/tenant data rather than code, that's D — not something this skill fixes.
- Follow the global `~/.claude/CLAUDE.md` git/worktree/commit conventions throughout.
