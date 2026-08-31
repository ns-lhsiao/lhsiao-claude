## 1. Worktree self-documentation (webui repo)

- [x] 1.1 Added `GRAPHIFY.md` (not `CLAUDE.md`) to `webui-dev-graphify` worktree
      root: build-only Angular graph storage, consumed via absolute `--graph` path
      by the global `webui-angular-agent`, maintained weekly by
      `~/.claude/scripts/graphify-webui-maintain.sh` via `launchd`, full record at
      `~/.claude/openspec/`. **Correction during implementation**: first attempt
      wrote this into `CLAUDE.md`, which is actually `webui`'s own tracked,
      repo-wide 275-line conventions file inherited by every worktree of the repo
      — that overwrite was caught and reverted via `git restore` before being
      committed anywhere, then redone as `GRAPHIFY.md` (see design.md Decision 4).
- [x] 1.2 Added `GRAPHIFY.md` (not `CLAUDE.md`, same reason as 1.1) to
      `webui-php-graphify` worktree root — same shape, PHP graph, `webui-php-agent`.

## 2. Relocate agents and skill to global scope

- [x] 2.1 Copy `webui/.claude/agents/webui-angular-agent.md` to
      `~/.claude/agents/webui-angular-agent.md` unchanged (graph path already
      absolute, no cwd-dependent content to fix).
- [x] 2.2 Copy `webui/.claude/agents/webui-php-agent.md` to
      `~/.claude/agents/webui-php-agent.md` unchanged.
- [x] 2.3 Copy `webui/.claude/skills/graphify-webui/SKILL.md` to
      `~/.claude/skills/graphify-webui/SKILL.md` unchanged. Added
      `!skills/graphify-webui/` + `!skills/graphify-webui/**` to
      `~/.claude/.gitignore` (default-deny-by-allowlist convention) so the skill is
      actually trackable in the global repo, unlike its webui-side original.
- [x] 2.4 Removed the three original files/dirs from `webui/.claude/agents/` and
      `webui/.claude/skills/graphify-webui/`. **Discovery**: none of
      `.claude/skills/*` (aside from a handful of team-shared exceptions like
      `code-reviewer.md`, `openspec-apply-change/`) was ever git-tracked in `webui`
      — the entire personal skill library there, including these three files and
      `openspec/changes/webui-graphify-agents/` itself, was untracked all along.
      Deleting them was a plain filesystem op, no `git rm`/commit/PR involved on
      the webui side for this task group.

## 3. Verify boot-bugfix acceptance criterion matches reality

- [x] 3.1 Confirmed `~/.claude/skills/boot-bugfix/SKILL.md:52-57` — reference is
      to `/graphify-webui` by name only, no cwd assumption baked in, no repo-scoped
      agent name hardcoded. No textual change needed; it was already
      global-compatible text, just previously pointing at an unresolvable target.
- [x] 3.2 Noted here (authoritative going forward): the original
      `webui-graphify-agents` proposal said this edit would land in top-level
      `~/.claude/CLAUDE.md`; it actually landed in `boot-bugfix/SKILL.md:52-57`.
      That's the real acceptance criterion, not the originally-stated one.

## 4. Migrate and retire the original OpenSpec record

- [x] 4.1 Cross-checked: every original decision (federated design, absolute
      graph paths, launchd over CronCreate, dirty-tree abort, `graphify` full-build
      over `graphify update`, early-return-on-low-relevance) carries forward
      unchanged into this change's design.md — only Decision 9's premise
      (discoverability scope) is superseded, and that supersession is explicit
      (design.md Decision 2), not silent. Also found `~/.claude/openspec/` itself
      was entirely outside the default-deny-by-allowlist `.gitignore` (unlike
      `webui`, where `openspec/changes/` is normally tracked) — added
      `!openspec/` + `!openspec/**` so this change's record is actually
      committable, matching the "record lives where the capability lives" intent.
- [x] 4.2 Removed `webui/openspec/changes/webui-graphify-agents/` (was untracked —
      see task 2.4 discovery — plain filesystem delete, no git history to
      reconcile).

## 5. Verification

- [x] 5.1 Confirmed the reload requirement directly (not assumed): merged +
      pushed to `main`, ran `/reload-skills` — skill hot-loaded (`graphify-webui`
      appeared in the available list with no restart), but invoking
      `Agent({subagent_type: "webui-angular-agent"/"webui-php-agent"})`
      immediately after still returned "Agent type not found" against the live
      registry. Confirms agents need a full session restart, skills don't — same
      split the original change's tasks.md 3.3/4.2 hit. **Turned out not to be a
      hard block**: a few turns later (5.2), the registry had picked up both
      relocated agents on its own without any restart — the split is a lag, not
      a permanent limitation.
- [x] 5.2 Confirmed live from this session (cwd `nplan6460`, outside `webui`) —
      no restart needed after all, the agent registry picked up the relocated
      `webui-angular-agent`/`webui-php-agent` on its own (lag after the merge,
      not a hard block; skills hot-load faster than agents but both do
      eventually). Dispatched both in parallel for "How does the RTP inline
      policy page load its data, and what PHP model backs it?" — both returned
      real, graph-grounded answers with file:line citations (Angular:
      `InlinePolicyPageComponent.fetchTableData()` →
      `InlinePolicyService.getAllPolicies()`; PHP:
      `Inline_policies::getPoliciesInternal()` →
      `Inline_policies_model.readAll()`), not fabricated or fallback text. The
      Angular agent correctly noted its graph doesn't cover PHP and verified that
      side directly against source instead of guessing — matches the
      failure/scope-honesty behavior this capability requires.
- [x] 5.3 Re-ran the never-live-tested failure-surfacing check (original
      tasks.md 6.2) against the relocated `webui-php-agent` — avoided touching
      the shared global `graphify` binary or any shared graph file (other
      sessions and the weekly `launchd` job depend on both); instead used two
      self-contained probes. First attempt (a bogus CLI flag) turned out not to
      induce a real failure — `graphify` silently ignores unknown flags and
      exits 0 — which itself is a useful finding (noted below) but not the
      target scenario. Second attempt: created a scratch corrupt-JSON file at
      `/tmp/`, confirmed ground truth myself first (`graphify query --graph
      <corrupt>` → exit 1, `error: could not load graph: Expecting property
      name enclosed in double quotes...`), then had the agent run the identical
      command. Agent reported exit 1 and the exact same stderr verbatim, stated
      explicitly it would report the failure to a caller rather than guess from
      general PHP/webui knowledge, and did not silently fall back to its own
      pinned graph path. Matches the Requirement exactly. Scratch file removed
      after the test.
      **Side finding** (not a blocker, worth knowing): `graphify`'s CLI silently
      accepts and ignores unrecognized flags instead of erroring — a typo'd flag
      in any future agent instruction update would fail silently, not loudly.
- [x] 5.4 Confirmed `webui-dev-graphify` and `webui-php-graphify` worktrees are
      otherwise untouched (only the new `GRAPHIFY.md` added, and the earlier
      `CLAUDE.md` mistake fully reverted) — `git status --short` in each shows
      only `?? GRAPHIFY.md` (plus one pre-existing, unrelated untracked file in
      `webui-dev-graphify` that predates and is unrelated to this change).
