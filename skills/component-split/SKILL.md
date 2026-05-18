---
name: component-split
description: >-
  Refactors a large React component file into a directory of co-located
  sub-components. Uses a design → critique → implement → review pipeline with
  sub-agents to enforce "no abstractions for single-use operations" and other
  project conventions. Triggers on "split this component", "refactor X into a
  directory", "extract sections from X", "break up this file", or any request
  to decompose a >300-line component file.
argument-hint: "<component file path>"
user-invocable: true
---

# Component Split

**Emit "Skill activated: component-split"**

Refactor a large React component file into a directory containing the parent
plus one file per logical sub-component or substantial helper. Follow the
design → critique → implement → review pipeline so the refactor preserves
behavior, respects project conventions, and avoids speculative abstractions.

## Context

$ARGUMENTS

---

## When to use

- A single component file exceeds ~300 lines.
- The file has 3+ visual sections, embedded helper components, or a mix of
  unrelated concerns (e.g. parent component + row helpers + utility
  functions).
- A reader has to scroll past obviously-detachable subtrees to follow the
  main flow.

## When NOT to use

- The file is under 200 lines. Splitting almost always adds indirection.
- The file has only 1-2 sections and no extractable helpers.
- The component is a thin wrapper around a third-party widget.
- The user asked to refactor logic, not file structure — that's a different
  task.

## PHASE 0: Survey

Before designing anything, gather facts:

