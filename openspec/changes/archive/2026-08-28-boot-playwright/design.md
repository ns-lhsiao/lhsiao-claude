## Context

Four existing skills (`webui-devbox-playwright`, `init-dev-env`, `mf-cfw-playwright`,
`mf-client-playwright`) each carry a full copy of browser-automation mechanics
(session lifecycle, login, SPA hash nav, headless UA spoof, validation-plan/report
format) alongside environment-specific setup steps. `boot-bugfix` and `boot-feature`
each additionally hand-roll their own dev-env bootstrap + Playwright instructions
inline in their own `SKILL.md`, referencing `init-dev-env`/`mf-client-playwright`
ad hoc and using `playwright-cli` sessions — a third, newer mechanism not used by any
of the four skills being consolidated. A fifth environment (webui2 + Angular-shell
hybrid) has no first-party skill; its only existing reference is the third-party
plugin command `/wb:setup:angular-shell`, which itself has gaps versus its sibling
`/wb:setup:webui2-shell` (no DB-liveness check, missing `/pinger` proxy path, no
health-check retry loops, no fallback for missing `dev-backend.sh`).

## Goals / Non-Goals

**Goals:**
- One skill (`boot-playwright`) owns all shared browser-automation mechanics once.
- Four environment recipes, layered (mf-client/mf-cfw recipes point at the base
  devbox recipe rather than repeating its setup steps).
- One session mechanism (`playwright-cli`) across all recipes and both boot-* callers.
- `boot-bugfix`/`boot-feature` delegate to `boot-playwright` instead of inlining
  dev-env + Playwright instructions.
- webui2-angular-shell-devbox recipe is self-contained and gap-free relative to the
  `/wb:setup:webui2-shell` reference, even though it's built on the
  `/wb:setup:angular-shell` hybrid-mode base.

**Non-Goals:**
- Deleting the four legacy skill directories (deprecation pointer only, this change).
- Wrapping or depending on the third-party `wb:setup:*` plugin commands at runtime —
  they were read for reference/gap-analysis only; `boot-playwright`'s recipes are
  independently owned content.
- Auto-detecting which recipe applies from changed files — that logic lives in the
  caller (human or `boot-bugfix`/`boot-feature`), not inside `boot-playwright`.
- Changing the devbox-ui per-slug SLOT port formula or any other environment
  mechanic — this change relocates and de-duplicates existing knowledge, it does not
  redesign the underlying dev stacks.

## Decisions

### 1. Session mechanism: standardize on `playwright-cli`, drop hand-rolled `browserServer`/ws-endpoint-file

The four legacy skills each hand-roll a `chromium.launchServer()` +
`fs.writeFileSync(wsEndpoint)` + reconnect-on-reuse pattern, with a different
endpoint-file path per skill (`/tmp/pw-session-endpoint.txt`,
`/tmp/pw-cfw-session-endpoint.txt`) purely to avoid collisions. `boot-bugfix` already
uses `playwright-cli -s=<name> open` (named sessions, built-in reuse-if-exists).
Adopting `playwright-cli` everywhere removes the endpoint-file bookkeeping entirely —
session naming (`-s=<recipe-or-slug>`) replaces file-path collision-avoidance.

Alternative considered: keep the raw Playwright API pattern and have `boot-bugfix`
adopt it instead. Rejected — `playwright-cli` is strictly less code for callers to
generate correctly per invocation, and it's already proven in `boot-bugfix`.

### 2. Recipe layering: mf-client/mf-cfw recipes extend, don't duplicate, the base recipe

`recipes/webui-angular-devbox-mf-client.md` and `-mf-cfw.md` open with an explicit
"read `webui-angular-devbox.md` first, bring up the base stack" instruction and then
contain only their own delta (dev server, proxy, MF-readiness wait). This was chosen
over each recipe being fully self-contained (which would let a reader open exactly
one file and never cross-reference, at the cost of ~80% duplicated content between
the base and each MF-specific recipe, and duplicated content drifting out of sync —
the exact problem this change is trying to eliminate one layer up).

