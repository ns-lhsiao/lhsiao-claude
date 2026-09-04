---
name: sumo-cost-audit
description: Audit your OWN real Sumo search spend on demand (defaults to your own email; use --user all ONLY when team-wide spend is explicitly asked). Use when a Sumo cost alert has landed (the "Daily Search Cost over $100" email), when the user asks "what did my Sumo searches cost on <date>" or "why did I spend $X on Sumo", or when calibrating the sumo-query budget proxy against real dollars. Reports per-query dollar cost from the Sumo usage view and a calibration factor for the sumo-query ledger (single-user audits only). Read-only -- never writes the ledger or sumo-query config. Do NOT use for live log searching (that is sumo-query); this reads billing metadata only.
---

# sumo-cost-audit

On-demand real-dollar audit of Sumo search spend. Answers "which queries, specifically, cost what?" -- the question the `sumo-query` budget ledger can only estimate, because the Sumo search-job API exposes no byte counters at run time. Real figures live in the Sumo usage view, with ingest lag.

## When to use

- A "Daily Search Cost over $100" alert email lands and you want to see which of your queries drove it.
- The user asks "what did I spend on Sumo yesterday / on 2026-07-29 / last Tuesday?"
- Calibrating the `sumo-query` proxy rate: run this over a range that overlaps the ledger, then apply the reported factor.

## When NOT to use

- Live log searching (errors, request-ids, cluster logs) -- that is `sumo-query`. This skill reads billing metadata, not debug logs.
- Scheduled / unattended spend detection -- the team's daily alert email already covers that. This skill is for the follow-up question, pulled when asked.

## Where the script lives

```bash
SCRIPT=$(ls \
  ~/.claude/skills/sumo-cost-audit/scripts/sumo_cost_audit.py \
  .claude/skills/sumo-cost-audit/scripts/sumo_cost_audit.py \
  2>/dev/null | head -1)
[ -z "$SCRIPT" ] && { echo "sumo-cost-audit skill not installed"; exit 1; }
```

## Usage

Default scope is your OWN spend. Only use `--user all` when the user explicitly asks for team-wide spend -- never default to `all` on your own.

```bash
# Your own spend on a specific past day
python3 "$SCRIPT" --user mitchw@netskope.com --from 2026-07-28T07:00:00Z --to 2026-07-29T13:00:00Z

# Your own spend, last 1 day
python3 "$SCRIPT" --user mitchw@netskope.com --days 1

# Team-wide (ONLY when the user explicitly asks -- matches the team alert)
python3 "$SCRIPT" --user all --days 1
```

Flags:
- `--user <email>` -- filter to one user (the `user_name` field). Default: `user_email` in `~/.claude/connections/sumo.json`. Set that once so audits default to your own spend without needing the flag. `all` is opt-in for team-wide spend only -- and in that mode no calibration factor is emitted (the ledger records only this machine's queries, so a team-wide numerator / one-user denominator would be meaningless).
- `--from` / `--to` -- ISO 8601 UTC range. `--to` defaults to now.
- `--days N` -- shortcut for `now-N days` to now, instead of `--from`.
- `--limit N` -- max usage rows to fetch (default 500, ranked by cost desc).
- `--format pretty|json` -- default `pretty` (ranked table); `json` for machine consumption.

## What it reports

- Per-query: timestamp, dollar cost, infrequent-tier GiB scanned, the query text, user. Ranked most expensive first.
- Total real dollars over the range.
- A **calibration factor**: `real_total_dollars / ledger_window_minutes` over the same range, read from `~/.claude/state/sumo_query/ledger.json`. Expressed in dollars-per-window-minute -- the same unit as `sumo-query`'s `rate` config.

## Calibration: turning the factor into a better proxy

The `sumo-query` ledger estimates cost as `cluster_count x window_minutes x rate`, with a default rate calibrated from a single 2026-07-29 datapoint (~$0.0023/window-minute). As index sizes drift, the estimate goes stale. This skill corrects it:

1. Run the audit over a range that overlaps ledger data: `python3 "$SCRIPT" --user <you> --days 7`
2. Read the reported `calibration_usd_per_window_minute` (e.g. `$0.0031/window-minute`)
3. Set it as the `rate` in `~/.claude/connections/sumo.json`:
   ```json
   { "access_id": "...", "access_key": "...", "rate": 0.0031 }
   ```
   Or pass `--rate 0.0031` to individual `sumo_search.py` calls.

When the ledger has no overlapping entries, the audit still reports real per-query costs but states that no calibration factor could be computed (never emits a factor from a zero or partial denominator).

## Ingest lag

Usage data lags. The 2026-07-29 spend surfaced in the 06:08 alert the following morning. The script warns when the requested range ends within the last 6 hours -- recent costs may be incomplete. For a full picture, audit a range that ended at least several hours ago.

## Credentials

Same as `sumo-query`: `~/.claude/connections/sumo.json` (or `SUMO_ACCESS_ID` / `SUMO_ACCESS_KEY` env vars). The script never bundles credentials.

## Separation from sumo-query

This skill is deliberately separate, not a `sumo-query` subcommand. `sumo-query`'s central invariant is that every search names an allowlisted cluster or an explicit `_index=`; a usage-audit query targets `_view=sumologic_search_usage_per_query` (a metadata view, no cluster), so routing it through `sumo_search.py` would mean punching a hole in the exact check that skill exists to enforce. This script issues its own search-job request and adds no `_view=` exemption to `sumo_search.py`. Because it reads only billing metadata, it is not subject to the window ladder, fan-out threshold, or budget ledger.

The view name (`USAGE_VIEW` in the script) is a single constant at the top -- if Sumo renames the builtin, change that one line.
