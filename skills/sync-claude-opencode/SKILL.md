---
name: sync-claude-opencode
description: Sync skills, commands, and MCP config between Claude Code (~/.claude) and opencode (~/.config/opencode). Use when the user says "sync my tools", "port my Claude skills to opencode", "sync commands", or wants to keep Claude Code and opencode configs in sync. Handles frontmatter conversion, conflict detection, and mcp.json copying bidirectionally.
---

# sync-claude-opencode

Sync AI tooling between Claude Code (`~/.claude`) and opencode (`~/.config/opencode`).

## What it syncs

| Item | Claude path | opencode path |
|------|-------------|---------------|
| Skills | `~/.claude/skills/<name>/SKILL.md` | `~/.config/opencode/skills/<name>/SKILL.md` |
| Commands | `~/.claude/commands/<name>.md` | `~/.config/opencode/commands/<name>.md` |
| MCP config | `~/.claude/mcp.json` | `~/.config/opencode/mcp.json` |

## Frontmatter conversion

When crossing the boundary, frontmatter is automatically converted:

**Claude -> opencode:**
- Skills: strip `allowed-tools` (not supported by opencode)
- Commands: strip `name`, `category`, `tags` (not supported by opencode command format)

**opencode -> Claude:**
- Skills: ensure `name` is present
- Commands: add `name` from filename, add `category: Workflow` and `tags: []` defaults

## Usage

```bash
# Preview what would change (always do this first)
python3 scripts/sync_claude_opencode.py bidirectional --dry-run

# Sync both directions
python3 scripts/sync_claude_opencode.py bidirectional

# Sync only Claude -> opencode
python3 scripts/sync_claude_opencode.py to-opencode

# Sync only opencode -> Claude
python3 scripts/sync_claude_opencode.py to-claude

# Force overwrite conflicts
python3 scripts/sync_claude_opencode.py bidirectional --force

# Also update the mcp block in opencode.jsonc for known servers (GitHub, Slack)
python3 scripts/sync_claude_opencode.py bidirectional --mcp-block
```

## Flags

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview without making changes |
| `--force` | Overwrite conflicts without prompting |
| `--mcp-block` | Also update the `mcp` section in `~/.config/opencode/opencode.jsonc` for known servers (GitHub, Slack) |

## Conflict resolution

By default, when both sides have a file and the content differs (after frontmatter conversion), the script reports a conflict. Use `--force` to overwrite with the newer file, or specify a single direction (`to-opencode` or `to-claude`) to avoid conflicts.

## Installing as an opencode command

Run the included `install.sh` to copy the command and script into your opencode config:

```bash
./scripts/install.sh
```

This installs:
- `~/.config/opencode/commands/sync-claude-opencode.md` (the `/sync-claude-opencode` slash command)
- `~/.config/opencode/scripts/sync_claude_opencode.py` (the sync engine)

After installing, restart opencode and run `/sync-claude-opencode --dry-run`.

## Dependencies

```bash
pip3 install pyyaml
```

(`commentjson` is optional — only needed if you use `--mcp-block` to parse `opencode.jsonc`.)

## Safety

- Never deletes files (no pruning by default)
- Never prints secrets from `mcp.json`
- The `--mcp-block` flag only updates known servers (GitHub, Slack); unknown servers stay in `mcp.json` only
- Always restart opencode after sync for changes to take effect
