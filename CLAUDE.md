# Claude Memory

## How to Interact With Humans

You are working with experienced software engineers at Netskope. They are skilled
in cloud-based distributed systems, microservice architecture, and full-stack web
development. Use domain-specific terms and concepts when appropriate.

Speak in complete, conversational sentences. Explain reasoning naturally without
over-elaborating. Prefer prose over lists for explanations and analysis; lists are
fine when enumerating concrete items such as files, options, or steps.

Calibrate verbosity to task type. For calculations, factual lookups, and
configuration choices: be terse — show the result and the minimum reasoning needed
to verify it. For design discussions, architecture trade-offs, and code review:
richer elaboration is appropriate. The failure mode to avoid is applying
design-discussion-level elaboration to lookup-level problems.

## Reasoning Discipline

Frontier-scale instruction-tuned models exhibit scale-dependent overthinking:
the tendency to overelaborate when a concise chain of reasoning suffices. This
introduces error accumulation on problems with straightforward solutions and is
the dominant failure mode on problems where smaller models outperform larger
ones. Counteract this:

- **Match reasoning depth to problem complexity.** Simple factual lookups,
  configuration decisions, and well-understood patterns need no extended
  deliberation. Reserve multi-step reasoning for genuinely ambiguous or
  novel problems.
- **Prefer concise explicit reasoning over verbose implicit reasoning.**
  When reasoning is warranted, use short, labeled steps rather than
  discursive prose that buries the logic. Each step should advance the
  conclusion; remove steps that merely restate the problem or hedge.
- **Constrain elaboration on mathematical and logical derivations.**
  Show only the essential calculation steps. Overelaboration in quantitative
  reasoning is the highest-risk failure mode — additional steps accumulate
  errors rather than improving accuracy.
- **Stop when you have the answer.** Do not continue generating justification,
  caveats, or alternative framings after reaching a confident conclusion.
  Post-answer elaboration is the most common form of overthinking.
- **Trust your first-pass answer.** When your initial assessment is short and
  confident, it is more likely correct than an elaborated revision. The most
  common error mode is not insufficient reasoning but over-reasoning that
  introduces doubt or errors into an initially correct conclusion.

Alignment training incentivizes thoroughness and hedging, which can degrade
performance on problems with clear answers. When you notice yourself adding
qualifications, alternative interpretations, or "however" clauses to a
confident conclusion, recognize that impulse as more likely a training artifact
than genuine uncertainty.

## Learnings

Read @LEARNINGS.md

- **WORKFLOW INTERRUPT — record before continuing.** When a tool call fails and you
  recover via a different approach, or the user corrects a misunderstanding, you MUST
  update `~/.claude/LEARNINGS.md` **immediately after the recovery succeeds and before
  resuming the original task.** Do not defer this to "later" or end-of-task — context
  and intent degrade quickly.
- Trigger conditions: a command returns an unexpected error and you retry differently;
  an API call needs different flags/method/path than you first tried; the user tells you
  something you assumed incorrectly. Any of these means stop, record, resume.
- Keep entries terse: state what failed, why, and the correct approach.

## Git Worktrees

- All feature work MUST be performed in a **git worktree**, never in the primary checkout.
  **Do not edit, write, or create any files until the worktree exists and you have `cd`-ed
  into it.** This applies regardless of how small or simple the change appears.
- When the user asks for a code change, follow this sequence: create worktree and topic
  branch, then begin editing inside the worktree.
- Worktree directories live in the **parent directory** of the primary checkout.
- Naming convention: `<repo_name>-<slug>`, where `<slug>` is a short kebab-case descriptor
  of the change (e.g., `my-service-fix-auth-timeout`).
- Remove the worktree directory and delete the local topic branch immediately after the PR
  merges. Then fast-forward the default branch in the primary checkout.
- Defer to project-level CLAUDE.md if it specifies a different worktree layout.

## Topic Branches

- Defer to project-level CLAUDE.md for branch naming conventions when they exist.
- If no project-level convention is specified, use: `<github_username>/<ticket>-<slug>`.
- Use the authenticated user's **GitHub username** (obtain via `gh api user --jq .login`),
  never their display name or real name.
- `<ticket>` is the issue or ticket number. For Jira tickets use the project-prefixed key
  (e.g., `ENG-1234`). Omit the ticket segment and its trailing hyphen if no ticket exists.
- `<slug>` is a short kebab-case descriptor of the change.

## Git Commits

- Use **Conventional Commits** style (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, etc.)
  for the subject line.
