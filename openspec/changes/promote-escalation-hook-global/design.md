## Context

See `proposal.md`. Precedent for the same move: `openspec/changes/archive/2026-08-31-graphify-webui-globalize`
(promoted webui-scoped graphify skill + agents into `~/.claude/`).

## Decisions

### D1 — Checklist at `~/.claude/escalation-risk-checklist.md`, not inside the skill dir

The hook resolves the checklist as `ESCALATION_CHECKLIST` → `dirname(__file__)/../escalation-risk-checklist.md`.
Putting it at `~/.claude/` root satisfies the fallback with zero configuration, and keeps it
out of `skills/escalation-verify/`, which is managed by `openskills` (`source:
netSkope/webui-openskills`) — a re-install would overwrite or orphan a file placed there.

Alternative rejected: checklist beside the skill + `ESCALATION_CHECKLIST` in settings.json.
Works, but adds an env var for no benefit and couples the hook to the skill's lifecycle.

### D2 — Pin `ESCALATION_MARKER_DIR` to `~/.claude/.escalation-hook`

Default is `$PWD/.escalation-hook`, which already produced 38 markers in `nplan6460`,
3 in `mf-cfw-simulate-export-csv`, 5 + 3 in two other worktrees, and 2 in `nplan6460/.claude`.
Marker keys are `sha1(absolute path)`, so one shared directory is collision-free and makes
"when did this design last get reviewed" answerable in one `ls -lt`.

`~/.claude/.escalation-hook` stays untracked (deny-by-default `.gitignore`), so markers never
show up as repo dirt.

### D3 — Retire the nplan6460 wiring rather than leave both

Two registrations would inject two `additionalContext` blocks on the same write (different
marker dirs → both fire, no dedup between them). Global wiring covers nplan6460 exactly as
before: the project's `ESCALATION_DESIGN_GLOBS='**/.specs/*/*.md'` is folded into the global
command line, since `.specs/` is a personal convention, not an nplan6460 one.

The project's `hooks/escalation_design_check.py` + `escalation-risk-checklist.md` files stay on
disk (harmless, unreferenced) — `nplan6460` is not a git repo, so deleting is a local-only
action the user can do later.

### D4 — `/escalation-check` is a thin manual wrapper

Its whole job is to run the same deterministic pre-scan + checklist pass on demand, for a
design written before the hook existed or edited outside the tool path (git checkout, another
agent). It must not grow into a second implementation: it invokes the same script
(`python3 ~/.claude/hooks/escalation_design_check.py` with a synthesized Write payload, or the
`prescan` semantics restated) and emits the same verdict-table requirement.

## Risks

- **Noise on unrelated repos.** A `design.md` written in any repo now triggers a gate. This is
  the intent, but the 150-word floor and content-hash dedup are what keep it tolerable; both are
  already implemented and unchanged.
- **Silent no-op if `python3` is absent from the hook's shell env.** Global settings already run
  `python3` for `gm-guard.py`, so the interpreter is known-good in that environment.
