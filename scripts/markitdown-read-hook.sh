#!/usr/bin/env bash
# PreToolUse hook for Read: converts .pdf/.html/.htm inputs to Markdown via
# markitdown (run through uvx, no persistent install needed) and redirects
# the Read tool to the converted file via hookSpecificOutput.updatedInput.
set -uo pipefail

CACHE_DIR="$HOME/.claude/cache/markitdown"
input_json="$(cat)"

file_path="$(jq -r '.tool_input.file_path // empty' <<<"$input_json")"
[ -z "$file_path" ] && exit 0
[ -f "$file_path" ] || exit 0

ext="$(echo "${file_path##*.}" | tr '[:upper:]' '[:lower:]')"
case "$ext" in
  pdf|html|htm) ;;
  *) exit 0 ;;
esac

mkdir -p "$CACHE_DIR"

abs_path="$(cd "$(dirname "$file_path")" && pwd)/$(basename "$file_path")"
mtime="$(stat -f %m "$file_path" 2>/dev/null || stat -c %Y "$file_path" 2>/dev/null)"
hash="$(echo -n "$abs_path" | shasum -a 256 | cut -d' ' -f1)"
cache_file="$CACHE_DIR/${hash}-${mtime}.md"

if [ ! -s "$cache_file" ]; then
  if ! uvx markitdown "$file_path" -o "$cache_file" >/dev/null 2>&1; then
    rm -f "$cache_file"
    exit 0
  fi
fi

[ -s "$cache_file" ] || exit 0

updated_input="$(jq -c --arg f "$cache_file" '.tool_input + {file_path: $f}' <<<"$input_json")"

jq -n -c \
  --argjson updated "$updated_input" \
  --arg orig "$file_path" \
  '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
      permissionDecisionReason: ("Converted " + $orig + " to Markdown via markitdown before reading"),
      updatedInput: $updated
    }
  }'
