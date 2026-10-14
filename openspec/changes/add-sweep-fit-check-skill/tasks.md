## 1. Skill scaffold

- [x] 1.1 Create `skills/sweep-fit-check/SKILL.md` (frontmatter, invocation, verdict contract, gate rules, safety contract)
- [x] 1.2 Add `templates/fit-report.md` and `templates/page-draft.md` (reuse `_TEMPLATE.md` frontmatter, optional `qe_ref` column)
- [x] 1.3 Document the playwright-cli rules learned in the 2026-10-14 probe (verify login URL, `'#id'` / `role=` selectors, coordinate click for close buttons, session name <= 15 chars)

## 2. Probe script

- [x] 2.1 Write `scripts/probe_fit.py` (stdlib only): flag lookup, `roles/me` check, GET endpoint probes
- [x] 2.2 Classify error-shaped 200 responses (`success:false` or missing `data`) as errors
- [x] 2.3 Report control flag as `unknown` unless entry-point evidence is supplied; never assume on
- [x] 2.4 Compute `untested_roles` from the page file versus the session's role
- [x] 2.5 Emit the JSON contract and fail closed on any unexpected exception (`verdict: STOP`)

## 3. Caller wiring

- [x] 3.1 Edit `live-regression-sweep/SKILL.md`: call fit check before Phase 0 on first use or stale page file; keep Phase 1 for source recon
- [x] 3.2 Edit `boot-playwright/SKILL.md`: call fit check before recipe load for live-tenant targets only
- [x] 3.3 Implement the skip rules (`last_verified` <= 60 days, `--skip-fit`) and the `--yes` limits (never for `STOP`)

## 4. Verification

- [x] 4.1 Dry-run against `lhsiao.qa` using the Analyze page file; confirm no non-GET request and `Run Analyze` appears only under `side_effects`
- [x] 4.2 Confirm the expected verdict (`GO-WITH-LIMITS`, `untested_roles` = [none], fixture-dependent cases `BLOCKED`; also verified STOP on entry-not-mounted, expired session and bad cookie file)
- [x] 4.3 Run `live-regression-sweep/scripts/check_report.sh` on the output directory (no credential or cookie leak)
- [ ] 4.4 Commit in `~/.claude` worktree, push, and open the PR
