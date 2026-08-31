#!/usr/bin/env bash
# Weekly maintenance for a webui graphify worktree: rebase onto origin/develop,
# then refresh the graph. Aborts (never stashes/discards) on any dirty tree or
# rebase conflict. See openspec/changes/webui-graphify-agents/ in webui repo.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <worktree-path> <corpus-path-relative-to-worktree>" >&2
  exit 2
fi

WORKTREE="$1"
CORPUS="$2"
LOG="$HOME/.claude/scripts/graphify-webui-maintain.log"

log() {
  printf '%s [%s] %s\n' "$(date -Iseconds)" "$WORKTREE" "$*" >>"$LOG"
}

if [ ! -d "$WORKTREE" ]; then
  log "ABORT: worktree not found"
  exit 1
fi

cd "$WORKTREE"

if [ -n "$(git status --short)" ]; then
  log "ABORT: dirty tree, skipping rebase+refresh (never auto-stashing)"
  exit 1
fi

if ! git fetch origin >>"$LOG" 2>&1; then
  log "ABORT: git fetch origin failed"
  exit 1
fi

if ! git rebase origin/develop >>"$LOG" 2>&1; then
  git rebase --abort >>"$LOG" 2>&1 || true
  log "ABORT: rebase conflict, rebase aborted, tree left untouched"
  exit 1
fi

# NOT `graphify update <path>` — it resolves output relative to <path> itself,
# not cwd, which recreates duplicate graphify-out/ dirs. Re-run the same full
# build used initially; AST extraction is content-hash cached per file so this
# is fast in practice. --code-only skips non-code files that would otherwise
# trigger a semantic-extraction attempt against an unconfigured LLM backend.
if ! graphify "$CORPUS" --code-only --out . --no-cluster >>"$LOG" 2>&1; then
  log "ABORT: graphify refresh failed"
  exit 1
fi

log "OK: rebased onto origin/develop and refreshed graph.json"
