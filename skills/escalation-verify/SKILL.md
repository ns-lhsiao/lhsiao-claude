---
name: escalation-verify
description: >-
  Verifies the verdict table produced by the escalation-prevention design hook
  (or /escalation-check) against the real source code. Turns each GAP /
  ADDRESSED row into a checkable claim, runs a fixed probe (grep / read / git),
  and re-ranks the findings as CONFIRMED-IN-CODE, REFUTED, DOC-DRIFT or
  UNVERIFIED with file:line evidence. Triggers on "/escalation-verify", "verify
  the escalation findings", "are these design gaps real", or a request to
  fact-check an escalation-check report against the code.
argument-hint: "<path to design.md | path to escalation report .html/.md> [--repo <path>] [--branch <name>]"
allowed-tools: Bash(git:*), Bash(/usr/bin/git:*), Bash(/usr/bin/grep:*), Bash(rg:*), Read, Grep, Glob
user-invocable: true
---

# Escalation Verify

**Emit "Skill activated: escalation-verify"**

The escalation hook reads **only the design document** (see
`escalation_design_check.py`: `.md` design artifacts only, keyword pre-scan, LLM
judgment against `escalation-risk-checklist.md`). It never opens source code, so
its GAP verdicts are design-level guesses and its ADDRESSED verdicts are claims
the code may not honor. This skill closes that loop. It is **read-only**: it
never edits code or the design.

## Inputs

1. A verdict table: output of the hook / `/escalation-check`, or a report that
   contains one (for example an `all-html/.../escalation-hook-*-scan.html`).
   If none exists, run the checklist pass first (`/escalation-check <design.md>`)
   and use its output.
2. The repo + branch the design **ships in**. Resolve it before probing:
   - OpenSpec change: `openspec/changes/<name>/` sits in the worktree whose branch
     carries the implementation. Check `tasks.md` for the ticket and PR.
   - Already merged: probe the merge commit or the integration branch, not an
     unrelated `master`. State which ref was probed in the report.
   - Never probe the primary checkout for an unmerged PR. Use its worktree.
   - Record the ref: run `/usr/bin/git -C <worktree> branch --show-current` and
     `/usr/bin/git -C <worktree> log --oneline -1`, and print both at the top of the
     report. A design gap that the code has since fixed is a `REFUTED` at HEAD, not a
     wrong finding; the reader can only tell the difference if the ref is on the page.
   - If the design predates its implementation (the usual case), say so in the
     report: verdicts describe the code **now**, not the code the design author saw.

## Step 1 — Extract claims

One row of the verdict table becomes one or more claims. Write each as a single
falsifiable sentence with a type:

| Type | Example claim | Source row |
|------|---------------|------------|
| `absent` | "Nothing trims whitespace on free-text identifiers before submit" | GAP |
| `present` | "A 409 is retried exactly once with a fresh UUID" | ADDRESSED |
| `name` | "The FF is `nplan6460_policy_analyzer_enabled` plus CF `NPLAN6460_POLICY_ANALYZER_ENABLED`" | any |
| `behavior` | "A late `GET /analyze/last` response after close reopens the panel" | GAP (FE1, R1) |

Drop rows marked `N/A`. Keep the design's own `file:line` for traceability.

**Split compound claims.** If one row bundles two separable assertions, write them
as `a` / `b` rows and judge each on its own. Dry-run example: "typed as a bare
`AnalyzeResp` and errors are status-only" became A1a (wrapper shape, since fixed)
and A1b (error-shaped `200` unchecked, still present). One verdict per row keeps a
half-fixed finding from being read as either fully real or fully false alarm.

## Step 2 — Run the probe (fixed set, no open-ended review)

Each claim type has a bounded probe. Do not widen it.

- **`absent`**: search the implementing files for the safeguard's vocabulary
  (per category: C2 `maxRows|limit`, C3 `escape|validate|422|field error`, FE1
  `AbortController|requestId|cancel|stale`, FE2 `trim|toLowerCase|normalize`,
  FE3 `success\s*===?\s*false|status.*error|throw` near the unwrap, FE4
  `slice|collapse|virtual|dedupe|key=`, RBAC1 `withAuthorization|hasPermission`).
  No hit in the files the change touches = candidate confirmation. Then read the
  single most relevant call site to rule out a differently named safeguard.
- **`present`**: open the cited code path and check the behavior the design
  promised (count, order, default, fail-open/closed). A wrong count or missing
  branch = `REFUTED`.
- **`name`**: compare against the code and against `tasks.md` / the PR. A mismatch
  where the code is newer than the design = `DOC-DRIFT`.
- **`behavior`**: read the handler and state logic that would produce it. If it
  can only be settled by running the app or a test, stop and mark `UNVERIFIED
  (needs-runtime)`. Name the Playwright or Jest check that would settle it; do not
  run it from here.

