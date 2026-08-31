## ADDED Requirements

### Requirement: Weekly per-worktree refresh job
Each domain graph's dedicated worktree (`webui-dev-graphify` for Angular,
`webui-php-graphify` for PHP) SHALL have a weekly scheduled job, implemented via
macOS `launchd`, that keeps its `graph.json` bounded-fresh (≤7 days stale) without
adding latency to query time.

#### Scenario: Scheduled run on a clean, up-to-date worktree
- **WHEN** the weekly job fires against a worktree that is clean and already
  current with `origin/develop`
- **THEN** the rebase is a no-op, the graph rebuild completes via content-hash
  caching with minimal reprocessing, and the job exits successfully

### Requirement: Dirty-tree abort, never auto-stash
The maintenance job SHALL check for a dirty working tree before doing anything
else, and SHALL abort and log without modifying the tree if dirty — it MUST NOT
auto-stash, force-push, or otherwise proceed past a dirty tree.

#### Scenario: Worktree has uncommitted changes
- **WHEN** the weekly job runs against a worktree with any uncommitted change
  (tracked or untracked)
- **THEN** the job aborts immediately, logs the abort, and leaves the tree exactly
  as it found it — no stash, no commit, no force-push

### Requirement: Rebase-then-rebuild sequence
On a clean tree, the maintenance job SHALL run `git fetch && git rebase
origin/develop`, and SHALL abort the rebase and alert (without leaving the tree in
a conflicted state) if the rebase does not complete cleanly. On successful rebase,
it SHALL rebuild the graph via a full `graphify <corpus-path> --code-only --out .
--no-cluster` run from the worktree root — not `graphify update`, which resolves
its output relative to the corpus path rather than the worktree root and would
reintroduce duplicate `graphify-out/` directories.

#### Scenario: Rebase hits a conflict
- **WHEN** `git rebase origin/develop` cannot complete cleanly
- **THEN** the job aborts the rebase, alerts, and does not attempt the graph
  rebuild step

### Requirement: Worktree self-documentation
Each domain graph's worktree SHALL contain a `GRAPHIFY.md` at its root — not
`CLAUDE.md`, which is already the webui repo's own shared, repo-wide
instructions file and would be silently clobbered by reuse — explaining that
the worktree is build-only graph storage for this tooling (not for manual edits
or commits), how its graph is consumed (absolute `--graph` path from the global
domain agent), how it is maintained (the weekly `launchd` job and the script
that runs it), and where to find the full capability record
(`~/.claude/openspec/`).

#### Scenario: Someone finds the worktree via `git worktree list`
- **WHEN** a user or a future session runs `git worktree list` against the `webui`
  repo and notices `webui-dev-graphify` or `webui-php-graphify`
- **THEN** reading that worktree's `GRAPHIFY.md` explains its purpose and points to
  where the rest of the design/history is recorded, without needing to already
  know this change existed
