## Why

`live-regression-sweep` and `boot-playwright` both assume the target page is testable on the given tenant. The NPLAN-6460 Analyze live probe (2026-10-14) showed the cost of skipping that check: wrong route first, a UI that is a legend rather than the tabs the QE cases assumed, an irreversible "Run Analyze" that overwrites the tenant's last result, and blockers (RBAC role coverage, CF state) discovered only mid-run. Today the check is ad hoc: sweep's Phase 1 recon fires only when a page file is missing or stale, and boot-playwright relies on a prose rule to ask the user.

## What Changes

- Add a standalone, read-only skill `sweep-fit-check` that answers "is this page testable here, how, and at what risk" before any test run.
- Output a fixed JSON verdict (`GO` / `GO-WITH-LIMITS` / `STOP`) plus a Markdown report and a draft `pages/<slug>.md` for the sweep page registry.
- Wire `live-regression-sweep` to call it before Phase 0 on first use of a page (no page file, or `last_verified` older than 60 days), replacing the current ad hoc Phase 1 trigger.
- Wire `boot-playwright` to call it before loading a recipe when the target is a live tenant.
- Codify the live-probe lessons (login verification, stable selectors, short session names, mutation inventory) inside the skill.

## Capabilities

### New Capabilities
- `sweep-fit-check`: read-only applicability analysis of a page/route on a real tenant, with a stable verdict contract consumable by other skills.

### Modified Capabilities
- `boot-playwright`: gains a pre-recipe fit-check call for live-tenant targets.

## Impact

- New: `~/.claude/skills/sweep-fit-check/` (`SKILL.md`, `scripts/probe_fit.py`, `templates/`).
- Edited: `~/.claude/skills/live-regression-sweep/SKILL.md` (Phase 0/1 wiring), `~/.claude/skills/boot-playwright/SKILL.md`.
- No tenant writes, no application repo changes. Credentials continue to come from the sweep `.env` or chat only.