1. **Read the file** end-to-end. Don't guess.
2. Run `wc -l` on the file and any siblings in the same directory.
3. List the file's sub-components and module-level helpers (`grep -n
   "^function\|^export function\|^const "`).
4. Find every consumer (`grep -rn "from '.*<FileName>'"`).
5. Find any tests that reference the file by path or its testids.
6. Check the project's CLAUDE.md hierarchy for conventions:
   - Repo-root `CLAUDE.md`
   - `apps/<app>/CLAUDE.md` (if monorepo)
   - Feature-local `CLAUDE.md`

## PHASE 1: Design (sub-agent)

Spawn a sub-agent to draft the directory layout. Brief it with:

- The exact file path.
- The list of sub-components, helpers, and module constants.
- The names and line ranges of section boundaries (e.g. `<SectionHeading>`
  markers).
- Tightly-coupled state that must NOT split (e.g. functions that close over
  shared form context, useState pairs that must be co-located).
- Project rules excerpted from the CLAUDE.md files.
- Any prior precedent — point to a previously-refactored sibling if one
  exists in the codebase.

Ask the sub-agent for:

1. A directory tree under `<ComponentName>/`.
2. Per-file: which JSX block + helpers it owns, what hooks it calls, what
   constants travel with it.
3. A migration step list (each step keeps tests green).
4. Risks specific to this file (cross-tab dependencies, modal
   mount-stability, useState that must travel together, etc.).
5. What to NOT split out and why (reject single-use abstractions).

Constrain the sub-agent's output to under 600 words.

## PHASE 2: Critique (sub-agent)

Spawn a SECOND sub-agent to critique the design from Phase 1. This sub-agent
should NOT have seen the design proposal — give it the same source file plus
the proposed plan as input. Ask for:

1. Plan flaws (split granularity, dependency direction, prop plumbing).
2. Missed risks the plan didn't enumerate.
3. Convention violations against the CLAUDE.md files.
4. Concrete refinements.
5. Anything to keep as-is (don't manufacture critique).

Constrain to under 350 words.

If the critique surfaces real issues, synthesize a revised plan. Common
revisions seen in practice:

- Drop sub-directories that contain only one file (speculative nesting).
- Drop barrel `index.ts` files (just import the concrete file path).
- Move shared constants out to a sibling file when 2+ extracted components
  use them.
- Lift modal/dialog mount points out of conditionally-rendered sections so
  they survive collapse.
- Choose ONE pattern across siblings: either all sections call a shared
  hook, or all receive its result via props. Don't mix.

## PHASE 3: Implement

Execute the migration in steps. **Tests must pass between every step.**

### Step A: Move the file into a directory

```bash
mkdir -p <Component>/
git mv <Component>.tsx <Component>/<Component>.tsx
```

Update relative import paths inside the moved file: `../../` becomes
`../../../`, etc. Update consumer import paths to the new explicit path:
`from './<Component>'` → `from './<Component>/<Component>'` (no barrel).

Run tests to confirm the move alone hasn't broken anything.

### Step B: Extract sub-components

For each section, extract in order from least-coupled to most-coupled (i.e.
sections with no shared state first, sections with the most state last).

For each extraction:
1. Create the new file with the section's JSX + the constants/hooks it owns.
2. Replace the inline block in the parent with `<SectionName />`.
3. Drop unused imports from the parent.
4. Run tests.

### Step C: Co-locate helpers

If a helper component is used by exactly one parent section, nest it under
that section's folder ONLY when:
- The helper is non-trivial (>30 lines), AND
- The directory has at least one other file that justifies the folder.

Otherwise keep the helper as a flat sibling. A directory with one file is
speculative nesting.

### Step D: Avoid these traps

- **No barrel `index.ts`** files. They add a redirect for one consumer with
  no benefit. Use explicit `from './Foo/Foo'` paths.
- **No `FormSection` / `FieldRow` / generic-wrapper abstractions** built
  during the refactor. The project rule "no abstractions for single-use
  operations" applies — three similar lines beat a premature wrapper.
- **No prop-drilling state that's already in context.** If the parent uses
  `useFormContext`, children should call it themselves, not receive
  `control` via props (unless it lets them avoid double subscription, e.g.
  in a virtualized list).
- **Don't split a closure unit.** A function that closes over 5+ values
  from the parent's render scope (`methods`, `setActiveTab`, `t`, `flags`,
  `onSubmit`, etc.) should stay inline. Extracting it as a hook trades
  inline simplicity for prop plumbing — usually a net loss.
- **Don't move the form-reset `useEffect`** away from the comment that
  documents its INVARIANT. Comments rot when separated from code.

## PHASE 4: Review (sub-agent)

After all extractions are done, spawn a third sub-agent to review the
result. This sub-agent has NOT seen the design or critique. Give it:

- The new file paths in dependency order.
- A summary of what changed (1-2 sentences).
- The CLAUDE.md rules.
- Confirmation that tests pass.

Ask for:
1. Bugs introduced (anything where behavior changed).
2. Section boundary issues (wrong things in wrong places).
3. Convention violations.
4. Things to keep as-is (explicit go/no-go).

Constrain to under 350 words. Address any real issues before committing.

## PHASE 5: Commit

One commit per refactor. Use `refactor(<scope>): split <Component> into
directory of sections` as the subject. Body should:

- State the line-count delta (was X lines, now Y).
- List the new files with one-line purpose for each.
- Note any non-obvious decisions (e.g. "modal kept at parent so it survives
  section collapse").
- Note that all N tests pass.

Match the project's commit style (Conventional Commits, Jira prefix, etc.)
by checking `git log` first.

## Output

After completing the pipeline, report to the user:
- Number of files created/moved.
- New parent line count vs. old.
- Test count and pass status.
- Any deferred items the reviews flagged.

## Rules

- **Read first, edit second.** Always read the actual source before
  designing. Don't trust filenames.
- **Tests green at every step.** Each extraction is a checkpoint. If a step
  breaks tests, stop and diagnose before adding more.
- **Reject premature abstractions.** When in doubt, don't extract. The
  project's CLAUDE.md says "three similar lines is better than a premature
  abstraction" — apply it.
- **Preserve all `data-testid`, `id`, RHF `name` attributes verbatim.**
  Tests + the project's own UX (tab-jump, scroll-to-error) depend on
  these.
- **Respect existing precedent.** If the codebase already split a sibling
  component, follow that pattern (or improve on it explicitly, not
  silently).
- **Never use sub-agents to implement the refactor itself** — they don't
  preserve enough context across files. Use sub-agents for design,
  critique, and review only. Do the implementation yourself.
- **Never invent a sub-component name** that doesn't reflect its actual
  contents. If you can't name it cleanly, the split is wrong.
