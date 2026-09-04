#!/usr/bin/env bash
# Install the sync-claude-opencode skill as an opencode command.
# Run from anywhere: bash scripts/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OC_DIR="$HOME/.config/opencode"

echo "Installing sync-claude-opencode into opencode..."

# Create directories
mkdir -p "$OC_DIR/commands" "$OC_DIR/scripts"

# Copy the opencode command file
cat > "$OC_DIR/commands/sync-claude-opencode.md" << 'COMMAND_EOF'
---
description: Sync skills, commands, and MCP config between Claude Code and opencode.
---

Sync AI tooling between Claude Code (`~/.claude`) and opencode (`~/.config/opencode`).

## Input

`$ARGUMENTS` — direction and flags. Examples:
- `bidirectional` (default)
- `to-opencode`
- `to-claude`
- `--dry-run`
- `--force`
- `--mcp-block`

## Workflow

1. Parse direction and flags from `$ARGUMENTS`.
2. Run the sync helper:
   ```bash
   python3 ~/.config/opencode/scripts/sync_claude_opencode.py $ARGUMENTS
   ```
3. If the helper reports conflicts and `--force` is not set, ask the user whether to:
   - Re-run with `--force` to overwrite all conflicts
   - Specify a single direction (`to-opencode` or `to-claude`) to avoid conflicts
   - Skip conflicted files
4. Print the summary to the user.
5. If changes were made (not a dry-run), remind the user to restart opencode.

## Safety rules

- Always run with `--dry-run` first unless the user explicitly says otherwise.
- Never delete files; only copy or overwrite.
- Never print secrets from `mcp.json`.
- Restart opencode after sync for changes to take effect.
COMMAND_EOF

# Copy the Python sync script
cp "$SCRIPT_DIR/sync_claude_opencode.py" "$OC_DIR/scripts/sync_claude_opencode.py"
chmod +x "$OC_DIR/scripts/sync_claude_opencode.py"

# Check for pyyaml
if ! python3 -c "import yaml" 2>/dev/null; then
    echo ""
    echo "WARNING: pyyaml is not installed. Install it with:"
    echo "  pip3 install pyyaml"
fi

echo ""
echo "Done! Restart opencode, then run: /sync-claude-opencode --dry-run"
