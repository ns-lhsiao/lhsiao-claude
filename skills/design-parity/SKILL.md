---
name: design-parity
description: >-
  Reviews an implemented UI against its Figma design (or prototype / annotated
  screenshots), finds source-code mismatches, separates real bugs from parity gaps
  from backend gaps, then fixes them through OpenSpec + parallel sub-agents and ships
  PR(s) plus a dark-theme HTML validation report. Triggers on "/design-parity", "UI
  parity", "figma parity", "looks weird vs figma", "match the design", or a screenshot
  of a page the user says doesn't match the design.
argument-hint: "<page/route or feature> [figma-url | annotated-png-dir] [ENG-1234]"
allowed-tools: Bash(*), Bash(playwright-cli:*), Read, Write, Edit, Grep(*), Glob(*), Agent, AskUserQuestion, Skill
user-invocable: true
---

# Design Parity

**Emit "Skill activated: design-parity"**

Pipeline: **Reference → Audit (3 parallel agents) → Decide with user → Worktree +
OpenSpec → Implement (parallel per surface) → Integrate + browser-verify → Report +
PR(s)**. The orchestrator (you) keeps conclusions only; sub-agents read files and
drive the browser. Keep each phase ≤ 4 concurrent agents.

## Phase 0 — Resolve inputs (no questions unless truly missing)

| Input | How to find it |
|---|---|
| Target surface | User screenshot / route / feature name. For NPLAN work check the project tracking dir (e.g. `~/ns/git/<nplan>/CLAUDE.md`, `dev-progress.md`) and any `serve-*` skill for worktree + dev-server recipe. |
| Design reference | Figma URL → `figma-mcp` skill (`get_screenshot` + `get_design_context`). Else existing annotated PNGs under `all-html/<project>/screenshots/figma-vs-spec/` (`mockup-api-mapping` output). Private `*.pages.github.io` prototype → CDP recipe in global CLAUDE.md. |
| Decision records | `openspec/specs/**`, `openspec/changes/**` (incl. `archive/`), design docs / `ui-implementation-notes.md` / `figma-vs-spec-*.html` / `sheet-vs-spec-*.html` in `all-html/<project>/`. |
| Ticket | User-provided key, else ask once (mf-cfw commitlint requires `ENG-NNN:`). |
| Base branch | The integration branch the feature lives on (NOT the repo default for NPLAN work). |

If the reference cannot be obtained, stop and ask — never audit against memory.

## Phase 1 — Parallel audit (3 agents, all read-only, one message)

Give every agent the reference image paths, worktree path, and "use `/usr/bin/git`,
`/usr/bin/grep`; HTML via grep/sed not Read". Ask for reports < 900 words.

1. **Element → source map + intent audit.** For each visible element in the user's
   screenshot: the `file:line` that renders it. For each divergence from the design:
   *deliberate* (cite the openspec/design-doc line) or *accidental* (built from ticket
   wording, misread note, etc.). Also: host-shell embedding issues (duplicate
   breadcrumb/title — check the shell's hide-list, e.g. webui
   `ngweb-breadcrumb.util.ts` `hideBreadcrumbCriteriaPredicateFns`), and which
   Periskope (`@netskope-ui/*`) components implement the design layout.
2. **Per-surface divergence table** for secondary surfaces (results, history, detail,
   empty states): element | design | impl `file:line` | deliberate? | severity
   (high=structure, med=copy/missing element, low=spacing/color) | fix. Flag impl
   elements absent from the design.
3. **Live capture.** Serve the current build, capture every state to
   `all-html/<project>/screenshots/ui-parity/NN-<state>.png`, record computed
   font/size/color/bbox of headings, labels, inputs, buttons, and **all console
   errors** (render loops show up here first). Close the session at the end.

## Phase 2 — Synthesize + decide

Present one compact gap list grouped as: **Real bugs** (fix regardless) ·
**Parity rework** · **Out of scope (backend gap)**. Then `AskUserQuestion` (≤ 3 questions)
only for genuine forks, typically:
- Scope: bugs only / bugs + primary surface / everything.
- Design vs API conflict (e.g. design shows one item, API takes an array).
- Design vs recorded decision conflict (e.g. breadcrumb depth chosen in an earlier design.md).

## Phase 3 — Worktree + OpenSpec

- Worktree per repo touched (global CLAUDE.md rules; `node_modules` symlink only if
  lockfile md5 matches; `npx husky install` for mf-cfw). Branch
  `pr/<TICKET>/<slug>` off the integration branch. `git worktree add` and writes there
  usually need the sandbox disabled.
