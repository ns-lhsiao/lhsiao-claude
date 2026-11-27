## 1. Branch

- [ ] 1.1 `git -C ~/.claude checkout -b pr/promote-escalation-hook-global` (primary checkout — hooks must live at their live paths; a worktree cannot serve as `~/.claude`)

## 2. Promote the hook

- [ ] 2.1 Copy `nplan6460/.claude/hooks/escalation_design_check.py` → `~/.claude/hooks/escalation_design_check.py`, `chmod +x`
- [ ] 2.2 Copy `nplan6460/.claude/escalation-risk-checklist.md` → `~/.claude/escalation-risk-checklist.md` (hook's default fallback = `dirname(hook)/../escalation-risk-checklist.md`, so it resolves with no env var)
- [ ] 2.3 Add `!escalation-risk-checklist.md` to `.gitignore` allowlist

## 3. Global wiring

- [ ] 3.1 Add `PostToolUse` entry in `~/.claude/settings.json`, matcher `Write|Edit|MultiEdit`:
  `ESCALATION_DESIGN_GLOBS='**/.specs/*/*.md' ESCALATION_MARKER_DIR="$HOME/.claude/.escalation-hook" python3 "$HOME/.claude/hooks/escalation_design_check.py"`
- [ ] 3.2 Validate `settings.json` parses and `hooks.PostToolUse` has the new entry

## 4. `/escalation-check` command

- [ ] 4.1 Write `~/.claude/commands/escalation-check.md` — argument `<design.md>`, runs the same pre-scan, demands the verdict table
- [ ] 4.2 Confirm it appears as a user-invocable command (frontmatter `description`, `argument-hint`)

## 5. Fix dangling references

- [ ] 5.1 `skills/escalation-verify/SKILL.md`: name the real global paths for the hook, checklist, and `/escalation-check`
- [ ] 5.2 Keep the skill read-only / probe semantics unchanged

## 6. Retire the project-local duplicate

- [ ] 6.1 Remove the `PostToolUse` entry from `nplan6460/.claude/settings.local.json` (leaves `{}`-ish valid JSON)
- [ ] 6.2 Verify the project files (`hooks/`, checklist) are left on disk, unreferenced

## 7. Validation

- [ ] 7.1 Live-fire from `~` : synthesized Write payload on a >150-word `design.md` → expect `hookSpecificOutput.additionalContext` with ATTENTION rows
- [ ] 7.2 Re-fire identical content → expect empty stdout (content-hash dedup)
- [ ] 7.3 Confirm marker landed in `~/.claude/.escalation-hook/reviewed-*.txt` and NOT in `$PWD/.escalation-hook`
- [ ] 7.4 Confirm `ESCALATION_MIN_WORDS` floor still skips a short doc
- [ ] 7.5 Confirm no marker/dir created in the repo where the test runs

## 8. Ship

- [ ] 8.1 Stage only: `hooks/escalation_design_check.py`, `escalation-risk-checklist.md`, `settings.json`, `commands/escalation-check.md`, `skills/escalation-verify/SKILL.md`, `.gitignore`, `openspec/changes/promote-escalation-hook-global/**` (leave the pre-existing dirty `LEARNINGS.md` / `knowledge/*` untouched)
- [ ] 8.2 Commit (Conventional Commits) + push to `origin`
