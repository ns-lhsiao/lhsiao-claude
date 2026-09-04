#!/usr/bin/env python3
"""
sumo_cost_audit.py -- on-demand real-dollar audit of Sumo search spend.

Queries the Sumo usage view (_view=sumologic_search_usage_per_query) for a
user and time range and reports real dollars per query -- the number the
sumo-query budget ledger can only estimate. Pulled on demand, never on a
schedule.

This is a DISTINCT skill from sumo-query. It does NOT route through
sumo_search.py (whose gate requires an allowlisted --cluster or explicit
_index=) because usage-audit queries target a metadata _view, not a cluster
debug index. No _view exemption is added to sumo_search.py to accommodate it.

Reads credentials from ~/.claude/connections/sumo.json (the same file
sumo-query uses). Reads the sumo-query ledger at
~/.claude/state/sumo_query/ledger.json (read-only) to compute a calibration
factor; it never writes the ledger or sumo-query's config.

Usage:
  sumo_cost_audit.py --user mitchw@netskope.com --from 2026-07-28T00:00:00Z --to 2026-07-29T06:00:00Z
  sumo_cost_audit.py --user mitchw@netskope.com --days 1
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "connections" / "sumo.json"
LEDGER_PATH = (Path(os.environ.get("SUMO_LEDGER_DIR",
                        str(Path.home() / ".claude" / "state" / "sumo_query")))
               / "ledger.json")

# Sumo builtin usage view. The team's "Daily Search Cost over $100" alert
# queries this same view. If Sumo renames it, change this one constant.
USAGE_VIEW = "sumologic_search_usage_per_query"

# Alert's own arithmetic: 0.0527 * 0.016 * (infrequent_bytes / 1Gi) = USD.
PER_GIB_RATE = 0.0527 * 0.016  # ~0.0008432 $/GiB scanned

POLL_INTERVAL_SECONDS = 2
JOB_TIMEOUT_SECONDS = 180  # usage views can be slower than a single index

# Usage data lags: the 2026-07-29 spend surfaced in the 06:08 alert the next
# morning. Warn when the requested range touches the last few hours.
LAG_WARN_HOURS = 6


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config():
    env_id = os.environ.get("SUMO_ACCESS_ID")
    env_key = os.environ.get("SUMO_ACCESS_KEY")
    env_url = os.environ.get("SUMO_API_URL", "https://api.sumologic.com")
    if env_id and env_key:
        return {"access_id": env_id, "access_key": env_key, "api_url": env_url}
    if not CONFIG_PATH.exists():
        die(
            f"config not found at {CONFIG_PATH}.\n"
            f"  sumo-cost-audit uses the same credentials as sumo-query. "
            f"Create ~/.claude/connections/sumo.json with access_id/access_key, "
            f"or set SUMO_ACCESS_ID / SUMO_ACCESS_KEY env vars."
        )
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        die(f"sumo.json is not valid JSON: {e}")
    for k in ("access_id", "access_key"):
        if not cfg.get(k):
            die(f"sumo.json missing {k!r}")
    cfg.setdefault("api_url", "https://api.sumologic.com")
    return cfg


def http_request(method, url, headers, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            cookies = resp.headers.get_all("Set-Cookie") or []
            if not raw:
                return {}, cookies
            return json.loads(raw), cookies
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code == 401:
            die("401 Unauthorized -- check SUMO_ACCESS_ID/KEY in ~/.claude/connections/sumo.json")
        if e.code == 429:
            die("429 rate-limited by Sumo. Wait a bit and retry.")
        die(f"HTTP {e.code} from {url}: {body_text[:500]}")
    except urllib.error.URLError as e:
        die(f"network error calling {url}: {e}")


def run_job(cfg, query, frm, to, limit):
    """Create a Sumo search job, poll to completion, fetch messages. Same API
    as sumo_search.py but with no cluster/_index gate -- the query targets a
    _view."""
    token = base64.b64encode(f'{cfg["access_id"]}:{cfg["access_key"]}'.encode()).decode()
    base = cfg["api_url"].rstrip("/")
    auth = f"Basic {token}"
    strip = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"[audit] view query: {query[:120]}...", file=sys.stderr)
    print(f"[audit] from: {frm.isoformat()}  to: {to.isoformat()}", file=sys.stderr)

    created, cookies = http_request("POST", f"{base}/api/v1/search/jobs",
        {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"},
        {"query": query, "from": strip(frm), "to": strip(to), "timeZone": "UTC"})
    job_id = created.get("id")
    if not job_id:
        die(f"search job create returned no id: {created}")
    cookie_header = "; ".join(c.split(";", 1)[0] for c in cookies) if cookies else ""
    print(f"[audit] job created: {job_id}", file=sys.stderr)

    poll = {"Authorization": auth, "Accept": "application/json"}
    if cookie_header:
        poll["Cookie"] = cookie_header
    start = time.time()
    status = None
    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        status, _ = http_request("GET", f"{base}/api/v1/search/jobs/{job_id}", poll)
        state = status.get("state")
        if state in ("DONE GATHERING RESULTS", "FORCE PAUSED", "CANCELLED"):
            break
        if time.time() - start > JOB_TIMEOUT_SECONDS:
            try:
                http_request("DELETE", f"{base}/api/v1/search/jobs/{job_id}", poll)
            except SystemExit:
                pass
            die(f"job timed out after {JOB_TIMEOUT_SECONDS}s (last state={state})")

    msg_count = status.get("messageCount", 0)
    print(f"[audit] state={status.get('state')} messages={msg_count}", file=sys.stderr)

    messages = []
    fetch = min(msg_count, limit)
    if fetch > 0:
        url = f"{base}/api/v1/search/jobs/{job_id}/messages?offset=0&limit={fetch}"
        result, _ = http_request("GET", url, poll)
        messages = [m.get("map", {}) for m in result.get("messages", [])]
    try:
        http_request("DELETE", f"{base}/api/v1/search/jobs/{job_id}", poll)
    except SystemExit:
        pass
    return messages


def parse_infrequent_bytes(msg):
    """Infrequent-tier scanned bytes for one usage row.

    The audit query extracts this server-side via
    `| json field=scanned_bytes_breakdown "Infrequent" as infre_scanned_bytes`,
    and the trailing `| fields ...` projection keeps only that extracted
    field (the raw scanned_bytes_breakdown is dropped). So read the extracted
    field first, fall back to data_scanned_bytes (equal to the Infrequent
    value on Infrequent-tier rows, which the query filters to), and only then
    try re-parsing the raw breakdown (present when no | fields projection).
    """
    v = msg.get("infre_scanned_bytes")
    if v not in (None, "", 0, "0"):
        return float(v)
    v = msg.get("data_scanned_bytes")
    if v not in (None, "", 0, "0"):
        return float(v)
    raw = msg.get("scanned_bytes_breakdown")
    if not raw:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
        return float(obj.get("Infrequent", 0) or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def to_usd(infrequent_bytes):
    return PER_GIB_RATE * (infrequent_bytes / (1 << 30))


def query_text(msg):
    """Best-effort extraction of the searched query string from a usage row."""
    for k in ("query", "query_string", "queryString", "search_query"):
        v = msg.get(k)
        if v:
            return v
    return msg.get("_raw", "")


def row_timestamp(msg):
    ts = msg.get("_messagetime") or msg.get("_receipttime")
    if ts:
        try:
            return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None


def sum_ledger_window_minutes(start_date, end_date):
    """Read-only sum of proxy_window_minutes over ledger entries whose
    local_date falls in [start_date, end_date] (YYYY-MM-DD). Returns 0 if the
    ledger is absent or has no overlapping entries."""
    if not LEDGER_PATH.exists():
        return 0
    try:
        data = json.loads(LEDGER_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    total = 0
    for e in data.get("entries", []):
        d = e.get("local_date", "")
        if start_date <= d <= end_date:
            total += e.get("proxy_window_minutes", 0)
    return total


def main():
    p = argparse.ArgumentParser(
        description="Audit real Sumo search spend from the usage view (on demand).")
    p.add_argument("--user", default=None,
                   help="Email to filter on (user_name field). Default: your own email from user_email "
                        "in sumo.json. Pass 'all' ONLY when team-wide spend is explicitly wanted "
                        "(matches the team alert; no calibration factor in that mode).")
    p.add_argument("--from", dest="from_", default=None,
                   help="ISO 8601 start (UTC). Required unless --days is given.")
    p.add_argument("--to", dest="to", default=None,
                   help="ISO 8601 end (UTC). Defaults to now.")
    p.add_argument("--days", type=float, default=None,
                   help="Shortcut: last N days from now (use instead of --from).")
    p.add_argument("--limit", type=int, default=500,
                   help="Max usage rows to fetch (default 500).")
    p.add_argument("--format", choices=("pretty", "json"), default="pretty")
    args = p.parse_args()

    cfg = load_config()
    # Default scope is the caller's OWN spend. --user all is opt-in only.
    user = args.user or cfg.get("user_email")
    if not user:
        die(
            "No --user given and no user_email in ~/.claude/connections/sumo.json.\n"
            "  Set it once so audits default to your own spend:\n"
            '    python3 -c "import json,os; p=os.path.expanduser(\'~/.claude/connections/sumo.json\'); '
            "d=json.load(open(p)); d['user_email']='<you>@netskope.com'; json.dump(d, open(p,'w'), indent=2)\"\n"
            "  Or pass --user <email> explicitly. Use --user all ONLY when team-wide spend is explicitly wanted."
        )

    now = datetime.now(timezone.utc)
    if args.days is not None:
        frm = now - timedelta(days=args.days)
        to = parse_iso(args.to) if args.to else now
    elif args.from_:
        frm = parse_iso(args.from_)
        to = parse_iso(args.to) if args.to else now
    else:
        die("provide --from (with optional --to) or --days N.")

    # Lag warning: usage data lags by hours; the 2026-07-29 spend surfaced
    # the next morning. Warn when the range touches the recent window.
    if (now - to).total_seconds() < LAG_WARN_HOURS * 3600:
        print(
            f"[audit] WARNING: the range ends within the last {LAG_WARN_HOURS}h. "
            f"Usage data lags (the 2026-07-29 spend surfaced at 06:08 the next "
            f"morning), so recent costs may be incomplete.",
            file=sys.stderr,
        )

    where_user = "" if user.lower() == "all" else f'| where user_name = "{user}"'
    # Filter to "Infrequent" (not merely != "Continuous"): the cost arithmetic
    # below (0.0527*0.016 * infrequent_bytes) and parse_infrequent_bytes() are
    # specific to the Infrequent tier. Excluding only "Continuous" left any
    # other tier's rows in the result with inconsistent cost math.
    query = (
        f"_view={USAGE_VIEW}\n"
        f'| where analytics_tier = "Infrequent"\n'
        f"{where_user}\n"
        f"| json field=scanned_bytes_breakdown \"Infrequent\" as infre_scanned_bytes\n"
        f"| 0.0527*0.016*(infre_scanned_bytes/1Gi) as usd\n"
        f"| sort by usd desc\n"
        f"| fields _messagetime, usd, query, user_name, infre_scanned_bytes, analytics_tier"
    )

    messages = run_job(cfg, query, frm, to, args.limit)

    rows = []
    total_usd = 0.0
    for m in messages:
        bytes_ = parse_infrequent_bytes(m)
        usd = to_usd(bytes_)
        total_usd += usd
        rows.append({
            "ts": (row_timestamp(m) or datetime.min).isoformat(),
            "usd": round(usd, 2),
            "user": m.get("user_name", ""),
            "query": (query_text(m) or "")[:200],
            "infrequent_gib": round(bytes_ / (1 << 30), 2),
        })
    rows.sort(key=lambda r: r["usd"], reverse=True)

    # Calibration factor: real dollars / ledger window-minutes over the range.
    # Only meaningful for a SINGLE-user audit: the ledger records only this
    # machine's sumo_search.py runs, so a team-wide (--user all) numerator
    # divided by a one-user denominator is apples-to-oranges and would emit a
    # meaningless factor (e.g. $122 team-wide / 10 ledger window-min).
    start_local = frm.astimezone().strftime("%Y-%m-%d")
    end_local = to.astimezone().strftime("%Y-%m-%d")
    is_all = user.lower() == "all"
    ledger_wm = sum_ledger_window_minutes(start_local, end_local)
    calibration = None
    if not is_all and ledger_wm > 0:
        calibration = total_usd / ledger_wm

    if args.format == "json":
        out = {
            "user": user, "from": frm.isoformat(), "to": to.isoformat(),
            "total_usd": round(total_usd, 2), "rows": rows,
            "ledger_window_minutes": ledger_wm if not is_all else None,
            "calibration_usd_per_window_minute": (
                round(calibration, 6) if calibration is not None else None),
        }
        print(json.dumps(out, indent=2, default=str))
        return

    # pretty
    print(f"\n=== Sumo spend: {user} | {frm.isoformat()} .. {to.isoformat()} ===")
    print(f"Total: ${total_usd:.2f}  ({len(rows)} queries, top {args.limit} shown)\n")
    if not rows:
        print("(no usage rows in range)")
    else:
        print(f"{'#':>3}  {'USD':>8}  {'GiB':>8}  {'time':<21}  query")
        for i, r in enumerate(rows, 1):
            q = r["query"].replace("\n", " ")
            if len(q) > 80:
                q = q[:80] + "..."
            print(f"{i:>3}  ${r['usd']:>7.2f}  {r['infrequent_gib']:>7.2f}  {r['ts'][:21]:<21}  {q}")
    print()
    if is_all:
        print("Calibration: not computed for a team-wide (--user all) audit.")
        print("  The ledger records only this machine's sumo_search.py runs, so a")
        print("  team-wide numerator / one-user denominator would be meaningless.")
        print("  Re-run with --user <your-email> to get a calibration factor.")
    elif ledger_wm > 0:
        print(f"Calibration: ${total_usd:.2f} / {ledger_wm} ledger window-minutes "
              f"= ${calibration:.4f}/window-minute")
        print(f"  -> set this as `rate` in ~/.claude/connections/sumo.json "
              f"(or pass --rate to sumo_search.py) to correct the proxy.")
    else:
        print(f"Ledger: no sumo-query entries overlap {start_local}..{end_local}; "
              f"no calibration factor computed.")
        print(f"  (Real costs above are still accurate; the proxy rate stays at "
              f"its default until the ledger has overlapping data.)")


def parse_iso(s):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        die(f"could not parse time {s!r}: {e}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
