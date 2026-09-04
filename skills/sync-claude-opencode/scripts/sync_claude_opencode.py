#!/usr/bin/env python3
"""Sync skills, commands, and MCP config between Claude Code and opencode.

Usage:
    python3 sync_claude_opencode.py [direction] [flags]

Directions:
    bidirectional  (default) - sync both ways
    to-opencode    - Claude -> opencode only
    to-claude      - opencode -> Claude only

Flags:
    --dry-run      - preview without making changes
    --force        - overwrite conflicts without prompting
    --mcp-block    - also update the mcp section in opencode.jsonc for known servers
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. Install with: pip3 install pyyaml")
    sys.exit(1)

# ─── Paths ───────────────────────────────────────────────────────────────

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
OPENCODE_DIR = HOME / ".config" / "opencode"

CLAUDE_SKILLS = CLAUDE_DIR / "skills"
OPENCODE_SKILLS = OPENCODE_DIR / "skills"
CLAUDE_COMMANDS = CLAUDE_DIR / "commands"
OPENCODE_COMMANDS = OPENCODE_DIR / "commands"
CLAUDE_MCP = CLAUDE_DIR / "mcp.json"
OPENCODE_MCP = OPENCODE_DIR / "mcp.json"
OPENCODE_CONFIG = OPENCODE_DIR / "opencode.jsonc"

# ─── Known MCP server mappings for --mcp-block ───────────────────────────

KNOWN_MCP_SERVERS = {
    "github": {
        "type": "local",
        "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
        "environment": {"GITHUB_TOKEN": "{env:GITHUB_TOKEN}"},
    },
    "slack": {
        "type": "local",
        "command": ["npx", "-y", "slack-mcp-server@latest"],
        "environment": {
            "NODE_TLS_REJECT_UNAUTHORIZED": "0",
            "SLACK_MCP_XOXP_TOKEN": "{env:SLACK_MCP_XOXP_TOKEN}",
            "SLACK_REFRESH_TOKEN": "{env:SLACK_REFRESH_TOKEN}",
        },
    },
}

# ─── Frontmatter helpers ─────────────────────────────────────────────────


def parse_frontmatter(text):
    """Split markdown into (frontmatter_dict, body_string)."""
    if text.startswith("---\n") or text.startswith("---\r\n"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                fm = {}
            body = parts[2].lstrip("\n").lstrip("\r\n")
            return fm, body
    return {}, text


def serialize_frontmatter(fm, body):
    """Reassemble markdown from frontmatter dict and body string."""
    if fm:
        fm_text = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
        return f"---\n{fm_text}\n---\n\n{body}"
    return body


# ─── Format converters ───────────────────────────────────────────────────

ALLOWED_OC_SKILL_KEYS = {"name", "description", "license", "compatibility", "metadata"}
ALLOWED_OC_COMMAND_KEYS = {"description", "agent", "model", "variant", "subtask"}


def skill_to_opencode(fm, body, name):
    """Convert a Claude skill frontmatter to opencode format."""
    cleaned = {k: v for k, v in fm.items() if k in ALLOWED_OC_SKILL_KEYS}
    if "name" not in cleaned:
        cleaned["name"] = name
    return serialize_frontmatter(cleaned, body)


def skill_to_claude(fm, body, name):
    """Convert an opencode skill frontmatter to Claude format."""
    cleaned = dict(fm)
    if "name" not in cleaned:
        cleaned["name"] = name
    return serialize_frontmatter(cleaned, body)


def command_to_opencode(fm, body, name):
    """Convert a Claude command frontmatter to opencode format."""
    cleaned = {k: v for k, v in fm.items() if k in ALLOWED_OC_COMMAND_KEYS}
    return serialize_frontmatter(cleaned, body)


def command_to_claude(fm, body, name):
    """Convert an opencode command frontmatter to Claude format."""
    cleaned = dict(fm)
    cleaned["name"] = name
    if "category" not in cleaned:
        cleaned["category"] = "Workflow"
    if "tags" not in cleaned:
        cleaned["tags"] = []
    return serialize_frontmatter(cleaned, body)


# ─── File discovery ──────────────────────────────────────────────────────


def find_skills(directory):
    """Return {skill_name: SKILL.md_path}."""
    result = {}
    if not directory.exists():
        return result
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            skill_md = child / "SKILL.md"
            if skill_md.exists():
                result[child.name] = skill_md
    return result


def find_commands(directory):
    """Return {command_name: file_path}."""
    result = {}
    if not directory.exists():
        return result
    for child in sorted(directory.iterdir()):
        if child.is_file() and child.suffix == ".md":
            result[child.stem] = child
    return result


# ─── Sync engine ─────────────────────────────────────────────────────────


def convert_file(src_path, converter, name):
    """Read a file, convert its frontmatter, return the new content string."""
    text = src_path.read_text()
    fm, body = parse_frontmatter(text)
    return converter(fm, body, name)


def sync_direction(
    src_files, dst_files, dst_dir, kind, converter, force, dry_run
):
    """
    Copy files from src to dst that are missing or different.
    Returns list of (action, kind, name, src, dst) tuples.
    """
    changes = []
    for name, src_path in sorted(src_files.items()):
        dst_path = _dst_path(name, dst_dir, kind)
        new_content = convert_file(src_path, converter, name)

        if name not in dst_files:
            # File doesn't exist on dst — copy
            if not dry_run:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_text(new_content)
            changes.append(("COPY", kind, name, str(src_path), str(dst_path)))
        else:
            existing = dst_path.read_text()
            if new_content != existing:
                if force:
                    if not dry_run:
                        dst_path.write_text(new_content)
                    changes.append(
                        ("OVERWRITE", kind, name, str(src_path), str(dst_path))
                    )
                else:
                    changes.append(
                        ("CONFLICT", kind, name, str(src_path), str(dst_path))
                    )
    return changes


def _dst_path(name, dst_dir, kind):
    """Compute the destination path for a skill or command."""
    if kind == "skill":
        return dst_dir / name / "SKILL.md"
    return dst_dir / f"{name}.md"


def sync_skills(direction, force, dry_run):
    """Sync skills between Claude and opencode."""
    changes = []
    claude_skills = find_skills(CLAUDE_SKILLS)
    oc_skills = find_skills(OPENCODE_SKILLS)

    if direction in ("to-opencode", "bidirectional"):
        changes += sync_direction(
            claude_skills, oc_skills, OPENCODE_SKILLS,
            "skill", skill_to_opencode, force, dry_run,
        )
    if direction in ("to-claude", "bidirectional"):
        changes += sync_direction(
            oc_skills, claude_skills, CLAUDE_SKILLS,
            "skill", skill_to_claude, force, dry_run,
        )
    return changes


def sync_commands(direction, force, dry_run):
    """Sync commands between Claude and opencode."""
    changes = []
    claude_cmds = find_commands(CLAUDE_COMMANDS)
    oc_cmds = find_commands(OPENCODE_COMMANDS)

    if direction in ("to-opencode", "bidirectional"):
        changes += sync_direction(
            claude_cmds, oc_cmds, OPENCODE_COMMANDS,
            "command", command_to_opencode, force, dry_run,
        )
    if direction in ("to-claude", "bidirectional"):
        changes += sync_direction(
            oc_cmds, claude_cmds, CLAUDE_COMMANDS,
            "command", command_to_claude, force, dry_run,
        )
    return changes


def sync_mcp_json(direction, force, dry_run):
    """Sync mcp.json between Claude and opencode."""
    changes = []
    has_claude = CLAUDE_MCP.exists()
    has_oc = OPENCODE_MCP.exists()

    if not has_claude and not has_oc:
        return changes

    if has_claude and not has_oc:
        if direction in ("to-opencode", "bidirectional"):
            if not dry_run:
                shutil.copy2(CLAUDE_MCP, OPENCODE_MCP)
            changes.append(("COPY", "mcp.json", "", str(CLAUDE_MCP), str(OPENCODE_MCP)))
        return changes

    if has_oc and not has_claude:
        if direction in ("to-claude", "bidirectional"):
            if not dry_run:
                shutil.copy2(OPENCODE_MCP, CLAUDE_MCP)
            changes.append(("COPY", "mcp.json", "", str(OPENCODE_MCP), str(CLAUDE_MCP)))
        return changes

    # Both exist — compare content
    claude_content = CLAUDE_MCP.read_text()
    oc_content = OPENCODE_MCP.read_text()
    if claude_content != oc_content:
        if force:
            # newer wins
            if CLAUDE_MCP.stat().st_mtime > OPENCODE_MCP.stat().st_mtime:
                if direction in ("to-opencode", "bidirectional"):
                    if not dry_run:
                        shutil.copy2(CLAUDE_MCP, OPENCODE_MCP)
                    changes.append(
                        ("OVERWRITE", "mcp.json", "", str(CLAUDE_MCP), str(OPENCODE_MCP))
                    )
            else:
                if direction in ("to-claude", "bidirectional"):
                    if not dry_run:
                        shutil.copy2(OPENCODE_MCP, CLAUDE_MCP)
                    changes.append(
                        ("OVERWRITE", "mcp.json", "", str(OPENCODE_MCP), str(CLAUDE_MCP))
                    )
        else:
            changes.append(
                ("CONFLICT", "mcp.json", "", str(CLAUDE_MCP), str(OPENCODE_MCP))
            )
    return changes


# ─── MCP block update (--mcp-block) ──────────────────────────────────────


def strip_jsonc_comments(text):
    """Remove // and /* */ comments and trailing commas from JSONC text."""
    # Remove /* */ block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Remove // line comments (respecting strings)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        in_string = False
        escaped = False
        result = []
        i = 0
        while i < len(line):
            c = line[i]
            if escaped:
                result.append(c)
                escaped = False
            elif c == "\\":
                result.append(c)
                escaped = True
            elif c == '"':
                result.append(c)
                in_string = not in_string
            elif (
                c == "/"
                and i + 1 < len(line)
                and line[i + 1] == "/"
                and not in_string
            ):
                break
            else:
                result.append(c)
            i += 1
        cleaned.append("".join(result))
    text = "\n".join(cleaned)
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def update_mcp_block(dry_run):
    """Update the mcp section in opencode.jsonc for known servers."""
    changes = []
    if not CLAUDE_MCP.exists():
        print("  SKIP --mcp-block: ~/.claude/mcp.json not found")
        return changes

    try:
        mcp_data = json.loads(CLAUDE_MCP.read_text())
    except json.JSONDecodeError:
        print("  SKIP --mcp-block: invalid JSON in mcp.json")
        return changes

    servers = mcp_data.get("mcpServers", {})
    mcp_block = {}
    for server_name, server_config in servers.items():
        if server_name in KNOWN_MCP_SERVERS:
            mcp_block[server_name] = KNOWN_MCP_SERVERS[server_name]
            mcp_block[server_name]["enabled"] = True

    if not mcp_block:
        print("  SKIP --mcp-block: no known servers found in mcp.json")
        return changes

    # Read opencode.jsonc
    if OPENCODE_CONFIG.exists():
        raw = OPENCODE_CONFIG.read_text()
        stripped = strip_jsonc_comments(raw)
        try:
            config = json.loads(stripped)
        except json.JSONDecodeError:
            print("  SKIP --mcp-block: invalid JSON in opencode.jsonc")
            return changes
    else:
        config = {"$schema": "https://opencode.ai/config.json"}

    config["mcp"] = mcp_block
    new_text = json.dumps(config, indent=2, ensure_ascii=False) + "\n"

    if dry_run:
        print(f"  WOULD UPDATE mcp block in {OPENCODE_CONFIG}")
        print(f"    Servers: {list(mcp_block.keys())}")
    else:
        OPENCODE_CONFIG.write_text(new_text)
        print(f"  UPDATED mcp block in {OPENCODE_CONFIG}")
        print(f"    Servers: {list(mcp_block.keys())}")

    changes.append(("UPDATE", "opencode.jsonc mcp block", "", "", str(OPENCODE_CONFIG)))
    return changes