### 3. Recipe selection is an explicit argument, not auto-detected

`/boot-playwright <recipe> <slug>` requires the caller to name the recipe. Rejected
alternative: have `boot-playwright` inspect changed files itself and pick a recipe.
`boot-bugfix`/`boot-feature` already know which UI area they're validating (they
just finished editing it), so the detection logic is trivial and cheap at the
call site — pushing it into `boot-playwright` would mean duplicating repo-layout
knowledge (which paths mean mf-client vs. mf-cfw vs. webui2) inside a skill that
otherwise has no reason to know it.

### 4. Legacy skills: deprecate in place, don't delete

Each of the four legacy `SKILL.md` files is replaced with a one-line pointer to
`boot-playwright` (per the user's explicit choice) rather than deleted outright.
This keeps the skill directories around for a comparison window before a future
cleanup pass removes them once `boot-playwright` has been exercised in real
`boot-bugfix`/`boot-feature` runs.

### 5. webui2-angular-shell-devbox recipe: rewritten from the hybrid-mode command, backfilled from its non-hybrid sibling

`/wb:setup:angular-shell` (hybrid Angular+webui2, the actual target environment) is
missing operational robustness that its sibling `/wb:setup:webui2-shell` (plain
webui2, no Angular) has: MariaDB/Colima liveness check, `/pinger` in
`PUBLIC_LOCAL_API_PATHS`, curl retry-loop health checks with kill-on-failure,
`dev-backend.sh`-missing fallback, dependency-install skip-if-present. The new
recipe merges hybrid-mode's Angular-specific content (dist build, hybrid plugin env
vars, `signed_off_pages.json` cache, headed-only requirement) with the operational
robustness backfilled from the non-hybrid command, rather than shipping the hybrid
command's gaps forward into a new first-party skill.

## Risks / Trade-offs

- **[Risk]** Layered recipes (Decision 2) require a reader of the mf-client/mf-cfw
  recipe to also open the base recipe — one extra file open per invocation.
  → **Mitigation**: each layered recipe's opening line names the base recipe file
  explicitly; this is a one-time cost per session, not per step.
- **[Risk]** Deprecating in place (Decision 4) leaves five skills matching similar
  trigger phrases ("playwright", "devbox", "validate UI"), risking the wrong one
  being picked by future skill-matching.
  → **Mitigation**: each deprecated `SKILL.md`'s `description:` frontmatter is
  rewritten to say "deprecated, use boot-playwright" up front, since the
  description (not just the body) drives skill selection.
- **[Risk]** `boot-bugfix`/`boot-feature` becoming **BREAKING** changes to their own
  Phase 5 / Step 3.5 means any in-flight bugfix/feature run relying on the old
  inline instructions mid-session could behave differently on re-invocation.
  → **Mitigation**: no persistent state depends on the old inline instructions
  (each `boot-*` invocation is a fresh run); no migration needed beyond the
  `SKILL.md` edits themselves.
- **[Risk]** The webui2 recipe (Decision 5) is unvalidated against a real hybrid
  stack run — the gap-backfill is derived from reading two reference commands, not
  from executing either.
  → **Mitigation**: flag this recipe for a real dry-run the first time
  `boot-feature` exercises a webui2 change, before trusting it unattended.

## Migration Plan

1. Create `boot-playwright/SKILL.md` + `recipes/*.md` (net-new, no risk to existing
   skills while in progress).
2. Rewrite `boot-bugfix` Phase 5 and `boot-feature` Step 3.5 to call
   `/boot-playwright <recipe> <slug>`.
3. Replace the four legacy `SKILL.md` bodies with deprecation pointers (frontmatter
   `description` updated first, per the mitigation above).
4. No rollback complexity: reverting is `git revert` on the `~/.claude` config repo
   commit(s) — nothing external depends on these files.

## Open Questions

- None outstanding — all four ambiguity points raised during `/opsx:explore` were
  resolved with the user (session mechanism, recipe layering, recipe-selection
  argument style, legacy-skill disposition, ticket-specific content disposition).
