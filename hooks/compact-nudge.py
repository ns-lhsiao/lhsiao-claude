#!/usr/bin/env python3
"""UserPromptSubmit hook: nudge to /compact when context >= 40% of cap.

Reads the current session's JSONL transcript, finds the most recent
assistant `usage` block, computes total context tokens (cache_read +
cache_creation + input), and if it crosses the threshold, prints a
system-reminder to stderr with a pre-filled `/compact "<task>"` line.

Stdout from a UserPromptSubmit hook is fed back to the model as
additional context, so the reminder lands in the very next turn.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CTX_LIMIT = int(os.environ.get("CLAUDE_CTX_LIMIT", 1_000_000))
THRESHOLD = float(os.environ.get("CLAUDE_COMPACT_THRESHOLD", 0.40))
PROJECTS_DIR = Path.home() / ".claude" / "projects"


def _read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _transcript_path(payload: dict) -> Path | None:
    explicit = payload.get("transcript_path")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    cwd = payload.get("cwd") or os.getcwd()
    slug = "-" + str(cwd).replace("/", "-").lstrip("-")
    project_dir = PROJECTS_DIR / slug
    if not project_dir.is_dir():
        return None
    candidates = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _last_usage(transcript: Path) -> dict | None:
    last = None
    with transcript.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = entry.get("message", {}).get("usage")
            if usage:
                last = usage
    return last


def _context_tokens(usage: dict) -> int:
    return (
        int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
        + int(usage.get("input_tokens") or 0)
    )


def _in_progress_task(transcript: Path) -> str | None:
    """Replay TaskCreate / TaskUpdate calls to find the active task."""
    tasks: dict[str, dict] = {}
    pending_create: str | None = None
    with transcript.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = entry.get("message", {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name")
                    if name == "TaskCreate":
                        pending_create = block.get("id")
                        tasks[pending_create] = {
                            "tool_use_id": block.get("id"),
                            "subject": block.get("input", {}).get("subject", ""),
                            "active_form": block.get("input", {}).get("activeForm", ""),
                            "status": "pending",
                            "task_id": None,
                        }
                    elif name == "TaskUpdate":
                        task_id = str(block.get("input", {}).get("taskId"))
                        status = block.get("input", {}).get("status")
                        for t in tasks.values():
                            if t.get("task_id") == task_id and status:
                                t["status"] = status
                elif btype == "tool_result" and pending_create:
                    text = block.get("content")
                    if isinstance(text, list):
                        text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
                    if isinstance(text, str) and "Task #" in text:
                        try:
                            num = text.split("Task #", 1)[1].split(" ", 1)[0]
                            tasks[pending_create]["task_id"] = num
                        except (IndexError, KeyError):
                            pass
                    pending_create = None
    for t in tasks.values():
        if t.get("status") == "in_progress":
            return t.get("active_form") or t.get("subject")
    for t in reversed(list(tasks.values())):
        if t.get("status") not in ("completed", "cancelled"):
            return t.get("active_form") or t.get("subject")
    return None


def _last_user_message(transcript: Path) -> str | None:
    last = None
    with transcript.open() as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "user":
                continue
            content = entry.get("message", {}).get("content")
            if isinstance(content, str):
                last = content
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "text" and b.get("text"):
                        last = b["text"]
    if not last:
        return None
    last = last.strip().splitlines()[0]
    return (last[:120] + "...") if len(last) > 120 else last


def main() -> int:
    payload = _read_payload()
    transcript = _transcript_path(payload)
    if not transcript:
        return 0
    usage = _last_usage(transcript)
    if not usage:
        return 0
    used = _context_tokens(usage)
    pct = used / CTX_LIMIT
    if pct < THRESHOLD:
        return 0

    task = _in_progress_task(transcript) or _last_user_message(transcript) or "current work"
    task_clean = task.replace('"', "'").strip()

    print(
        f"<system-reminder>\n"
        f"Context usage is at {pct:.0%} ({used:,} / {CTX_LIMIT:,} tokens), "
        f"past the {THRESHOLD:.0%} compact threshold.\n"
        f"Recommend running `/compact {task_clean}` before continuing so the "
        f"summary preserves the in-progress intent.\n"
        f"</system-reminder>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
