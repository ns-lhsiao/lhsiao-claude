---
name: escalation-check
description: Run the escalation-risk design gate on demand — deterministic pre-scan plus the mandatory checklist verdict table — for a design document the PostToolUse hook did not see (written before the hook existed, checked out from git, or produced by another agent).
argument-hint: "<path to design.md>"
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

# Escalation Check

**Input**: a path to a design artifact (`.md`). If omitted, infer the most recently
written design artifact in the session; if still ambiguous, ask.

The same gate the `PostToolUse` hook fires automatically on `Write|Edit|MultiEdit`:
`~/.claude/hooks/escalation_design_check.py` against
`~/.claude/escalation-risk-checklist.md`. Use this command when the hook did not run —
the doc predates the hook, arrived via `git checkout`, or came from another agent.

## Step 1 — deterministic pre-scan

```bash
python3 - "$ARGUMENTS" <<'PY'
import json, subprocess, sys
path = sys.argv[1]
content = open(path, encoding="utf-8", errors="replace").read()
payload = {"tool_name": "Write",
           "tool_input": {"file_path": path, "content": content}}
print(subprocess.run(
    ["python3", "/Users/lhsiao/.claude/hooks/escalation_design_check.py"],
    input=json.dumps(payload), capture_output=True, text=True).stdout)
PY
```

The hook dedupes on content hash, so a doc it already gated returns nothing. When that
happens, say so and run the scan inline instead: the category table is the `CATEGORIES`
list in `~/.claude/hooks/escalation_design_check.py` (trigger keywords vs mitigation
keywords — trigger without mitigation = ATTENTION, both = NOTED).

## Step 2 — checklist pass

Read `~/.claude/escalation-risk-checklist.md` in full. For **every category that is
topically relevant to this design** (not every category), decide:

- `ADDRESSED` — cite the design section that handles it
- `GAP` — state the missing requirement precisely enough to add it
- `N/A` — say why the category does not apply here

Emit one row per category, most severe first:

`# · category · verdict · evidence or missing requirement`

## Step 3 — fold back

Every `GAP` becomes either an explicit requirement in the design or an open question.
Do not silently pass the gate, and do not report a category you did not actually evaluate.

## Boundaries

- Read-only on code. This command evaluates the **design document** only; it never opens
  source. To fact-check the verdict table against real code, hand off to
  `/escalation-verify <path>`.
- Do not re-run the scan on cosmetic edits — the hash dedup exists to prevent that.