- Commit body: concise prose. Explain **why** the change was made, not just what changed.
  Reference the ticket if one exists. Follow best practices: blank line after subject,
  imperative mood in the subject, wrap body at 72 characters.
- Defer to project-level CLAUDE.md or skill instructions if they specify different commit
  conventions.

## Pull Requests

- **Title**: Conventional Commits form (e.g., `fix: resolve auth timeout on token refresh`).
- **Description**: concise prose explaining **why** the change was made. Place a single
  closing keyword on its own line at the end: `Fixes #42` or reference the Jira key like
  `ENG-1234`.
- **Screenshots**: When Playwright validation produced screenshots, host them in the
  `netSkope/pr-screenshots` repo (owned by Louis, commit+push directly to `develop` — no
  PR/approval needed) at path `{repo}/{slug}/screenshots/<original-filename>`, keeping the
  filenames Playwright/the report already produced. `{repo}` is the source repo the PR is
  against (`mf-client`, `webui`, `webui2`, etc). `{slug}` is the Jira ticket key (`ENG-1234`)
  when the branch has one, otherwise the branch name — resolved once per branch and not
  changed if a ticket gets attached later. Re-running validation on the same branch overwrites
  the files already at that path; never timestamp or version the directory. Embed each image
  in the PR description under a `## Validation` heading using
  `![caption](https://raw.githubusercontent.com/netSkope/pr-screenshots/develop/{repo}/{slug}/screenshots/<file>)`.
  Never reference a local file path; GitHub markdown will not render it. If the shots also
  live under `all-html/<project>/` (see **HTML Reports**), reference the same
  `raw.githubusercontent.com` URLs there too so the report and PR share one source.
- **Merge method**: squash merge only when merging via API.
- Defer to project-level CLAUDE.md if it specifies different PR conventions.

## Planning with OpenSpec

- **Every non-trivial code change must start with `/opsx:propose "<description>"`.**
  This includes features, refactors, multi-file bugfixes, and chores. Do not
  open editors or run `Edit`/`Write` against project source until an `/opsx`
  proposal exists for the change.
- **Carve-out — trivial fixes only.** Skip `/opsx` for single-line typo fixes,
  comment edits, formatting-only changes, or one-line dependency bumps where
  intent is self-evident from the diff. When in doubt, propose first.
- **Multi-file bugfixes go through `/opsx`, not `/boot-bugfix` alone.** A bug
  whose fix touches >1 file or crosses a serialization boundary needs the
  proposal/specs/tasks artifacts so the design is captured before code lands.
  `/boot-bugfix` is reserved for targeted single-file fixes.
- **Repo without `openspec/`.** If the repo has no `openspec/` directory at the
  root, ask the user whether to run `openspec init` first or proceed without
  OpenSpec for this task. Do not silently skip the gate.
- **Slash commands**: `/opsx:propose`, `/opsx:apply`, `/opsx:archive`. The CLI
  (`openspec`) is installed globally via npm; init it per-project.
- **Why**: requested 2026-05-25. Without an upfront proposal, design decisions
  get rediscovered mid-implementation, parity bugs ship, and PRs need
  immediate follow-ups. Forcing the artifact moves the thinking left.

## Source Code Comments

- When **caveman mode is active** (`/caveman lite|full|ultra` or any caveman skill
  loaded by the harness), write inline source-code comments (`//`, `#`, short
  JSDoc bodies) in caveman style: drop articles, filler, and hedging; fragments
  OK; short synonyms allowed. Apply matching intensity to comments as the active
  caveman level.
- This **overrides** the default caveman boundary that says "code/commits/security
  write normal." That boundary still applies to **commit messages**, **PR titles
  and bodies**, and **security warnings** — those stay in normal prose.
- Never abbreviate identifiers, function names, error strings, API paths,
  config keys, or other technical tokens. Comment prose compresses; code symbols
  do not.
- Verbose vs caveman example for an inline comment:
  - Normal: `// Reset cross-page Select All state so reopening the panel after a close does not inherit stale bulk-selection intent.`
  - Caveman (full): `// Reset cross-page Select All on close. Else header stays checked w/ empty selectedRows, unselectedIds bleed into next session.`
- When caveman mode is **off** (`stop caveman` / `normal mode`), revert to
  normal comment prose immediately. Do not retroactively rewrite comments
  written under the other regime unless asked.
- Defer to project-level `CLAUDE.md` if it specifies a different comment
  convention.

## HTML Reports

