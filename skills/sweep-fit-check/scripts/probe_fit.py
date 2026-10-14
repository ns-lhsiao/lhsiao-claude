#!/usr/bin/env python3
"""sweep-fit-check probe: read-only applicability analysis of a page on a real tenant.

Only GET requests are issued. The session cookie header is read from a file (never argv)
and is never written to any output. Any unexpected failure yields verdict STOP.

Usage:
  probe_fit.py --tenant https://x.example --cookie-file /tmp/claude/c.txt --out-dir DIR \
               [--page-file pages/x.md | --slug x --route '#/x'] [--entry-mounted true|false|unknown]
"""
import argparse
import datetime
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

STALE_DAYS = 60
STATUS_RANK = {"GO": 0, "GO-WITH-LIMITS": 1, "STOP": 2}


def load_page(path):
    """Return (frontmatter dict, markdown body). PyYAML is required for the frontmatter."""
    import yaml  # noqa: PLC0415

    text = Path(path).read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError(f"{path}: no YAML frontmatter")
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def case_table(body):
    """Parse the `## Cases` markdown table into [{id,title,pri,mutates}]."""
    cases = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and re.match(r"^[A-Z]{2,}-\d+", cells[0]):
            cases.append({"id": cells[0], "title": cells[1], "pri": cells[2], "mutates": cells[3].upper().startswith("Y")})
    return cases


class Client:
    def __init__(self, tenant, cookie):
        self.tenant = tenant.rstrip("/")
        self.cookie = cookie
        self.ctx = ssl.create_default_context()

    def get(self, path):
        """GET only. Returns (status, parsed_json_or_None, text_head)."""
        req = urllib.request.Request(self.tenant + path, method="GET", headers={"Cookie": self.cookie})
        try:
            with urllib.request.urlopen(req, timeout=40, context=self.ctx) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        text = raw.decode("utf-8", "replace")
        try:
            return status, json.loads(text), text[:200]
        except ValueError:
            return status, None, text[:200]


def classify(status, body, expect):
    """Probe result. Error-shaped 200 (success:false or missing data) is an error, not reachable."""
    if expect.get("status") is not None:
        ok = status == expect["status"]
        return ("ok" if ok else "error", f"expected {expect['status']}, got {status}")
    if status != 200:
        return "error", f"HTTP {status}"
    if expect.get("envelope", True) and isinstance(body, dict):
        if body.get("success") is False:
            return "error", "200 with success:false"
        if "data" not in body:
            return "error", "200 without data key"
    return "ok", "200"


def ff_value(client, name):
    status, body, _ = client.get(f"/api/v2/ui/platform/featureflags/{name}")
    if status == 200 and isinstance(body, dict):
        return str(body.get("var_value"))
    return f"unreadable(HTTP {status})"


def run(args):
    fm, body = ({}, "")
    page_exists = bool(args.page_file and Path(args.page_file).exists())
    if page_exists:
        fm, body = load_page(args.page_file)
    slug = fm.get("slug") or args.slug or "unknown"
    route = fm.get("route") or args.route or ""
    cookie = Path(args.cookie_file).read_text().strip()
    client = Client(args.tenant, cookie)
    notes = []

    # RBAC: role name + required api group permission
    status, roles, _ = client.get("/api/v2/rbac/roles/me")
    if status in (401, 403) and not isinstance(roles, dict):
        raise RuntimeError(f"session invalid or expired (HTTP {status} on roles/me); re-login and re-export the cookie")
    session_role = roles.get("roleName") if status == 200 and isinstance(roles, dict) else None
    groups = {g["apiGroupName"]: g["permission"] for g in (roles or {}).get("apiGroups", [])} if session_role else {}
    rbac_group = fm.get("rbac_group")
    rbac = {"group": rbac_group, "perm": groups.get(rbac_group) if rbac_group else None, "role": session_role}

    # Flags: FF read from API; CF reported unknown unless entry evidence supplied
    ff = {n: ff_value(client, n) for n in fm.get("ff", [])}
    entry = args.entry_mounted
    cf = {n: ("unknown" if entry == "unknown" else ("evidence:mounted" if entry == "true" else "evidence:not-mounted")) for n in fm.get("cf", [])}

    # Probes (GET only)
    probes = []
    for p in fm.get("probes", []):
        spec = p if isinstance(p, dict) else {"path": p}
        expect = {"path": spec["path"], **(spec.get("expect") or {})}
        st, js, head = client.get(expect["path"])
        result, why = classify(st, js, expect)
        probes.append({"path": expect["path"], "status": st, "result": result, "why": why})

    # Cases
    cases = case_table(body)
    blocked = fm.get("blocked_cases", {}) or {}
    needs_design = fm.get("needs_design", {}) or {}
    case_roles = fm.get("case_roles", {}) or {}
    ff_off = [n for n, v in ff.items() if v in ("0", "None", "false", "False", "")]
    unreachable = bool(ff_off) or (rbac_group and rbac["perm"] is None) or entry == "false" or any(
        p["result"] == "error" and p["path"] in set(fm.get("critical_probes", [])) for p in probes
    )
    case_status, untested = {}, set()
    for c in cases:
        cid = c["id"]
        if unreachable:
            case_status[cid] = "BLOCKED:renderer-or-access-unreachable"
        elif cid in blocked:
            case_status[cid] = f"BLOCKED:{blocked[cid]}"
        elif cid in needs_design:
            case_status[cid] = "NEEDS-DESIGN"
        elif case_roles.get(cid) and case_roles[cid] != session_role:
            case_status[cid] = f"BLOCKED:untested-role:{case_roles[cid]}"
            untested.add(case_roles[cid])
        else:
            case_status[cid] = "RUNNABLE"

    side_effects = fm.get("side_effects", []) or []

    # Differences between the page file and what the tenant shows (drives the draft)
    differences = [f"probe {p['path']}: {p['why']}" for p in probes if p["result"] == "error"]
    if rbac_group and rbac["perm"] is None:
        differences.append(f"rbac group {rbac_group} absent for role {session_role}")
    differences += [f"flag {n} unreadable or off ({v})" for n, v in ff.items() if v.startswith("unreadable") or n in ff_off]

    # Verdict
    limited = any(v != "RUNNABLE" for v in case_status.values()) or untested or not page_exists
    if unreachable:
        verdict = "STOP"
    elif limited:
        verdict = "GO-WITH-LIMITS"
    else:
        verdict = "GO"
    if not page_exists:
        notes.append("no page file: draft generated, cases unknown")

    # last_verified staleness
    lv = fm.get("last_verified")
    skip = False
    if lv:
        age = (datetime.date.today() - datetime.date.fromisoformat(str(lv))).days
        skip = age <= STALE_DAYS and not unreachable
        notes.append(f"last_verified {lv} ({age}d)")

    return {
        "target": {"kind": fm.get("kind", "unknown"), "route": route, "slug": slug},
        "renderer": {"entry_mounted": entry, "reachable": not unreachable, "blockers": ff_off},
        "access": {"ff": ff, "cf": cf, "rbac": rbac},
        "probes": probes,
        "side_effects": side_effects,
        "cases": case_status,
        "untested_roles": sorted(untested),
        "verdict": verdict,
        "fresh_page_file": skip,
        "page_exists": page_exists,
        "differences": differences,
        "notes": notes,
    }


