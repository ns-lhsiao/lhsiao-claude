---
name: reground
description: >-
  Re-reads and internalizes the full CLAUDE.md directive chain. Use after /clear
  or when context has drifted during a long session.
user-invocable: true
allowed-tools:
  - Read
  - Glob
---

# Reground

Re-read the **entire CLAUDE.md file chain** — global (`~/.claude/CLAUDE.md`), any
project-level, and any subdirectory-level files — so that all directives are fresh
in working memory.

## Instructions

1. Use Glob to find every `CLAUDE.md` file that applies to the current session,
   starting from `~/.claude/CLAUDE.md` and walking down through the project hierarchy.
2. Use Read to load each file found.
3. After reading, produce a **brief summary** (no more than 10 lines) confirming which
   files were loaded and calling out any key directives especially relevant to the
   current working directory. The summary MUST always include the **learnings protocol**:
   when a tool call fails and you recover via a different approach, or the user corrects
   a misunderstanding, update `~/.claude/LEARNINGS.md` immediately after recovery
   succeeds and before resuming the original task.
4. Do NOT take any other action. This skill is purely a re-orientation step.
