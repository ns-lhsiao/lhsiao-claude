#!/usr/bin/env python3
"""Diff two live-regression-sweep results directories.

Usage: diff_results.py <prev_results_dir> <curr_results_dir>

Each directory holds <slug>.json files shaped like:
  {"run": {...}, "cases": {"CC-01": {"result": "PASS", ...}, ...}}

Prints markdown: regressions (was PASS, now FAIL/PARTIAL), fixed (was FAIL/PARTIAL, now PASS),
still failing, new cases, and cases that disappeared. Exit code 1 if any regression exists.
"""
import json
import sys
from pathlib import Path

GOOD = {"PASS"}
BAD = {"FAIL", "PARTIAL"}


def load(d: Path) -> dict:
    out = {}
    for f in sorted(d.glob("*.json")):
        out[f.stem] = json.loads(f.read_text()).get("cases", {})
    return out


def res(c: dict) -> str:
    return str(c.get("result", "?")).upper()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    prev, curr = load(Path(sys.argv[1])), load(Path(sys.argv[2]))
    regress, fixed, still, new, gone = [], [], [], [], []
    for slug in sorted(set(prev) | set(curr)):
        p, c = prev.get(slug, {}), curr.get(slug, {})
        for cid in sorted(set(p) | set(c)):
            if cid not in p:
                new.append((slug, cid, res(c[cid])))
            elif cid not in c:
                gone.append((slug, cid, res(p[cid])))
            else:
                a, b = res(p[cid]), res(c[cid])
                if a in GOOD and b in BAD:
                    regress.append((slug, cid, f"{a} -> {b}"))
                elif a in BAD and b in GOOD:
                    fixed.append((slug, cid, f"{a} -> {b}"))
                elif a in BAD and b in BAD:
                    still.append((slug, cid, f"{a} -> {b}"))
    for title, rows in (
        ("Regressions", regress),
        ("Fixed", fixed),
        ("Still failing", still),
        ("New cases", new),
        ("Missing in this run", gone),
    ):
        print(f"## {title} ({len(rows)})")
        for slug, cid, what in rows:
            print(f"- {slug} {cid}: {what}")
        print()
    return 1 if regress else 0


if __name__ == "__main__":
    sys.exit(main())