def write_outputs(result, out_dir, page_file, slug):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    lines = [f"# Fit check: {result['target']['slug']}", "", f"**Verdict: {result['verdict']}**", ""]
    lines += [f"- Route: `{result['target']['route']}`", f"- Entry mounted: {result['renderer']['entry_mounted']}",
              f"- FF: {result['access']['ff']}", f"- CF: {result['access']['cf']}",
              f"- RBAC: {result['access']['rbac']}", f"- Untested roles: {result['untested_roles']}", ""]
    lines += ["## Side effects", ""] + [f"- {s}" for s in result["side_effects"]] + [""]
    lines += ["## Probes", ""] + [f"- `{p['path']}` -> {p['result']} ({p['why']})" for p in result["probes"]] + [""]
    lines += ["## Cases", ""] + [f"- {k}: {v}" for k, v in result["cases"].items()] + [""]
    lines += ["## Differences vs page file", ""] + [f"- {d}" for d in result.get("differences", [])] + [""]
    lines += ["## Notes", ""] + [f"- {n}" for n in result["notes"]]
    (out / "fit-report.md").write_text("\n".join(lines) + "\n")

    # Draft page file: only when no page file exists, or when the tenant differs from it.
    # Never overwrite an existing page file; the draft goes beside it as <slug>.draft.md.
    exists = result.get("page_exists", False)
    if exists and not result.get("differences"):
        return
    if exists:
        draft = Path(page_file).with_suffix(".draft.md")
    else:
        draft = out / f"{slug}.draft.md"
    draft.write_text(
        f"---\nslug: {slug}\nroute: \"{result['target']['route']}\"\nkind: {result['target']['kind']}\n"
        f"ff: {list(result['access']['ff'])}\ncf: {list(result['access']['cf'])}\n"
        f"rbac_group: {result['access']['rbac'].get('group')}\nprobes: []\nside_effects: []\n"
        f"last_verified: {datetime.date.today().isoformat()}\n---\n\n# {slug}\n\n"
        + ("Differences vs page file:\n" + "\n".join(f"- {d}" for d in result["differences"]) + "\n\n" if exists else "")
        + "## Cases\n\n| ID | Title | Pri | Mutates | Baseline (last observed) | qe_ref |\n|---|---|---|---|---|---|\n"
    )
    result["page_draft"] = str(draft)
    (out / "fit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--cookie-file", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--page-file")
    ap.add_argument("--slug")
    ap.add_argument("--route")
    ap.add_argument("--entry-mounted", choices=["true", "false", "unknown"], default="unknown")
    args = ap.parse_args()
    try:
        result = run(args)
    except Exception as e:  # fail closed
        result = {"target": {"slug": args.slug or "unknown", "route": args.route or "", "kind": "unknown"},
                  "renderer": {"entry_mounted": args.entry_mounted, "reachable": False, "blockers": []},
                  "access": {"ff": {}, "cf": {}, "rbac": {}}, "probes": [], "side_effects": [], "cases": {},
                  "untested_roles": [], "verdict": "STOP", "fresh_page_file": False,
                  "notes": [f"probe failed: {type(e).__name__}: {e}"]}
    write_outputs(result, args.out_dir, args.page_file, result["target"]["slug"])
    print(json.dumps({"verdict": result["verdict"], "out": str(Path(args.out_dir) / "fit.json")}))
    sys.exit(0 if result["verdict"] != "STOP" else 2)


if __name__ == "__main__":
    main()
