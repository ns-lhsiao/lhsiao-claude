---
name: live-regression-sweep
description: >-
  Fan-out live regression testing of several webui pages against a REAL tenant
  (not a local dev stack). Preflights the tenant (login, feature-flag and renderer
  matrix), optionally recons each page's source, then runs one sub-agent per page
  in its own playwright-cli session, and aggregates screenshot-backed HTML reports
  plus a machine-readable results.json that can be diffed against the previous run.
  Per-page knowledge (routes, renderer discriminators, flags, RBAC mock targets,
  cleanup, case library with stable IDs) lives in pages/*.md. Triggers on
  "/live-regression-sweep", "live regression", "sweep these pages on <tenant>",
  "crowd test the pages", "regression test on qa tenant with screenshots".
argument-hint: "<tenant-url> <page-slug...|all> [--recon-only] [--no-mutate] [--project <slug>]"
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Grep
  - Write
  - Edit
  - Agent
  - AskUserQuestion
---

# Live Regression Sweep

Runs the same regression case library against a real tenant, one sub-agent per page,
and produces (a) one dark-theme HTML report per page with a screenshot for every case
and (b) `results/<slug>.json` so the next run can say what regressed.

Use it for "does the whole area still behave" sweeps. Do NOT use it for verifying one
fix (that is `boot-bugfix` / `boot-playwright`) or for local dev stacks (those are
`boot-playwright` recipes).

## Invocation

```
/live-regression-sweep <tenant-url> <page-slug...|all> [--recon-only] [--no-mutate] [--project <slug>]
```

- `<page-slug>` must match a file in `pages/` (see list below). `all` = every page file
  not starting with `_`. Unknown slug: list valid slugs and STOP.
- `--recon-only`: Phase 0 + Phase 1 only. No browser mutations.
- `--no-mutate`: run only cases marked `mutates: N`; skip the rest as `N-A (no-mutate)`.
- `--project`: output folder under `/Users/lhsiao/ns/git/all-html/`. Default
  `live-regression-<tenant-host-first-label>`, e.g. `live-regression-qa-de`.

Pages available: `client-configuration`, `devices`, `service-profile`, `firewall-app`,
`network-profile`. Add a page by copying `pages/_TEMPLATE.md`.

## Credentials

Never in args, files that are tracked, reports, screenshots, or logs.

- `~/.claude/skills/live-regression-sweep/.env` (git-ignored; see `.env.example`):
  `LRS_USER`, `LRS_PASSWORD`. If absent, ask the user in chat and pass them to sub-agents
  only inside the agent prompt. Do not write them to disk.
- After every run run `scripts/check_report.sh <report-dir>`; it greps for the password
  and for broken `<img>` links.

## Phase 0 — Preflight (you, not a sub-agent)

1. Open ONE session, log in (see "playwright-cli rules"), then probe the renderer matrix:

   ```bash
   sed "s|__PATTERN__|<regex from pages/*.md flags.globals>|" scripts/probe_globals.js > /tmp/claude/lrs/probe.js
   playwright-cli -s=lrs eval "$(cat /tmp/claude/lrs/probe.js)"
   playwright-cli -s=lrs eval "async () => { const r = await fetch('/api/v2/ui/platform/featureflags/balkan_features_enabled',{credentials:'include'}); return r.status+' '+(await r.text()).slice(0,1500) }"
   ```

2. For every requested page, compare the flags against `renderer_matrix` in its page
   file and decide which renderer WILL mount. Print the matrix to the user.
3. **Gate.** If a page's target renderer is unreachable on this tenant (flag off, no
   licence, 403), do not screenshot the wrong renderer as a pass. Mark that renderer
   `BLOCKED`, test the renderer that IS mounted, label it clearly in the report, and
   tell the user which flag a tenant admin must change. If the user's goal was the
   unreachable renderer, ask (AskUserQuestion) before spending the run.
4. Decide mutation policy: `--no-mutate`, or each page's `mutation` block. Pages whose
   cleanup needs Apply (see `apply_policy`) are flagged to the user up front.

## Phase 1 — Recon (optional, read-only)

Run when a page file is missing, `last_verified` is older than ~60 days, or the user
asks. One read-only agent per page: map source (route, component, controller, flags,
RBAC constant, API), list existing tests, answer `open_questions`. Output goes back
into the page file (propose the diff to the user; do not silently rewrite).

## Phase 2 — Live fan-out

One sub-agent per page, run in parallel, launched in a single message. Build each
prompt from `templates/live-agent-prompt.md` by filling the `{{...}}` placeholders from
the page file. Defaults:

- Session name: the page file's `session` (<= 15 chars; longer names truncate the
  daemon socket and the session dies silently).
- Concurrency: all requested pages. Each agent logs in independently with its own session.
  Warn the user about cost: a live agent used roughly 150-220K tokens and 15-25 minutes
  in the reference run. Offer a subset if they asked for `all`.
- Orchestration is plain `Agent` fan-out. If the user explicitly asks for a workflow,
  the `Workflow` tool may be used (recon -> live -> verify pipeline) but never start it
  on your own.

Each agent returns: counts, top findings, report path, cleanup confirmation. Treat the
return text as a claim, not proof (Phase 3 verifies).

## Phase 3 — Aggregate and verify

1. `scripts/check_report.sh <report-dir>`: broken images, password leak.
2. **Spot-check screenshots.** Open at least 2 per page: one PASS and the most
   important FAIL. A report whose screenshots do not show the claimed state is wrong
   regardless of what the agent said.
3. **Cleanup ledger.** For each page, confirm via API/UI that no object with the page's
   `object_prefix` remains live or pending. Anything left is listed to the user.
4. **Diff vs previous run:** `scripts/diff_results.py <prev-results-dir> <this-results-dir>`
   prints new FAIL / fixed / still failing / missing cases. Include it in the summary.
   First run = no baseline; say so.
5. Update `/Users/lhsiao/ns/git/all-html/index.html` (group `<h2>` with count, one `<li>`
   per report with `data-tags`, `.snippet`, `.tags`; tags like `playwright-e2e`,
   `validation`, `angular`, `react`, `client-config`). Use `grep -n`/`sed -n` and a python
   replace with a `count == 1` assert; the Read tool mangles that file.
6. Report to the user: per-page result table, regressions first, then new findings,
   then cleanup state, then what was NOT tested (BLOCKED / N-A with reason).

## Safety contract (copy into every agent prompt)

- Shared tenant. Create/edit/delete ONLY objects whose names start with the page's
  `object_prefix` + a 4-char run id. Never touch pre-existing objects.
- Delete every object created; verify via API; record final state.
- **Never click Apply / Send for Approval / call deploy** unless Phase 3 asks the user
  and they say so explicitly (see Apply policy).
- Real devices/users/clients are READ-ONLY: no delete, no enable/disable, no unenroll.
- No tenant-wide settings changes. No password in any file or caption.
- A failure is reported as FAIL with evidence; retry at most once, and say so.

## Apply policy

Pending changes are tenant-global: Apply pushes other people's pending changes too.
Some legacy pages have no revert, so test objects can only be removed by Apply.

1. Before asking, open the pending panel and list what is pending and who owns it.
2. Ask with AskUserQuestion, naming the foreign pending items. A free-text "ok" /
   "可以" is NOT enough; the question must offer explicit "Apply" vs "leave pending".
3. After Apply, verify by a fresh list read (see "session timeout" below). Record it in
   the report's Cleanup section with before/after counts and the audit note used.

## playwright-cli rules (all learned the hard way)

- Run every call with the sandbox disabled. Headless works on tenants (no UA block seen on qa.de).
- Login: open `<tenant>/locallogin`, `snapshot`, `fill` Username/Password by ref, click
  `Log In`, poll `eval "() => location.hash"` until it is not `#/login...` (~20 s).
- After login NEVER `open`/`goto` a `#/...` URL (drops the session). Navigate with
  `eval "() => { window.location.hash = '#/...'; }"` or by clicking nav. Page loads of
  30-60 s are normal; poll for a readiness selector.
- **Session timeout.** The tenant session dies after several idle minutes. A snapshot
  that suddenly shows no rows / no buttons may be the "Your session has timed out" page.
  Always screenshot before concluding "gone", re-login, and re-read state. Never infer
  success from an empty snapshot.
- `run-code` page.route mocks must be registered in the SAME call as the navigation.
  `playwright-cli` sessions keep routes only within that call.
- Multi-line JS: write to a file, then `eval "$(cat file)"`.
- The RBAC mock target differs per page; use the page file's `rbac_mock`. Two families
  exist: `/api/v2/rbac/roles/me` (React/MFE pages) and `POST /rbac_v3/getRoleFunctionPrivileges`
  (legacy Angular pages, returns a string like `"rwa"`; mock `"r"`).
- Long-running click commands may hit the 60 s tool timeout and move to background;
  re-snapshot instead of assuming failure.
- If rtk mangles `grep`/`git`, call `/usr/bin/grep`, `/usr/bin/git`.
- Leave sessions open during the run; close them only when the user says they are done.

## Report contract

Per page: `<project>/<slug>.html`, screenshots in `<project>/screenshots/<slug>/<CASE-ID>-<slug>.png`,
referenced with RELATIVE `<img src>` inside `<figure class="shot"><figcaption>`. Reuse the
dark-GitHub `<style>` block from an existing report (e.g. any file under
`all-html/webui-e2e-qa-de/`). Sections: H1 + sub, meta chips (tenant, date, renderer,
flag evidence), Summary table (ID | case | priority | result | screenshot), per-case cards
(steps, expected, actual, badge, screenshot), Findings, Cleanup state, Environment/limits.
Results: PASS / FAIL / PARTIAL / BLOCKED (with reason) / N-A (with reason).

Each agent also writes `<project>/results/<slug>.json`:

```json
{
  "run": {"tenant": "https://qa.de.goskope.com", "date": "2026-10-07", "page": "devices", "renderer": "react-mf-client"},
  "cases": {
    "DV-01": {"title": "renderer gate", "result": "PASS", "screenshot": "screenshots/devices/DV-01-renderer-gate.png", "note": ""}
  }
}
```

Case IDs come from the page file and are stable. New cases get new IDs; never renumber.

## Page registry

`pages/<slug>.md` = YAML frontmatter (route, session, renderer_matrix, flags, rbac_mock,
api, object_prefix, mutation, apply_policy, open_questions, last_verified) + a case table
(`ID | title | priority | mutates | baseline`). `baseline` is the last observed behavior;
a deviation from baseline is a regression candidate even if the case "passes" visually.
Update `baseline` and `last_verified` after a run the user accepts.

## Known cost and limits

- The tenant account is usually a single admin; RBAC cases are mock-based and prove UI
  hiding only. Server-side 403 needs a separate API-level check with a restricted token.
- Counts of rows/devices on the tenant limit pagination cases (mark PARTIAL).
- Delete-in-use needs a referencing object; create one only if the page file says how.
