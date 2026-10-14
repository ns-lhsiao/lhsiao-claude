## Context

`live-regression-sweep` runs a case library per page against a real tenant, and `boot-playwright` drives single-page validation. Both assume the target is reachable and safe to exercise. The 2026-10-14 Analyze live probe was done by hand and showed what a pre-check would have caught: a wrong route, a legend UI where the QE cases assumed tabs, an irreversible `Run Analyze` (overwrites the tenant's "last" result), and coverage limits (only the Tenant Admin role observable, CF state unreadable). Sweep's current Phase 1 recon only triggers on a missing or stale page file and is read-the-source oriented, not tenant-oriented.

## Goals / Non-Goals

**Goals:**
- One read-only skill that returns a machine-readable verdict and a human report before any test run.
- A contract both callers consume without parsing prose.
- Emit a draft sweep page file so the second run skips the check.

**Non-Goals:**
- Running test cases, mutating the tenant, or toggling flags.
- Replacing sweep's source-level recon (Phase 1 stays for source mapping; fit-check is tenant-level).
- Parsing QE test-plan documents. Cases come from a page file; translating a QE document into one is a manual step.

## Decisions

1. **Standalone skill, not a sweep phase.** Callers differ (sweep fans out, boot-playwright validates one fix) but need the same answer. Alternative: embed in sweep as Phase 0.5. Rejected because boot-playwright would then duplicate it.
2. **JSON contract is the interface.** Fields: `target.kind`, `renderer`, `access` (flags, rbac), `side_effects[]`, `cases{id: RUNNABLE|BLOCKED:<reason>|N-A|NEEDS-DESIGN}`, `untested_roles[]`, `verdict`, `page_draft`. Callers read only this file; the Markdown report is for the user.
3. **GET-only probing.** Mutating UI actions are detected from the page file or DOM labels and listed under `side_effects` with `reversible` and `effect`; they are never invoked. Escalation C1.
4. **Flags reported separately and honestly.** Feature flag via `/api/v2/ui/platform/featureflags/<name>`; control flag has no readable endpoint here, so it is reported `unknown` unless the entry point visibly mounts. Never inferred on. Escalation FF1.
5. **Coverage limits are part of the verdict.** Only the logged-in role is observable, so `untested_roles` lists roles the page file requires but the session cannot represent. Escalation RBAC1.
6. **Fake-200 handling.** An HTTP 200 whose body has `success:false` or lacks `data` is classified as an error, not as a reachable endpoint. Escalation FE3.
7. **Verdict gating.** `GO` and `GO-WITH-LIMITS` may proceed under `--yes`; `STOP` never does. A `GO-WITH-LIMITS` or `STOP` result requires the caller to ask the user via AskUserQuestion with explicit options.
8. **Skip rule.** Page file exists and `last_verified` is within 60 days, or `--skip-fit`. Chosen to match sweep's existing 60-day recon staleness rule.
9. **Probe implementation.** One Python script (`scripts/probe_fit.py`, stdlib `urllib`) takes a cookie header and a YAML-ish list of endpoints from the page file. Chosen over bash+curl for JSON assertions. Cookies are obtained by the caller via playwright-cli `cookie-list`, never persisted.

## Risks / Trade-offs

- [Fit-check passes but the first run still fails] → Verdict is advisory about reachability; `NEEDS-DESIGN` cases are listed so they are not scored as passes.
- [Extra round-trip on first use] → Skipped when the page file is fresh; `--yes` covers `GO`.
- [Credential leakage into reports] → Report templates have no credential fields; the sweep `check_report.sh` password grep is run on the output directory.
- [Page-file schema drift between sweep and fit-check] → Fit-check emits the existing `_TEMPLATE.md` frontmatter verbatim and adds only an optional `qe_ref` column.
- [CF stays `unknown`] → Accepted; the entry point's presence is recorded as separate evidence.
- [Probe traffic appears in the tenant's audit/access logs under the test user] → The report states the probed endpoints and timestamp so the run can be attributed; no attempt is made to suppress or avoid logging.

## Migration Plan

1. Land the skill and the two caller edits in one PR on the `~/.claude` config repo.
2. Dry-run against `lhsiao.qa` with the Analyze page (read-only) as the acceptance test.
3. Rollback: revert the caller edits; the skill directory is inert when not called.

## Open Questions

- Whether the draft page file should be written directly to `live-regression-sweep/pages/` or to a staging path for user approval (leaning staging).
- Where Simulate gets its own page file versus sharing the Analyze API probe.
