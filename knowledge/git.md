# Git Operations & Conventions

## Git branch-membership & version-name verification

- **`git branch -a --contains <sha>` under the RTK hook returns a collapsed summary** (`remote-only (1): <branch>`) that HIDES most containing branches — reading it as ground truth produces "commit is on no release branch" false negatives. Fix: test membership explicitly per branch with `git merge-base --is-ancestor <sha> <branch>` in a loop. Same trap for `git ls-tree`/`git cat-file -e` path existence checks: `git cat-file -e "$B:path"` returned "absent" on branches where `git ls-tree -r --name-only "$B" | grep <basename>` correctly returned 1. Prefer `git ls-tree -r --name-only`. Confirmed 2026-07 during ENG-1133971 verification.
- **The same PR can exist as several distinct SHAs** (fork copies, re-pushes, cherry-picks) with identical subject lines. Pickaxing by `--grep=<TICKET>` across `--all` returns them all; only one is an ancestor of the release branches. Never cite a sha from `git log --all --grep` without an `--is-ancestor` check against `origin/develop` and the target release branch, then corroborate with `git blame` on the actual defective lines. ENG-1133971: three copies of `ENG-276787 (#7122)`; only `db93f6d240` ships (Release107+); `716fa34e29` lives on a stale feature branch only.
- **Netskope ENG Jira has NO `Release<N>` version names** — the convention is bare `<N>.0.0` (e.g. `107.0.0` id 37324, `140.0.0` id 56002). `Release<N>` is a *git branch* name only (`origin/Release107`). Passing `Release107` to a version lookup finds nothing. Translate branch name → version name before resolving ids. The ~471 `release-*` entries in ENG are unrelated legacy semver tags.
- **ENG `customfield_11701` (Root Cause Analysis) and `customfield_12500` (Fix Description) are both `customfieldtypes:textarea`** with `operations: ['set']`. Despite the `"type": "string"` schema, both require ADF (`{"type":"doc","version":1,...}`) — a plain string returns 400 `"Operation value must be an Atlassian Document"`.

## Git show redirect / RTK hook

- **`git show <branch>:<file> > /tmp/out` can silently produce a 0-byte file** under the RTK shell hook (the rewrite mangles the redirect target). Symptom: `wc -l /tmp/out` shows 0 while the same `git show` piped works. Fix: use process substitution for cross-branch file compares — `diff <(git show origin/A:path) <(git show origin/B:path)` — instead of writing temp files. Confirmed 2026-07 during ENG-1127021 triage.
- **`git show "$B:$P"` inside a bash `for` loop gets its revspec CORRUPTED by the RTK hook** when `$B`/`$P` are shell variables. Symptom: `fatal: ambiguous argument 'origin/Release138k/application/models/Foo.php'` — the hook's rewrite ate a chunk of the path mid-string (`src/webui/system_framewor` vanished, leaving a stray `k`). The bare-`$B`-interpolated form `git show $B:src/...` fails the same way. Fix: prefix the whole thing with `rtk proxy` — `n=$(rtk proxy git show "$B:$P" | grep -c pattern)` — which bypasses the rewrite and returns correct counts. Also note `git log --reverse -S '<literal>' -- <path>` returns EMPTY under the hook but works under `rtk proxy`; a silent-empty pickaxe reads as "never introduced" and will fabricate a wrong origin trace. Always `rtk proxy` pickaxe and cross-branch `git show`. Confirmed 2026-07 during ENG-1133971 triage.