- Tiny cross-repo fixes (one predicate + spec) skip OpenSpec per the carve-out; commit
  them directly.
- Main change: **fork** an agent to run `/opsx:ff <slug>-figma-parity` (read
  `~/.claude/commands/opsx/ff.md`). Requirements:
  - MODIFIED/REMOVED deltas against existing specs the parity reverses; SHALL/MUST on
    the **first line** of every requirement body.
  - `tasks.md` split into **disjoint-file sections** (one per surface) + a final
    Shared/verification section. Declare **shared contracts** up front (exact export
    names/signatures + file paths) so parallel sections can import each other.
  - i18n ownership: each section edits only its own namespace, exact-string Edit only.
  - `openspec validate <change> --strict` passes.

## Phase 4 — Parallel implementation (one agent per section, one message)

Each prompt: read proposal/design/tasks/its spec + reference PNGs; files it owns;
contracts it must deliver **first** or may consume (poll for them, never stub);
"re-read before editing shared files (`SimulatorTab`-style composers,
`react-app-env.d.ts`, i18n json), never Write them whole"; run tsc + its jest dir;
tick its tasks; no commits. When the user gives a mid-flight layout tweak, apply it
yourself if the owning agent is done.

## Phase 5 — Integrate + verify

1. `tsc --noEmit`, eslint on touched dirs, jest for the feature + its api dir.
2. i18n orphan check: flatten the json, grep each leaf key (watch dynamic keys like
   `` `${side}_group` `` before deleting).
3. **Browser-verify agent** on a NEW port from the worktree (never reuse a sibling
   server): after-shots to `screenshots/ui-parity-after/`, assert zero render-loop
   console errors, compare to reference with measurements, list remaining gaps
   honestly, then write the report (Phase 6) — or do the report yourself.
4. Fix every bug the browser run finds **before** committing; re-run 1.

## Phase 6 — Report + ship

- Report `all-html/<project>/<slug>-figma-parity.html`, stylish dark theme (copy the
  `<style>` from `fix-devices-search-stale-row.html` verbatim). Sections: H1 + .sub,
  meta chips (ticket, branches, change), Root Cause, The Fix (files table),
  Validation (unit → browser table → before/after figures), Out of scope, Open items.
  Add the `index.html` entry (data-tags, .snippet, .tags; python exact-replace with a
  `count==1` assert — the file is too large for Edit).
- Commit per repo convention (mf-cfw/webui: `ENG-NNN: subject`), body explains why.
- Screenshots → `netSkope/pr-screenshots` `develop` at `<repo>/<TICKET>/screenshots/`,
  embed with `https://github.com/netSkope/pr-screenshots/raw/develop/...` under
  `## Validation`.
- `gh pr create` (unsandboxed) against the integration branch, filling the repo's
  `.github/pull_request_template.md`; cross-link companion PRs. End with the
  Claude Code attribution line.
- Final message: PR links, what changed, verification numbers, open items
  (placeholder copy, backend gaps, residual visual diffs). Leave dev servers you
  started stopped.

## Known traps (Periskope / mf-cfw) — check these first

- **Built from ticket text, not Figma** is the usual root cause. Look for spec text
  that copies the ticket verbatim.
- `@netskope-ui/select` `Select.Root` runs `useEffect(onChange(...), [selected, onChange])`
  → an inline `onChange` arrow + RHF `useWatch` = "Maximum update depth exceeded".
  Pass a stable `useCallback`, skip no-op writes. jsdom shows it as a test **hang**,
  not a console.error.
- `Select.Trigger` without `asChild` is the nested-submenu item (right caret,
  borderless) — looks like an empty band. Use `Select.Trigger asChild` with a
  bordered anchor + chevron-down.
- `<Text className="text-lg">` is a no-op (`ps-text` forces `text-sm`); use
  `fontSize="lg"` (+ `as="div" role="heading" aria-level`).
- `@netskope-ui/table` orders columns by `accessorKey`; display-only columns still
  need one. `withAdminPreferences` stored `column_order` overrides new defaults —
  bump the `page` key when the column set changes.
- `InputV2` puts `data-testid` on both wrapper and input → `getByTestId` ambiguous
  against the real component.
- New `@netskope-ui/*` exports must be added to the shadow declarations in
  `src/react-app-env.d.ts`.
- Silent input normalization (e.g. dropping empty items before POST) breaks
  index alignment between form and results — prefer blocking submit.
- Never claim parity from a screenshot you didn't measure; list residual gaps.