# ─── Summary printer ─────────────────────────────────────────────────────


def print_summary(changes):
    """Print a human-readable summary of sync actions."""
    if not changes:
        print("\n  Everything is already in sync. No changes needed.")
        return

    copies = [c for c in changes if c[0] == "COPY"]
    overwrites = [c for c in changes if c[0] == "OVERWRITE"]
    conflicts = [c for c in changes if c[0] == "CONFLICT"]
    updates = [c for c in changes if c[0] == "UPDATE"]

    print(f"\n  Summary: {len(changes)} action(s)")
    print(f"    Copies:     {len(copies)}")
    print(f"    Overwrites: {len(overwrites)}")
    print(f"    Conflicts:  {len(conflicts)}")
    print(f"    Updates:    {len(updates)}")

    if copies:
        print("\n  Copied:")
        for action, kind, name, src, dst in copies:
            label = f"{kind}/{name}" if name else kind
            print(f"    {label}")
            print(f"      {src}")
            print(f"      -> {dst}")

    if overwrites:
        print("\n  Overwritten:")
        for action, kind, name, src, dst in overwrites:
            label = f"{kind}/{name}" if name else kind
            print(f"    {label}")
            print(f"      {src}")
            print(f"      -> {dst}")

    if conflicts:
        print("\n  Conflicts (both sides differ, use --force to overwrite):")
        for action, kind, name, src, dst in conflicts:
            label = f"{kind}/{name}" if name else kind
            print(f"    {label}")
            print(f"      Claude:      {src}")
            print(f"      OpenCode:    {dst}")

    if updates:
        print("\n  Config updates:")
        for action, kind, name, src, dst in updates:
            print(f"    {kind} -> {dst}")


