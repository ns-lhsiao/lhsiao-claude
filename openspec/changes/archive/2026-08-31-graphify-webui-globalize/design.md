## Context

This is a relocation + correction of an already-shipped change (`webui-graphify-agents`,
20/20 tasks complete, never archived, originally landed in `webui/openspec/changes/`).
Grounding facts carried over from that change:

- `webui-angular-agent` and `webui-php-agent` each query a persistent `graphify`
  knowledge graph over an absolute `--graph <path>` (Decision 3 of the original
  design) — one graph per domain, in a dedicated build-only worktree
  (`webui-dev-graphify` for Angular, `webui-php-graphify` for PHP), refreshed weekly
  via `launchd` (`~/.claude/scripts/graphify-webui-maintain.sh`, already committed
  and running).
- The `/graphify-webui` skill dispatches both agents unconditionally in parallel and
  synthesizes prose answers, dropping whichever domain reports nothing relevant.
- All three definition files (`webui-angular-agent.md`, `webui-php-agent.md`,
  `graphify-webui/SKILL.md`) currently live in `webui/.claude/`, per the original
  Decision 9: "Agent/skill definition files live in the primary `webui` checkout's
  `.claude/`... need to be discoverable from whatever session invokes them, which is
  the primary checkout in the common case."
- That premise is now known to be wrong for the actual usage pattern: `/boot-bugfix`
  (global) tells any session investigating a bug touching `src/webui/...` to run
  `/graphify-webui` first — regardless of which repo that session's cwd happens to
  be in. A session in, say, `nplan6460` investigating a webui-adjacent bug cannot
  resolve `/graphify-webui` or its two agents at all, because Claude Code's
  skill/agent registry is scoped to cwd's project `.claude/` plus `~/.claude/`, not
  to "whatever repo the bug happens to be about."
- The original change's own text already flagged this as mis-scoped conceptually
  ("that's Claude Code configuration, not webui architecture context" — its own
  `openspec/config.yaml > context` note), even though it didn't yet know about the
  cross-repo invocation failure.

Stakeholder: single user (Louis), personal dev-tooling productivity — unchanged from
the original change.

## Goals / Non-Goals

**Goals:**
- `/graphify-webui` and its two domain agents resolve and dispatch correctly from
  any session, regardless of cwd/repo.
- The OpenSpec record for this capability lives where the capability actually lives
  (`~/.claude`), so future archival produces capability specs in the right place.
- Worktrees hosting the graph builds are self-documenting — `git worktree list`
  turning one up shouldn't require reverse-engineering its purpose from this change
  history.
- The previously untracked `/graphify-webui`-first instruction in `boot-bugfix`
  becomes a tracked, verifiable acceptance criterion instead of an informal aside.

**Non-Goals:**
- No change to query/maintenance mechanics: graph corpora, `graphify` subcommand
  selection, federated (not merged) domain-agent design, weekly `launchd` cadence,
  and dirty-tree abort policy are all unchanged from the original design — this
  change only relocates definition files and their documentation.
- No new cross-language graph edges (still federated, still a known limitation).
- No change to `webui-dev-graphify` / `webui-php-graphify` worktree contents beyond
  adding one `GRAPHIFY.md` file each — they remain build-only graph storage.

## Decisions

1. **Full relocation to `~/.claude/{agents,skills}/`, not a symlink or dual copy.**
   A symlink from `webui/.claude/agents/webui-angular-agent.md` back to the global
   file was considered, to preserve "looks discoverable from webui too" without
   duplicating content. Rejected: Claude Code's project-scope skill/agent discovery
   is unlikely to follow symlinks outside the repo tree reliably across platforms/
   sync tools, and a dual copy (kept in sync manually) reintroduces the exact
   staleness risk this change exists to eliminate. A single global copy, with no
   trace of the concept remaining in `webui/.claude/`, is the simplest correct state.

2. **Superseding Decision 9's premise.** Original: "discoverable from the primary
   checkout in the common case." New: "discoverable from any cwd" is the actual
   requirement — the original design didn't anticipate `/boot-bugfix`-style
   cross-repo dispatch because that skill didn't exist yet when
   `webui-graphify-agents` was designed. This isn't a reversal of a decision that
   was wrong at the time; it's a genuinely new requirement (a global consumer
   skill) invalidating an old scoping choice made before that consumer existed.

