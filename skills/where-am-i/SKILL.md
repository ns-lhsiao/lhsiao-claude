---
name: where-am-i
description: >-
  Print a one-screen orientation snapshot for the current shell — repo, branch,
  base/upstream, worktree status, deployed branch (if known), and any open PR
  associated with the current branch. Use at the start of a session, after
  switching directories, or whenever you want to confirm "which branch are we
  on" before making changes. Triggers on "/where-am-i", "where am i", "what
  branch", "orient me".
argument-hint: ""
allowed-tools: Bash(*), Read
user-invocable: true
---

# Where Am I

**Emit "Skill activated: where-am-i"**

A short preflight that prints repo + branch + diff context so neither you nor
the user has to ask "which branch are you on" mid-task. Read-only — never
modifies state.

## Procedure

Run these in parallel (single Bash batch when possible) and assemble the report:

### 1. Repo identity

```bash
pwd
git rev-parse --show-toplevel 2>/dev/null
git rev-parse --is-inside-work-tree 2>/dev/null
git remote get-url origin 2>/dev/null
git rev-parse --abbrev-ref HEAD
```

If `pwd` differs from `git rev-parse --show-toplevel`, note the subdirectory.
If the toplevel sits inside another repo (nested git, e.g. mf-client inside
netskope-ng-base), call that out explicitly — the user has been bitten by this
before.

### 2. Branch context

```bash
git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null
git status --porcelain=v1 --branch
git log --oneline -5
```

Report:
- Current branch and tracking remote
- Ahead/behind counts vs. upstream
- Number of staged / unstaged / untracked files (counts only — not the full
  list unless small)

### 3. Worktree context

```bash
git worktree list
```

If the current path is a worktree (not the primary checkout), say so and name
the primary. Useful because the user follows a strict worktree-per-feature
convention.

### 4. Base branch + divergence

Determine the likely base. Try in order:
1. `git config branch.<current>.merge` (if upstream is set, it implies a base
   on origin)
2. PR base via `gh pr view --json baseRefName -q .baseRefName 2>/dev/null`
3. Fall back to `master` or `main` (whichever exists in `origin`)

Then:

```bash
git rev-list --left-right --count <base>...HEAD
```

Report ahead/behind vs. base.

### 5. Open PR (if any)

```bash
gh pr view --json number,title,state,baseRefName,headRefName,headRepositoryOwner,url 2>/dev/null
```

If a PR exists, print number, state, base, head repo (note if head repo owner
is not the expected upstream — the user has hit fork/upstream confusion before).

### 6. Deployed branch hint (best-effort)

If the repo is `mf-client`, mention:
- `staging` → qa01
- `release/YYYYMM.N` → prod (verify with team)

Skip if the current repo is unfamiliar; do not guess.

## Output format

Keep it tight — under 20 lines. Example:

```
Repo:      mf-client (netSkope/mf-client)
Path:      ~/ns/git/netskope-ng-base/frontends/mf-client-ENG-1007534
Worktree:  yes (primary at ~/ns/git/netskope-ng-base/frontends/mf-client)
Branch:    pr/ENG-1007534/fix-foo  →  origin/pr/ENG-1007534/fix-foo
Base:      release/202605.2  (ahead 3, behind 0)
Working:   2 staged, 1 unstaged, 0 untracked
PR:        #1199 OPEN  →  netSkope:release/202605.2  (head on netSkope)
Deploys:   staging→qa01;  release/*→prod
```

If anything looks off (detached HEAD, no upstream, head on a fork when the
team workflow expects upstream branches, etc.), flag it as a one-line warning
at the top.

## Don't

- Don't run `git fetch`, `git pull`, or any state-mutating command.
- Don't speculate about deployment for repos you don't recognize.
- Don't dump full file lists or full commit history — counts and the latest
  five commits are enough.
