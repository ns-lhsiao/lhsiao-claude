## Why

The escalation-prevention design gate — `escalation_design_check.py` (PostToolUse
hook), `escalation-risk-checklist.md`, and the `/escalation-check` entry point —
currently exists only inside `/Users/lhsiao/ns/git/nplan6460/.claude/`. It was
authored there on 2026-09-29 while working NPLAN-6460 and never left.

Two things break because of that scoping:

1. **`skills/escalation-verify/SKILL.md` (global, tracked) already assumes the gate
   is global.** It references "the escalation-prevention design hook (or
   `/escalation-check`)" (line 4-5) and `escalation-risk-checklist.md` (line 22,
   29-31). Neither the hook, the checklist, nor a `/escalation-check` command exists
   under `~/.claude/`, so the skill's step "If none exists, run `/escalation-check
   <design.md>`" is a dead end in every repo except nplan6460.
2. **hedr-hub already triaged this gap and filed it as work.** `roles/triage.log.md`,
   2026-11-13: "hub 2 triaged: … s3 work/do (escalation-check hook + checklist
   absent, refs in escalation-verify SKILL.md)". Still open.

The gate is personal Claude Code config, not an nplan6460 artifact: the checklist's
categories are distilled from customer escalations across the whole product, and the
hook's trigger set (OpenSpec `changes/*/{proposal,design}.md`, `specs/*/{spec,design,plan}.md`,
generic `design.md`/`plan.md`) is repo-agnostic. Scoping it to one project directory
means every other design gets zero escalation-risk review.

## What Changes

- **Move the hook to `~/.claude/hooks/escalation_design_check.py`** — unchanged logic.
- **Move the checklist to `~/.claude/escalation-risk-checklist.md`** — sits at the
  hook's default fallback path (`dirname(hook)/../escalation-risk-checklist.md`), so no
  env var is required.
- **Wire it globally** in `~/.claude/settings.json` `PostToolUse` for
  `Write|Edit|MultiEdit`, with `ESCALATION_MARKER_DIR` pinned to
  `~/.claude/.escalation-hook` so review markers stop littering every repo/worktree.
- **Add `/escalation-check`** (`~/.claude/commands/escalation-check.md`) — the
  manual entry point `escalation-verify` already tells callers to use.
- **Retire the project-local duplicate** in `nplan6460/.claude/settings.local.json` so
  design writes there do not fire two gates.
- **Fix the dangling references** in `skills/escalation-verify/SKILL.md` to name the
  real global paths.

Not in scope: changing the category set, thresholds, or the heuristic scan; publishing
the checklist upstream to `netSkope/webui-openskills` (the skill's source repo).

## Impact

- Every session: design-artifact writes ≥150 words now inject a review instruction.
  Cost is one extra `additionalContext` block per materially-changed design, deduped by
  content hash.
- `~/.claude` gains two tracked files (`hooks/escalation_design_check.py`,
  `escalation-risk-checklist.md`, `commands/escalation-check.md`) plus a `.gitignore`
  allowlist entry for the top-level checklist.