3. **OpenSpec artifacts migrate wholesale, with targeted edits, not a fresh rewrite.**
   The original `proposal.md`/`design.md`/`tasks.md`/`specs/` already encode
   real decisions (federated design, absolute graph paths, `launchd` over
   `CronCreate`, etc.) that remain correct and shouldn't be re-derived. This
   change's own artifacts reference and update only the parts that changed
   (file paths, Decision 9's premise, the boot-bugfix acceptance criterion);
   everything else carries forward by reference to the original change's history
   rather than being duplicated verbatim.

4. **Per-worktree `GRAPHIFY.md`, not a single doc referencing both, and not
   `CLAUDE.md`.** Each of `webui-dev-graphify` and `webui-php-graphify` gets its
   own short `GRAPHIFY.md` (not a shared doc one has to find via the other)
   because a worktree is typically discovered in isolation — someone runs
   `git worktree list` and needs the answer right there in that worktree's root,
   without needing to already know the other worktree exists. Discovered during
   implementation: these worktrees are checkouts of the `webui` repo, so each
   already has `webui`'s own tracked, repo-wide `CLAUDE.md` (275 lines of PHP/
   Angular conventions loaded into every session) — writing the worktree-purpose
   note into `CLAUDE.md` would silently clobber that shared file. A distinct
   filename avoids the collision entirely rather than relying on care not to
   overwrite it.

5. **The boot-bugfix reference is corrected to match reality, not the original
   proposal's stated target.** The original proposal said the out-of-band edit
   would land in top-level `~/.claude/CLAUDE.md`; it actually landed in
   `~/.claude/skills/boot-bugfix/SKILL.md:52-57` (already committed, already
   working). `tasks.md`'s acceptance criterion is written against the actual
   location, not the originally-stated one — rewriting history to match a proposal
   that was never executed as written would be worse than acknowledging the drift.

## Risks / Trade-offs

- **[Risk]** Claude Code's skill/agent registry may not hot-reload definition files
  moved into `~/.claude/` mid-session (the original change hit exactly this with new
  files added to `webui/.claude/agents/` — tasks.md 3.3/4.2 both needed a session
  reload to verify live `Agent()` dispatch). → **Mitigation**: same as before —
  verify the underlying mechanics directly first (`graphify query` by hand), then
  confirm live dispatch after a fresh session reload; don't block on same-session
  verification.
- **[Risk]** Deleting `webui/.claude/agents/*.md` and `webui/.claude/skills/graphify-webui/`
  outright (Decision 1) means any in-flight session that had them loaded from the
  old location loses them until it reloads — acceptable for a single-user personal
  tool, not acceptable if this were multi-user shared tooling. → **Mitigation**:
  none needed given the single-user context; noted for completeness.
- **[Risk]** `webui/openspec/changes/webui-graphify-agents/` being deleted rather
  than archived means `openspec archive` in the `webui` repo will never see it —
  if anyone later expects `webui/openspec/specs/` to contain a record of this
  work, they won't find one there. → **Mitigation**: intentional — the capability
  never belonged in webui's spec tree; the `GRAPHIFY.md` files left in the two graph
  worktrees (Decision 4) are the pointer for anyone who stumbles onto the worktrees
  from the webui side and wants the full history, directing them to
  `~/.claude/openspec/` (post-archive, `~/.claude/openspec/specs/`).
- **[Risk]** tasks.md 6.2's unresolved verification (agent must surface `graphify`
  failure, not fabricate) still hasn't been exercised live, and now the agent files
  are moving again, adding another reason it could have silently regressed.
  → **Mitigation**: re-run it explicitly as part of this change's own tasks.md,
  not deferred again.

## Migration Plan

1. In `webui` repo: create `GRAPHIFY.md` in `webui-dev-graphify` and
   `webui-php-graphify` worktrees documenting their purpose and pointing at this
   change's new home.
2. In `webui` repo: remove `.claude/agents/webui-angular-agent.md`,
   `.claude/agents/webui-php-agent.md`, `.claude/skills/graphify-webui/` and
   `openspec/changes/webui-graphify-agents/`.
3. In `~/.claude`: add `agents/webui-angular-agent.md`, `agents/webui-php-agent.md`,
   `skills/graphify-webui/SKILL.md` — content unchanged except any cwd-dependent
   assumptions (there are none; graph paths were already absolute).
4. In `~/.claude/skills/boot-bugfix/SKILL.md`: confirm the existing
   `/graphify-webui` reference (already committed) matches the new global agent
   names/paths — no textual change expected, just verification.
5. Reload session; verify live `Agent()` dispatch to both relocated agents from a
   cwd outside `webui` (the actual scenario this change exists to fix).
6. Re-run the tasks.md 6.2 failure-surfacing check against the relocated PHP agent.

**Rollback**: recreate the three files in `webui/.claude/` from this change's
history, delete the `~/.claude/{agents,skills}` copies, remove the two worktree
`GRAPHIFY.md` files. No graph data, worktree, or scheduling job is touched by
rollback — purely definition-file and doc relocation.

## Open Questions

(none outstanding — the original change's one open question, scheduling mechanism,
was resolved in favor of `launchd` and is unaffected by this relocation)
