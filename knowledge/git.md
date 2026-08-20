# Git Operations & Conventions

## Git branch-membership & version-name verification

- **`git branch -a --contains <sha>` under the RTK hook returns a collapsed summary** (`remote-only (1): <branch>`) that HIDES most containing branches — reading it as ground truth produces "commit is on no release branch" false negatives. Fix: test membership explicitly per branch with `git merge-base --is-ancestor <sha> <branch>` in a loop. Same trap for `git ls-tree`/`git cat-file -e` path existence checks: `git cat-file -e "$B:path"` returned "absent" on branches where `git ls-tree -r --name-only "$B" | grep <basename>` correctly returned 1. Prefer `git ls-tree -r --name-only`. Confirmed 2026-07 during ENG-1133971 verification.
- **The same PR can exist as several distinct SHAs** (fork copies, re-pushes, cherry-picks) with identical subject lines. Pickaxing by `--grep=<TICKET>` across `--all` returns them all; only one is an ancestor of the release branches. Never cite a sha from `git log --all --grep` without an `--is-ancestor` check against `origin/develop` and the target release branch, then corroborate with `git blame` on the actual defective lines. ENG-1133971: three copies of `ENG-276787 (#7122)`; only `db93f6d240` ships (Release107+); `716fa34e29` lives on a stale feature branch only.
- **Netskope ENG Jira has NO `Release<N>` version names** — the convention is bare `<N>.0.0` (e.g. `107.0.0` id 37324, `140.0.0` id 56002). `Release<N>` is a *git branch* name only (`origin/Release107`). Passing `Release107` to a version lookup finds nothing. Translate branch name → version name before resolving ids. The ~471 `release-*` entries in ENG are unrelated legacy semver tags.
- **ENG `customfield_11701` (Root Cause Analysis) and `customfield_12500` (Fix Description) are both `customfieldtypes:textarea`** with `operations: ['set']`. Despite the `"type": "string"` schema, both require ADF (`{"type":"doc","version":1,...}`) — a plain string returns 400 `"Operation value must be an Atlassian Document"`.

## Git show redirect / RTK hook

- **`git show <branch>:<file> > /tmp/out` can silently produce a 0-byte file** under the RTK shell hook (the rewrite mangles the redirect target). Symptom: `wc -l /tmp/out` shows 0 while the same `git show` piped works. Fix: use process substitution for cross-branch file compares — `diff <(git show origin/A:path) <(git show origin/B:path)` — instead of writing temp files. Confirmed 2026-07 during ENG-1127021 triage.
- **`git show "$B:$P"` inside a bash `for` loop gets its revspec CORRUPTED by the RTK hook** when `$B`/`$P` are shell variables. Symptom: `fatal: ambiguous argument 'origin/Release138k/application/models/Foo.php'` — the hook's rewrite ate a chunk of the path mid-string (`src/webui/system_framewor` vanished, leaving a stray `k`). The bare-`$B`-interpolated form `git show $B:src/...` fails the same way. Fix: prefix the whole thing with `rtk proxy` — `n=$(rtk proxy git show "$B:$P" | grep -c pattern)` — which bypasses the rewrite and returns correct counts. Also note `git log --reverse -S '<literal>' -- <path>` returns EMPTY under the hook but works under `rtk proxy`; a silent-empty pickaxe reads as "never introduced" and will fabricate a wrong origin trace. Always `rtk proxy` pickaxe and cross-branch `git show`. Confirmed 2026-07 during ENG-1133971 triage.

## Branch & Commit Conventions

- **mf-client + webui branches**: `pr/ENG-XXXXXX/kebab-slug`. CI rejects the global `<user>/<ticket>-<slug>` default. See `https://nsgo.to/branchingstrategy`.
- **mf-client + webui commits**: `ENG-XXXXXX: Subject` (project-key prefix with colon). NOT Conventional Commits. Allowed prefixes per `commitlint.config.js`: `ENG`, `NG`, `EP`.
- **mf-client default branch is `master`** — `git fetch origin main` fails. Verify with `git remote show origin`.
- **mf-client push target**: always `origin` (`netSkope/mf-client`), NOT a personal fork. CODEOWNERS / shared CI assume upstream-branch PRs.
- **Check Jira fixVersion for base branch**: a fix targeting `release/202605.2` must be based on that release branch, not `master`. Wrong base pollutes the PR diff and forces a reset+cherry-pick.
- **webui in-flight fixVersion → `develop`**: a `Release<N>` branch is only cut at code-freeze. Before that, basing on `develop` is correct; track the SHA for later cherry-pick.
- **mf-client staging PR pattern**: when fix targets `release/YYYYMM.N`, also cherry-pick onto `origin/staging` and open a separate PR named `pr/ENG-XXXXXX/<slug>-staging` for QA validation on qa01.
- **mf-client is a separate git repo** inside `netskope-ng-base/frontends/mf-client`. Always `cd` in and `git remote -v` before running git/gh commands. Release branches exist on the mf-client remote, not the parent.
- **Investigate on the deployed branch**, not the primary checkout. For env-specific bugs, confirm which branch is deployed (e.g. mf-client `staging` → qa01) and analyze code via `git show <branch>:<file>`.
