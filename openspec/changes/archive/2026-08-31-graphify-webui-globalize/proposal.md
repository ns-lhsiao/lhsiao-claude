## Why

`webui/.claude/skills/graphify-webui/SKILL.md` and its two domain agents
(`webui-angular-agent`, `webui-php-agent`) currently live project-scoped inside the
`webui` repo checkout (shipped complete via `webui-graphify-agents`, 20/20 tasks,
never archived). That repo-scoping was a deliberate choice at the time (Decision 9:
"discoverable from the primary checkout in the common case") but the premise only
covered sessions already cd'd into `webui`. It breaks the moment a session in a
different repo needs graph-informed orientation on webui source — e.g. `/boot-bugfix`
(global, `~/.claude/skills/boot-bugfix/SKILL.md`) instructs any bug investigation
touching `src/webui/...` to run `/graphify-webui` first, but that skill and its two
agents are invisible outside a `webui` cwd, so the call silently fails to resolve.

Separately, the original change's own text already flags a mis-homing: "It does
introduce new `.claude/agents/` and `.claude/skills/` tooling, but that's Claude Code
configuration, not webui architecture context" (design.md, config.yaml section), and
"Stakeholder: single user (Louis), personal dev-tooling productivity — not a deployed
webui feature" (design.md Context). This tooling was never a webui capability; it was
personal Claude Code config that happened to be authored inside the webui repo.

## What Changes

- Move `webui-angular-agent` and `webui-php-agent` subagent definitions from
  `webui/.claude/agents/` to `~/.claude/agents/` (global scope).
- Move the `/graphify-webui` orchestrator skill from `webui/.claude/skills/` to
  `~/.claude/skills/` (global scope). Skill name unchanged — it's still specific to
  the webui domain, just globally invocable regardless of caller cwd.
- No changes to either agent's `graphify` invocation: both already pin an absolute
  `--graph <path>` (Decision 3 from the original design), so relocating the
  definition files doesn't touch query mechanics.
- Migrate this change's own OpenSpec artifacts (`proposal.md`, `design.md`,
  `tasks.md`, `specs/`) from `webui/openspec/changes/webui-graphify-agents/` into
  this change in `~/.claude/openspec/`, updating file-path references (Impact
  section) and Decision 9's premise to reflect the global home. The original
  `webui-graphify-agents` change directory is removed from `webui/openspec/changes/`
  once migrated — it was never truly a webui capability.
- Add a short `GRAPHIFY.md` (not `CLAUDE.md` — see design.md Decision 4, that
  filename is already taken by webui's own shared, repo-wide instructions) to
  each graph-build worktree (`webui-dev-graphify`,
  `webui-php-graphify`) explaining the worktree is build-only graph storage for this
  tooling, read via absolute path by the global agents, and maintained by
  `~/.claude/scripts/graphify-webui-maintain.sh` — so anyone finding the worktree in
  `git worktree list` isn't left guessing what it's for.
- Fold the previously "out of band, not part of this change" global-config edit
  (the `/graphify-webui`-first instruction, which actually landed in
  `~/.claude/skills/boot-bugfix/SKILL.md:52-57`, not literally in top-level
  `CLAUDE.md` as the original proposal said) into tracked `tasks.md` with an
  acceptance criterion matching where it actually landed.
- Re-verify the one acceptance criterion the original change flagged as never
  live-tested (tasks.md 6.2: a domain agent must surface a `graphify` failure rather
  than fabricate an answer) — agent file paths are changing, so this needs a fresh
  pass regardless of whether it passed before.

## Capabilities

### New Capabilities
- `webui-codebase-graph-query`: the query-time contract — two domain subagents
  (Angular, PHP), each querying its own `graphify` graph via a pinned absolute
  `--graph` path, with a build-if-missing bootstrap fallback and an orchestrating
  skill that fans out to both in parallel and synthesizes prose answers. Globally
  invocable from any session/repo.
- `webui-codebase-graph-maintenance`: the freshness contract — one dedicated
  worktree per domain graph, a weekly rebase-then-rebuild job per worktree (via
  `launchd`), and a dirty-tree abort policy that never auto-stashes.

### Modified Capabilities
(none — these capabilities are new to `~/.claude/openspec`; the original webui-side
change was never archived, so no existing spec baseline exists anywhere yet)

## Impact

- **webui repo**:
  - Removed: `.claude/agents/webui-angular-agent.md`, `.claude/agents/webui-php-agent.md`,
    `.claude/skills/graphify-webui/SKILL.md`, `openspec/changes/webui-graphify-agents/`.
  - Added: `GRAPHIFY.md` in each of the `webui-dev-graphify` and `webui-php-graphify`
    worktrees (sibling worktrees to the primary checkout, unaffected otherwise).
- **~/.claude (this repo)**:
  - Added: `agents/webui-angular-agent.md`, `agents/webui-php-agent.md`,
    `skills/graphify-webui/SKILL.md`, this change's artifacts.
  - Modified: `skills/boot-bugfix/SKILL.md` acceptance criteria/tasks.md now formally
    tracks what was previously an ad hoc, untracked edit there.
- **No change** to `graphify` CLI usage, graph build corpora, or scheduling mechanism
  (`launchd`, per original Decision 11) — this change is a relocation + documentation
  correction, not a redesign of the query/maintenance mechanics.
- **No change** to webui application runtime behavior (still true, unchanged from the
  original change).