For `behavior` claims, `CONFIRMED-IN-CODE` means the unguarded path exists
(for example a state setter after `await` with no abort, feeding a `show` flag derived
from that state). It does **not** mean the symptom was reproduced. Say "code path
confirmed, repro needs-runtime" and name the Jest or Playwright step.

Scope each probe to the files in the change's diff (`git diff --name-only
<base>...<branch>`) plus their direct imports. Anything beyond that is out of
scope and must be reported as such.

## Step 3 — Judge

| Verdict | Meaning | Effect on severity |
|---------|---------|--------------------|
| `CONFIRMED-IN-CODE` | The design gap is real and the code has it too (established by reading the code path, not by running it) | raise one level |
| `REFUTED` | Code already handles it, the design just did not say so | lower to LOW, reclassify as "design under-documents" |
| `DOC-DRIFT` | Design and code disagree (names, counts, order, defaults) | keep; new class, fix is a doc edit |
| `UNVERIFIED` | Needs runtime, another repo, or a tenant | unchanged; list the exact check |

Every verdict carries evidence: `path:line` and a one-line quote of what was found,
or the exact search that returned nothing plus the files it covered. "I found no
hit" without the search and the file list is not evidence.

## Step 4 — Report

Emit a table, most severe first:

`# · category · design verdict → code verdict · evidence (file:line) · action`

followed by three short lists: findings **downgraded** (false alarms), findings
**upgraded** (real), and **DOC-DRIFT** items. End with the probe scope (repo,
ref, files in the diff) and anything left `UNVERIFIED`. If the user wants an HTML
report, follow the global HTML Reports convention (`all-html/<project>/`,
index entry with `data-tags`, snippet, tags).

## Worked example (dry run, mf-cfw `pr/ENG-1274461/nplan-6460-main` @ `b6d469d7`, webui `run-analyze-button`)

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| A1a | Analyze call typed as bare `AnalyzeResp` | `REFUTED` at HEAD | `policyAnalyzer.api.ts:15,21` unwrap `resp.data.data` (v21 realign) |
| A1b | Error-shaped `200` is not treated as failure | `CONFIRMED-IN-CODE` | `policyAnalyzer.api.ts:14-15,20-21` return `resp.data.data` unchecked; `api.ts:4-11` has no interceptor; Simulate side does check (`trafficSimulator.api.ts:33-34`) |
| A2 | Late `GET /analyze/last` after close reopens the panel; no in-flight lock | `CONFIRMED-IN-CODE` (repro `needs-runtime`) | `AnalyzeSidePanelWrapper.tsx:131-137` unconditional `setAnalyzeResp` after `await`; `:96-102` close only clears state; `:199` `show` derives from state; `:163-173` OPEN handler ignores `isRunning` |
| A6 | Design names a stale feature flag | `DOC-DRIFT` | `run-analyze-button/design.md:41,43,60,80,90,122` and `spec.md:4,7,11` use `..._analysis_enabled`; `show_feature_helper.php:1942,5123,5129` use `..._analyzer_enabled` + CF |

Lessons baked into the steps above: split A1 into a/b; print the probed ref; label
A2 as code-path-confirmed, not reproduced.

## Shell notes (zsh, worktree-isolated sessions)

- Call `/usr/bin/git` and `/usr/bin/grep` directly. The rtk hook rewrites `git` and
  can mangle quoted `grep` patterns into a silent "0 matches".
- Do not pass unquoted globs or flags containing `*` (`src/api/simulate/*.ts`,
  `--include=*.ts`). zsh aborts the whole command with "no matches found" before
  grep runs, which looks like an empty result. Quote the pattern, or use the Grep
  tool / `rg -g '*.ts'`.
- Read whole small files (an API module is usually under 60 lines) instead of
  trusting a grep-only "absent"; it is the cheapest way to avoid a false
  `CONFIRMED-IN-CODE`.

## Boundaries

- Read-only. Do not edit code, the design, or Jira.
- Do not re-litigate design quality; only test the claims the verdict table made.
- Do not expand into a general code review. A new issue found on the way is
  listed once under "Incidental", not investigated.
- Never run a dev server, Playwright, or a test suite from this skill; hand off.
- Inside a worktree-isolated session use `/usr/bin/git` and `/usr/bin/grep`
  directly (the rtk hook can mangle quoted patterns and trips the isolation guard).

## Known limits

- Grep vocabulary is heuristic. A safeguard with an unusual name can produce a
  false `CONFIRMED-IN-CODE`; the "read the call site" step exists to catch that.
- Cross-repo claims (Angular host vs mf-cfw remote) need both worktrees; probe each
  side separately and report them as separate rows.
- The result is a snapshot of one ref. Re-run after the branch moves.
