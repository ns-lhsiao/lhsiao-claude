---
name: learn
description: >-
  Retrospectively reviews the current session for errors, corrections, and
  recovered failures, then records new learnings in ~/.claude/LEARNINGS.md.
user-invocable: true
allowed-tools:
  - Read
  - Edit
  - Bash(git:*)
---

# Learn

Retrospective pass over the current conversation to harvest any learnings that
the real-time "WORKFLOW INTERRUPT" protocol may have missed.

## Instructions

### 1. Scan the conversation history

Walk back through the **full conversation** and identify every instance of:

- A tool call that returned an error, followed by a different approach that succeeded.
- A user correction of an assumption, misunderstanding, or incorrect command/flag/endpoint.
- Unexpected API, CLI, or library behavior that required changing flags, methods, paths,
  or invocation patterns.
- Any moment where the first attempt was wrong and a second attempt succeeded for a
  different reason than a trivial typo.

Collect each finding as a tuple: **(what failed, why it failed, what worked instead)**.

### 2. Read current learnings

Use the Read tool to load `~/.claude/LEARNINGS.md`. For each finding from step 1,
check whether an existing entry already covers it. A finding that substantially
overlaps an existing entry should be:

- **Skipped** if the existing entry already captures the essential information.
- **Merged** (via Edit) if the new finding adds meaningful detail to the existing entry.

### 3. Draft candidate entries

For each *new* finding (not already covered), draft an entry matching the established
format:

- **H2 heading** (`##`): short, descriptive title of the problem area.
- **Bullet(s)**: state what failed, why, and the correct approach. Keep terse — high
  signal-to-word ratio. Include exact commands, flags, API paths, or code patterns
  where applicable.

### 4. Apply changes

If there are **no findings**, report that plainly and exit — do not manufacture entries.

Otherwise, use Edit to append new entries to `~/.claude/LEARNINGS.md` (or merge into
existing entries where appropriate).

### 5. Commit and push

Stage, commit, and push the changes to `ns-lhsiao/lhsiao-claude`:

```
git -C ~/.claude add LEARNINGS.md && git -C ~/.claude commit -m "docs: record learnings from session" && git -C ~/.claude push
```

## Quality Guardrails

- **Err toward inclusion.** If uncertain whether something qualifies, include it.
- **No duplicates.** Skip findings already captured unless the new detail is substantial.
- **Terse entries.** Match the existing entry style — no verbose prose, no filler.
- **Honest "no findings" output.** If the session had no errors or corrections, report
  that cleanly and take no further action.