- Any HTML report you generate (summaries, reviews, dashboards, etc.) MUST be written to
  `/Users/lhsiao/ns/git/all-html/<project>/<name>.html`, never into a project's own repo
  directory. `<project>` is a short kebab-case slug for the task/repo the report is about.
- Create the `<project>` subdirectory if it doesn't exist.
- After writing or moving a report, update `/Users/lhsiao/ns/git/all-html/index.html` in the
  same turn: add a `<li>` under the matching `<project>` `<h2>` group (create the group if new),
  and bump its `(N)` count. The index is a hand-maintained list, not a directory scan.
- **Each `<li>` entry must include a `data-tags` attribute, a `.snippet` div, and a `.tags` div**,
  matching the structure of existing entries in `index.html`. Required per entry:
  - `data-tags="tag1 tag2 tag3"` on the `<li>` — space-separated, matches the tag spans below.
  - `.snippet` — plain-text (no markup) one- or two-sentence summary of the report, max ~160
    chars, drawn from the report's own intro/first paragraph.
  - `.tags` — 2 to 4 `<span class="tag tag-<name>">` chips. Reuse an existing tag class from
    `index.html`'s `<style>` block (e.g. `rca`, `bugfix`, `validation`, `qa-plan`,
    `playwright-e2e`, `design-review`, `migration`, `todo-checklist`, `runbook`, `onboarding`,
    `deploy-infra`, `docker`, `nginx`, `k8s`, `steering-config`, `client-config`, `angular`,
    `webui2`, `feature-flag`, `react`) when it fits. Only invent a new tag when none fit —
    if you do, add a matching `.tag-<name>` CSS rule (light bg + matching dark text, GitHub
    label style) to the `<style>` block in the same turn.
  - The tag bar and search filtering are auto-generated from whatever `.tag` chips exist in the
    listing — no separate registration step needed beyond adding the chip to the entry.
- **Stylish template for `/boot-bugfix` and `/boot-feature` reports.** Any HTML report driven by
  `/boot-bugfix` or `/boot-feature` MUST use the "stylish" dark-GitHub theme established by
  `fix-devices-search-stale-row/fix-devices-search-stale-row.html` — reuse its `<style>` block
  verbatim: CSS vars (`--bg:#0d1117`, `--card:#161b22`, `--border:#30363d`, `--accent:#58a6ff`,
  `--green`/`--red`/`--yellow`), `.wrap` (max-width 960px), `.meta`+`.chip` header, `.card`,
  `pass`/`fail` table cells, `.shot`+`figcaption` for screenshots, and `.note` (yellow left-border
  callout). Keep the section order: H1 + `.sub`, meta chips, Root Cause, The Fix (files-touched
  table), Validation (criteria → unit/coverage → browser table + figures).
  - Attach the matching tag to the `index.html` `<li>`: `boot-bugfix` for `/boot-bugfix` reports,
    `boot-feature` for `/boot-feature` reports (in `data-tags` AND as a `.tag` chip). Add a
    `.tag-boot-bugfix` / `.tag-boot-feature` CSS rule to `index.html`'s `<style>` if absent.
- Defer to project-level CLAUDE.md if it specifies a different output location.

## Playwright / Browser Validation

- **Confirm a testable target BEFORE driving Playwright.** If the feature under test is not
  reachable on the current tenant/environment — a required feature flag is off (so webui serves
  the legacy renderer instead of the fix), the tenant lacks the data/config, or no environment is
  available — **PAUSE and ask the user** to either toggle the needed feature flag or name another
  candidate tenant/environment that can fulfill the validation. Do NOT proceed to screenshot a page
  that isn't actually exercising the change.
- **Why**: 2026-07-31 (ENG-1152682) a full Playwright run captured the *legacy Angular* devices page
  because `ng_devices_enabled` was off on the tenant — the React fix was never exercised, and the
  report + PR had to be redone. Verify the correct renderer is mounted (e.g. via a renderer-specific
  discriminator) before asserting.

## Sensitive Data

- NEVER commit passwords, API keys, access key IDs, service account credentials, tokens,
  or any other secret material to any file, in any repository, under any circumstances.
  If you encounter secrets in source, flag them to the user immediately.

## Configuration Repo

- `~/.claude` is a git repo tracking user-authored config (`ns-lhsiao/lhsiao-claude`).
- Tracked files: CLAUDE.md, LEARNINGS.md, settings.json, skills/, scripts/
- After modifying tracked config files, commit and push to keep the repo in sync.

@RTK.md
# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.
