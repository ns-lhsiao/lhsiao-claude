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
- Defer to project-level CLAUDE.md if it specifies a different output location.

## Sensitive Data

- NEVER commit passwords, API keys, access key IDs, service account credentials, tokens,
  or any other secret material to any file, in any repository, under any circumstances.
  If you encounter secrets in source, flag them to the user immediately.

## Configuration Repo

- `~/.claude` is a git repo tracking user-authored config (`ns-lhsiao/lhsiao-claude`).
- Tracked files: CLAUDE.md, LEARNINGS.md, settings.json, skills/, scripts/
- After modifying tracked config files, commit and push to keep the repo in sync.

@RTK.md