# ─── Main ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Sync skills, commands, and MCP config between Claude Code and opencode."
    )
    parser.add_argument(
        "direction",
        nargs="?",
        default="bidirectional",
        choices=["bidirectional", "to-opencode", "to-claude"],
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--force", action="store_true", help="Overwrite conflicts")
    parser.add_argument(
        "--mcp-block", action="store_true", help="Update mcp block in opencode.jsonc"
    )
    args = parser.parse_args()

    print(f"\n  Sync direction: {args.direction}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Force: {args.force}")
    print()

    all_changes = []
    all_changes += sync_skills(args.direction, args.force, args.dry_run)
    all_changes += sync_commands(args.direction, args.force, args.dry_run)
    all_changes += sync_mcp_json(args.direction, args.force, args.dry_run)

    if args.mcp_block:
        all_changes += update_mcp_block(args.dry_run)

    print_summary(all_changes)

    if any(c[0] == "CONFLICT" for c in all_changes):
        print("\n  NOTE: Conflicts found. Re-run with --force to overwrite,")
        print("  or specify a direction (to-opencode / to-claude) to avoid conflicts.")

    if not args.dry_run and any(c[0] != "CONFLICT" for c in all_changes):
        print("\n  Reminder: Restart opencode for changes to take effect.")

    print()


if __name__ == "__main__":
    main()
