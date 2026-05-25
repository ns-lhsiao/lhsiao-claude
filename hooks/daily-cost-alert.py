#!/usr/bin/env python3
"""UserPromptSubmit hook: warn once when today's spend crosses a threshold.

Walks every transcript under ~/.claude/projects/, sums today's assistant
usage blocks priced via the webui-insights pricing table, and if the
total >= COST_THRESHOLD prints a system-reminder. A sentinel file under
~/.claude/hooks/state/ ensures the warning fires at most once per local
calendar day.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

COST_THRESHOLD = float(os.environ.get("CLAUDE_COST_THRESHOLD", 200.0))
PRICING_PATH = Path(
    os.environ.get(
        "CLAUDE_PRICING_PATH",
        Path.home()
        / ".claude/plugins/cache/webui-claude-marketplace/webui-insights/0.4.3/config/config.json",
    )
)
PROJECTS_DIR = Path.home() / ".claude" / "projects"
STATE_DIR = Path.home() / ".claude" / "hooks" / "state"

DEFAULT_PRICING = {
    "claude-opus-4-7":   {"input": 0.005, "output": 0.025, "cache_read": 0.0005, "cache_create": 0.00625},
    "claude-opus-4-6":   {"input": 0.005, "output": 0.025, "cache_read": 0.0005, "cache_create": 0.00625},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015, "cache_read": 0.0003, "cache_create": 0.00375},
    "claude-haiku-4-5":  {"input": 0.001, "output": 0.005, "cache_read": 0.0001, "cache_create": 0.00125},
}


def _load_pricing() -> dict:
    try:
        cfg = json.loads(PRICING_PATH.read_text())
        return cfg.get("model_pricing") or DEFAULT_PRICING
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return DEFAULT_PRICING


def _model_key(name: str | None, pricing: dict) -> str | None:
    if not name:
        return None
    if name in pricing:
        return name
    # Bedrock IDs look like "us.anthropic.claude-opus-4-7-v1:0" — strip prefix/suffix.
    stripped = name.split(".")[-1].split(":")[0]
    for variant in (stripped, stripped.rsplit("-v", 1)[0]):
        if variant in pricing:
            return variant
    return None


def _entry_cost(usage: dict, model_key: str, pricing: dict) -> float:
    rates = pricing[model_key]
    return (
        int(usage.get("input_tokens") or 0) * rates["input"]
        + int(usage.get("output_tokens") or 0) * rates["output"]
        + int(usage.get("cache_read_input_tokens") or 0) * rates["cache_read"]
        + int(usage.get("cache_creation_input_tokens") or 0) * rates["cache_create"]
    ) / 1000.0


def _today_total() -> float:
    pricing = _load_pricing()
    today = datetime.now().date()
    total = 0.0
    if not PROJECTS_DIR.is_dir():
        return 0.0
    for transcript in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(transcript.stat().st_mtime).date()
        except OSError:
            continue
        if mtime < today:
            continue
        try:
            with transcript.open() as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = entry.get("timestamp")
                    if not ts:
                        continue
                    try:
                        # ISO 8601 with Z; treat as UTC then convert to local.
                        when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
                    except ValueError:
                        continue
                    if when.date() != today:
                        continue
                    msg = entry.get("message") or {}
                    usage = msg.get("usage")
                    if not usage:
                        continue
                    key = _model_key(msg.get("model"), pricing)
                    if not key:
                        continue
                    total += _entry_cost(usage, key, pricing)
        except OSError:
            continue
    return total


def _already_alerted(today: str) -> bool:
    return (STATE_DIR / f"cost-alert-{today}").exists()


def _mark_alerted(today: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"cost-alert-{today}").touch()


def main() -> int:
    # Drain stdin so the parent doesn't block.
    try:
        sys.stdin.read()
    except Exception:
        pass

    today = datetime.now().date().isoformat()
    if _already_alerted(today):
        return 0

    spent = _today_total()
    if spent < COST_THRESHOLD:
        return 0

    _mark_alerted(today)
    print(
        f"<system-reminder>\n"
        f"Daily Claude spend has crossed the alert threshold: "
        f"${spent:,.2f} today (>= ${COST_THRESHOLD:,.0f}).\n"
        f"Consider pausing non-critical work, switching to Sonnet/Haiku for "
        f"lighter tasks, or running `/usage-report --period 1d` to see what's "
        f"driving cost. This warning fires once per calendar day.\n"
        f"</system-reminder>"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
