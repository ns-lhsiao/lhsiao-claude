---
name: sweep-fit-check
description: >-
  Read-only applicability analysis of a page/route on a REAL tenant, run before any
  live test. Answers "is this testable here, how, and at what risk" and returns a
  GO / GO-WITH-LIMITS / STOP verdict as JSON plus a Markdown report and a draft sweep
  page file. Called by live-regression-sweep (first use of a page) and boot-playwright
  (live-tenant targets). Triggers on "/sweep-fit-check", "is this page testable on
  <tenant>", "fit check", "applicability analysis before live test".
argument-hint: "<tenant-url> <page-slug|route> [--skip-fit] [--yes]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# Sweep Fit Check

Run this BEFORE a live regression sweep or live-tenant validation. It never mutates the
tenant: GET requests only, no clicking of mutating UI actions. Its job is to surface, up
front, the things that otherwise surface mid-run: wrong route, unreachable renderer, flags
off, roles you cannot represent, cases that need design clarification, and actions that
cannot be undone.

## When it runs / is skipped

- Runs on first use of a page, i.e. `live-regression-sweep/pages/<slug>.md` is missing, or
  its `last_verified` is older than 60 days.
- Skipped when the page file is fresh (<= 60 days) and the previous verdict was not `STOP`,
  or when `--skip-fit` is passed.
- Sweep's Phase 1 (source recon) stays separate: fit-check is tenant-level, recon is
  source-level.

## Inputs

- Tenant URL, page slug (matches a `pages/*.md`) or a bare route + slug for a first run.
- Session cookie header in a file (mode 0600, under `/tmp/claude/`), exported with
  `playwright-cli -s=<short> cookie-list`. Never pass cookies or passwords on argv, never
  write them into outputs.
- Optional `--entry-mounted true|false|unknown`: whether the page's entry point (button,
  menu) visibly mounted. This is the only CF evidence available; the CF itself is not
  readable, so it is reported `unknown` or as evidence, never assumed on.

## Procedure

1. Log in with one playwright-cli session (see rules below), export the cookie to a file.
2. Look at the page in the browser read-only: does the entry point mount? Record
   `--entry-mounted`.
3. Run:

   ```bash
   python3 -I ~/.claude/skills/sweep-fit-check/scripts/probe_fit.py \
     --tenant <url> --cookie-file /tmp/claude/fit/cookie.txt --out-dir /tmp/claude/fit/<slug> \
     --page-file ~/.claude/skills/live-regression-sweep/pages/<slug>.md --entry-mounted <v>
   ```

   For a first run without a page file pass `--slug <slug> --route '<route>'` instead of
   `--page-file`.
4. Read `fit.json` (the contract) and show the user `fit-report.md`.
5. Gate (see below), then hand `fit.json` and the draft page file back to the caller.

## Verdict contract (`fit.json`)

| Field | Meaning |
|---|---|
| `target` | `kind` (crud-page / trigger-panel / api-only / unknown), `route`, `slug` |
| `renderer` | `entry_mounted`, `reachable`, `blockers[]` (flags that are off) |
| `access` | `ff{}` values, `cf{}` (`unknown` or `evidence:*`), `rbac{group, perm, role}` |
| `probes[]` | each GET: `path`, `status`, `result` ok/error, `why` |
| `side_effects[]` | mutating actions: `action`, `reversible`, `effect` (listed, never invoked) |
| `cases{}` | `RUNNABLE` / `BLOCKED:<reason>` / `N-A` / `NEEDS-DESIGN` |
| `untested_roles[]` | roles the page file needs that this session cannot represent |
| `verdict` | `GO` / `GO-WITH-LIMITS` / `STOP` |

`STOP`: target unreachable (flag off, permission absent, entry did not mount, critical
probe failed) or the probe itself failed (fail closed).
`GO-WITH-LIMITS`: reachable, but some case is `BLOCKED` / `NEEDS-DESIGN`, a role is
untested, or there is no page file yet.
`GO`: everything runnable, nothing untested.

Error-shaped 200s (`success:false`, or no `data` key) count as probe errors.

## Gate (callers MUST follow)

- `GO`: proceed. `--yes` skips the question.
- `GO-WITH-LIMITS`: show blocked cases, untested roles and side effects, then
  AskUserQuestion with explicit options (e.g. "Run runnable cases only" / "Stop"). `--yes`
  permits proceeding with the runnable subset.
- `STOP`: never proceed, even with `--yes`. Tell the user which flag/permission a tenant
  admin must change, and ask which tenant to use instead.
- A free-text "ok" is not enough when `side_effects` contains an irreversible action; the
  question must name the action and offer "run it" vs "skip it".

## Page-file additions (optional frontmatter keys read by the probe)

`kind`, `ff: [name]`, `cf: [name]`, `rbac_group`, `probes: [path | {path, expect: {status}}]`,
`critical_probes: [path]`, `side_effects: [{action, reversible, effect}]`,
`blocked_cases: {ID: reason}`, `needs_design: {ID: reason}`, `case_roles: {ID: roleName}`.
The existing keys (`route`, `session`, `renderer_matrix`, `rbac_mock`, `last_verified`...) are
unchanged. The `## Cases` table may add an optional `qe_ref` column; the probe ignores it.
A draft is written beside an existing page file as `<slug>.draft.md`; it never overwrites.

## playwright-cli rules (from the 2026-10-14 Analyze live probe)

- Run every call with the sandbox disabled.
- Verify login by reading the resulting URL/title; a first attempt can leave the form empty.
  Re-fill and re-click until the URL is no longer `/locallogin` or `/auth/login`.
- Navigate with `eval "() => { window.location.hash = '#/route' }"`, never `open`/`goto` a
  `#/` URL on a live session.
- Refs go stale between invocations. Use `'#id'`, `'button:has-text("...")'`,
  `'role=button[name="..."]'`, or `'text=...'`. Close buttons that resist selectors: click by
  coordinates (`mousemove x y; mousedown; mouseup`).
- Session names <= 15 characters (longer names truncate the daemon socket).
- Scroll an inner panel with `mousemove` over it then `mousewheel 0 <n>`; `scroll` and
  `scrollTop` loops may not reach it.
- Screenshot before concluding a state is empty (session timeout looks like "no rows").

## Output hygiene

Reports list probed endpoints and a timestamp so the run can be attributed in tenant audit
logs. No cookie, token or password in `fit.json`, `fit-report.md`, or the draft. After a run,
grep the output directory for the password and cookie values.