- **Root cause of the `$B:$P` corruption is zsh, not only RTK — and there is a pure-quoting fix.** `git show "$r:src/webui/neo/src/app/components/nav-bar/navbar-config.service.ts"` in a zsh `for` loop errored `fatal: ambiguous argument 'origin/Release141/navbar-config.service.ts'` — zsh read `:s/webui/neo/...` as the **`:s/old/new/` history-substitution modifier** and rewrote the revspec, deleting the middle of the path. Any `$var:` followed by `s`, `h`, `t`, `r`, `e`, `g`, `p`, `q`, `l`, `u`, `a`, `A`, `c`, `x` can trigger it — so *most* real paths (`:src/...`, `:helpers/...`, `:test/...`) are affected. Fix without RTK: split into two separately-quoted words — `git show "${r}":"${P}"`. Confirmed 2026-09-15 during ENG-1277032 triage; with `2>/dev/null` in the loop this presents as a silent `grep -c` of `0` on **every** branch including one you know is positive.
- **`git cat-file -p "$B:$P" | grep -c <pat>` inside a `for` loop silently returns `0` for every branch** — a *wrong answer*, not an error, so it reads as "symbol absent on all branches" and will fabricate an origin trace. Confirmed 2026-08-31 during ENG-1172829 triage: the loop reported `isCfwOsFamilyEnabled` absent on Release139/140/141 AND `origin/develop`, yet the identical `git cat-file -p "origin/Release141:<path>" | grep -c` run as its OWN standalone Bash call returned `1`. `git cat-file` is affected the same way `git show` is (see above). Fix: never loop cross-branch content reads — issue one Bash call per branch, or wrap in `rtk proxy`. Sanity-check any loop result against a branch you KNOW contains the symbol; if that control also returns 0, the loop is lying.
- **Plain `git diff HEAD -- <files>` under the RTK hook can silently return a summarized stub** (`<file> | N ++++++++++`, `1 file changed`, `--- Changes ---`, with the second file's stat line and the actual patch body missing) instead of the real unified diff — this is RTK's token-optimized rewrite, not an error, so a downstream `grep -c '^diff --git'` check reads `0` and looks like "nothing changed" when files clearly are modified. Symptom hit while building a local-PR-review context file (vanguard repo, TC-CLIENT-176) that needs the byte-identical diff a CI reviewer would see. Fix: `rtk proxy git diff HEAD -- <files>` to get the untouched patch. Same fix family as the `git show`/`git cat-file` RTK traps above — when a git command's output needs to be machine-parsed or fed verbatim to another consumer (not just eyeballed), default to `rtk proxy` rather than trusting the hook's summary.

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
- **`git add <one-file>` still commits whatever else is ALREADY staged in the index.** `git add` only adds; it never scopes the following `git commit` to just what you added. Stray pre-staged files from unrelated earlier work (a different session, a half-finished `git add -A`) ride along silently — `git commit -m "..."` after `git add web/scripts/foo.sh` committed 4 unrelated pre-staged files alongside it in `devbox-ui` (2026-08-28). Always check `git show --stat HEAD` (or `git status` before the add) — not just the diff of the file you intended — and if extras snuck in, `git reset --soft HEAD~1` + explicit `git reset HEAD -- <unwanted files>` before recommitting, rather than trusting a single `git add <file>` to have scoped it.

## zsh eats `$var:path` in `git cat-file -p $b:src/...` (2026-09-07)
- `for b in Release126 ...; do git cat-file -p origin/$b:src/webui/.../File.php; done` silently
  returned EMPTY for every branch, making a defect look "absent on all releases". Root cause is
  **zsh history/parameter modifiers**: `$b:s...` is parsed as the `:s` (substitute) modifier applied
  to `$b`, with the next char as the delimiter — the rev:path string is mangled before git sees it.
  `git show`, `git cat-file`, and `git grep` are all affected. `rtk proxy` does NOT fix it (same shell
  parsing) — don't blame rtk.
- Correct forms: brace the variable (`git cat-file -p "origin/${b}:src/..."`) or build the whole
  rev:path into one variable first (`p="origin/${b}:path"; git cat-file -p "$p"`).
- Tell: a single hand-typed literal invocation works, the loop version returns 0 hits/0 lines.

## Never `git pull origin master` on a worktree meant for a story-specific integration branch (2026-09-15)
- Ran `git pull --ff-only origin master` on a fresh mf-cfw worktree before confirming the epic's
  actual PR-target integration branch (`pr/ENG-1274461/nplan-6460-main`), just to "catch up" a
  stale worktree. `master` had ~11 unrelated commits (a whole DNS Security feature) not yet merged
  into that integration branch. Every subsequent commit/rebase on the branch carried those 11
  master-only commits along, so `gh pr diff <n> --name-only` showed 27 unrelated files even though
  `git diff --stat` scoped to my own paths looked clean — the PR was polluted from the base, not
  from my own commit.
- `git rev-list --left-range --count <base>...<branch>` reporting "ahead N" where N is much bigger
  than your own commit count is the tell — check `gh pr diff <n> --name-only` (what GitHub actually
  computes against the PR's base) rather than trusting local `git diff --stat` against a possibly
  stale local ref of the base.
- Fix once discovered: don't try to rebase/filter the polluted branch — `git checkout -b tmp
  origin/<real-integration-branch>` then `git cherry-pick <your-single-commit-sha>` onto the clean
  base, then `git branch -f <original-branch-name> tmp` + `push --force-with-lease`. Much safer
  than rebase --onto with a long unrelated commit range.
- Root fix: identify the actual PR-target branch (check project CLAUDE.md / ask) BEFORE ever
  running any `git pull`/`git fetch --merge` against `master`/`main` in a story worktree — only
  ever sync against the real integration branch once it's known.
- **Do not `git checkout <ref> -- .`** to "peek" at another branch's tree — it silently overwrites
  every file in the working tree (including uncommitted edits) with that ref's versions, no
  conflict/warning. Recoverable via `git checkout HEAD -- .` if nothing was committed yet, but it's
  a destructive footgun; use `git show <ref>:<path>` or a separate worktree to inspect instead.

## mf-client `master` history is release-squash granular — pickaxe + `--is-ancestor` both mislead (2026-09-14)
- `git log --reverse -S '<marker>' origin/master -- <path>` on **mf-client** returns commits titled
  `Release: 202510.3 (R131) (#655)` / `Release/202603.4 (#990)` — the squash of a whole release branch
  into master, NOT the per-ticket commit that introduced the code. Author/date are the release
  manager's, not the real author's. Do not report these as "the introducing commit"; report them as
  "first master-side appearance" and name the release.
- Worse, the standard first-shipping-release walk **silently returns nothing**:
  `git merge-base --is-ancestor <sha> origin/release/YYYYMM.N` is false for *every* branch, because
  the release branch is the **source** and master the **destination** — the master-side squash is not
  an ancestor of the release branch it came from. An empty walk here is a false negative, not
  evidence the code is unreleased.
- Correct method for mf-client: **content-probe each release branch** in version order and take the
  first hit —
  `for b in "${BRANCHES[@]}"; do git grep -c '<marker>' "$b" -- <path>; done`
  (pass the rev as its own arg with `--` before the path; avoids the zsh `$b:path` modifier trap above).
  Bracket the answer by confirming the immediately-preceding branch has 0 hits.
- **Two parallel release-branch naming schemes coexist** on mf-client, both needed:
  `release/YYYYMM.N` (monthly train, e.g. `release/202608.2`) and `release/<R>.MM.DD-N`
  (R-number cut, e.g. `release/140.08.24-0`, `release/141.09.01-0`). Build the ordered list from
  `git branch -r` with `sort -V` and include both. Map between them via the R-number in release
  squash subjects (`Release 133 (202512.2)`, `Release: 202510.3 (R131)`) and the `<R>.MM.DD` branch
  names: R131=202510, R133=202512, R135=202603, R140=202608.
- There is **no `develop`** on mf-client — only `master` plus release branches. Don't look for one.
