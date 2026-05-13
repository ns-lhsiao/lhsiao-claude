---
name: restack-pr
description: >-
  Recover a stale or stuck PR by cherry-picking its commits onto a fresh base
  branch and opening a replacement PR. Use when a PR is too far behind, has a
  bad rebase history, was created against the wrong head repo (fork vs.
  upstream), or otherwise can't be salvaged with a simple force-push. Triggers
  on "/restack-pr", "redo this PR", "recreate the PR", "cherry-pick onto
  master", "PR is stale", or any situation that calls for closing the existing
  PR and opening a fresh one.
argument-hint: "<old-pr-number> [target-base-branch]"
allowed-tools: Bash(git:*), Bash(gh:*), Read, AskUserQuestion
user-invocable: true
---

# Restack PR

**Emit "Skill activated: restack-pr"**

## Why this exists

Some PRs can't be saved with `git rebase` or `git push --force-with-lease`:
- The PR's head branch is on the wrong remote (fork vs. upstream).
- The branch has accumulated unrelated commits from a botched rebase.
- The base branch has moved enough that conflict resolution would pollute the
  diff.
- A squash-merge already happened on a different PR and we now need to redo
  the rest cleanly.

The recovery is mechanical but easy to get wrong (see LEARNINGS for the
"#933 → #1126" episode). This skill codifies it.

## Inputs

- `<old-pr-number>` — the PR to retire
- `[target-base-branch]` — defaults to the old PR's base, or to the repo's
  default branch if the base has been deleted/renamed

If either is unclear, ask via `AskUserQuestion` once. Don't guess.

## Procedure

### 1. Inspect the old PR

```bash
gh pr view <old> --json number,title,state,baseRefName,headRefName,headRepositoryOwner,url,body
```

Capture:
- Title, body, base branch, head branch
- Head repo owner (compare with `git remote get-url origin`'s host org)
- State (skip if already MERGED — see LEARNINGS: pushing to a merged PR's
  branch lands orphan commits)

If the PR's head repo owner does NOT match the upstream (e.g. head is on a
fork like `ns-lhsiao` while the team workflow expects `netSkope`), call that
out and confirm the user wants the new PR opened on the correct remote.

### 2. Identify commits to bring forward

```bash
git fetch origin <old-base-branch>
git log --oneline origin/<old-base-branch>..origin/<old-head-branch>
```

If commits include merge commits or unrelated noise, ask the user which SHAs
to cherry-pick rather than picking the whole range. The new PR's diff should
match the *intent* of the old PR, not its messy history.

### 3. Create a fresh branch off the target base

Branch naming follows the project's convention:
- `mf-client` and `webui` — `pr/ENG-XXXXXX/<slug>`
- Default — `<gh-username>/<ticket>-<slug>`

Pick a slug that's distinct from the old branch (e.g. add `-v2` or
`-restack`) so the two don't collide locally:

```bash
git fetch origin <target-base>
git checkout -b <new-branch> origin/<target-base>
```

Worktree convention (per CLAUDE.md): if the user is in a worktree for the old
branch, create a sibling worktree for the new branch in the parent dir, named
`<repo>-<slug>`.

### 4. Cherry-pick

```bash
git cherry-pick <sha1> [<sha2> ...]
```

Resolve conflicts. Keep going until the branch contains the same logical
change as the old PR.

### 5. Push to the correct remote

For repos with a strict upstream-only convention (mf-client, webui), push to
`origin` (upstream), NOT to a fork remote. Verify with
`git remote -v` first — note the LEARNINGS quirk where a transferred fork's
origin URL still shows the old org but pushes land on upstream.

```bash
git push -u origin <new-branch>
```

### 6. Open the replacement PR

Reuse the old PR's title (perhaps with a `(restack)` suffix) and body. Append
a one-line cross-link in the body:

```
Replaces #<old-pr-number>.
```

Use the project's PR template (see LEARNINGS: webui uses H4 headings,
mf-client uses H2 with emoji prefixes — read
`.github/pull_request_template.md` and mirror it exactly).

```bash
gh pr create --base <target-base> --head <new-branch> \
  --title "<title>" --body "$(cat body.md)"
```

### 7. Close the old PR

```bash
gh pr close <old> --comment "Superseded by #<new>. Restacked onto <target-base>."
```

If the old PR's branch is on a fork, also delete it from the fork to prevent
future confusion:

```bash
gh api -X DELETE repos/<fork-owner>/<repo>/git/refs/heads/<old-head-branch> 2>/dev/null || true
```

### 8. Verify

```bash
gh pr view <new> --json url,baseRefName,headRefName,headRepositoryOwner
git log --oneline <target-base>..HEAD
```

Confirm the diff matches the old PR's intent and the head repo is the
expected upstream org.

## Don't

- Don't `git reset --hard` or force-push to the old branch — close it cleanly
  via `gh pr close` instead. (Force-push to a merged PR's branch lands orphan
  commits — see LEARNINGS.)
- Don't reuse the same branch name on a different remote — open the new PR on
  a fresh branch name. Once a PR is opened with its head on one repo, you
  can't retarget it to a branch on a different repo.
- Don't skip commit-message rewrites — if the old commits used `fix:` style
  but the project requires `ENG-XXXXXX:` (mf-client, webui commitlint), use
  `git cherry-pick --edit` or amend after.
- Don't bundle in unrelated commits while restacking. The new PR should be
  the same change, not change+cleanup.
