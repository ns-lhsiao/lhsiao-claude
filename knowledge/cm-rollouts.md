# CM Tickets & Feature Flag Rollouts

## MP Deployment Windows (from #deployment-windows bot, UTC)

Per-POP maintenance/deployment windows. CM execution must fall inside the POP's own window — regional "21:00–04:00 local" wording is NOT universally correct (MEL2 opens 22:00 local).

| POP | Window (UTC) | Local |
|-----|--------------|-------|
| sjc1, sjc2, sv5 | 04:00–12:00 | 20:00–04:00 PST |
| mel2 | 11:00–19:00 | 22:00–06:00 AEDT |
| sin2 | 13:00–21:00 | 21:00–05:00 SGT |
| bom3 | 15:30–23:30 | 21:00–05:00 IST |
| ruh1 | 18:00–02:00 | 21:00–05:00 AST |
| am2, zur2, fr4, fra2 | 19:00–03:00 | 20:00–04:00 CET |
| lon3 | 20:00–04:00 | 20:00–04:00 GMT |

- DFW3 not listed in the bot output — confirm its window separately before scheduling.
- Bot reports "Open now / Upcoming" live; the table above is the recurring schedule (verified 2026-11-03).

## Global Feature Flag Rollouts doc (hard rules)

Full review process (workflow, do's/don'ts, SLA, cautionary tales): [feature-flag-review.md](feature-flag-review.md). This section = hard rules only.

Confluence: "Global Feature Flag Rollouts" (DEV space). Reviewer enforcement observed on CM-350336 (2026-11-03):

- **1 CM per window** — umbrella CM spanning multiple days/MPs/regions is explicitly banned. Split by region (US/EU/APAC/MEA is the working pattern).
- **Soak period** — after first 1–2 MPs, monitor ≥1 business day before continuing.
- **Health validation beyond "status":"success"** — load the actual feature UI on sample tenants, watch error rates / new traffic to nearby services.
- **Workflow** — submit plan to #global-feature-flag-rollout-review (SRE + Support sign-off, SLA 3 days) BEFORE execution.
- **Capture original state** — pre-change outputs, script outputs, validations all go in CM comments (rollback may need "only newly-enabled tenants" subset).
- Provisioner-specific guidelines live in "How to add Feature Flag" page (provisioner host selection, rate limiting, cache-skip).

## Worked example: ng_devices_enabled batch enable (2026-11-03)

- Audit source: CM-346076 — `SELECT var_value FROM global_vars WHERE var_name = 'ng_devices_enabled' AND var_value = '0'` per tenant DB, 13 MPs, 1114 hits. Audit key IS the provisioner API key (same name); "read-device-disable" was just the audit comment's label.
- Umbrella CM-350336 created first, rejected on review → superseded by 4 regional CMs: CM-351435 (US, soak), CM-351436 (EU), CM-351437 (APAC), CM-351439 (MEA). All blocks ENG-1055073, relates CM-346076.
- SOP scripts ("SOP - Bulk Enable and Disable Feature Flags", page 4455334119): check_feature_flag.sh / enable_bulk_feature_flag.sh / disable_bulk_feature_flag.sh in `/bulk_feature_flags/` pod dir. **SOP's -t classification is STALE (SRE review 2026-11-03): ALL MPs including AM2/SV5/FR4 are k8s — use `-s` (provisioner-pycore-provisioner-tm port 80). `provisionervip:6400` is deprecated; audit pod logs prove SV5 runs a webui pod. Notify SOP owner.** Script template uses placeholder flag `on_prem_infra_qs_api_enabled` — string-replace with real flag. Skips already-set tenants, HTTP-code checks, success/fail summaries, sleep 5, `bump_client_config_version=0` + `background=0` for UI-only flags.
- SRE review gotchas (CM-351435 review, 2026-11-03): structured Requested Begin/End is what Gatekeeper checks — zero-length or business-hours values get flagged even when the outline text is compliant; keep them consistent with the outline dates. Customer Notification field: Yes(14750)/No(14751) — reviewer will demand 72h Support-notification evidence if Yes; set No with rationale when enablement just flips tenants to already-GA default. Reviewer wants: named dashboards/Sumo queries for health checks, abort criteria (30-min guardrail), rollback duration quantified, impact fields not one-word "no".
- Datacenter option IDs beyond the skill's references/datacenters.md: BOM3 = 58366 (Datacenters) / 58367 (Impacted). Find unknown options via JQL: `project = CM AND "Datacenters" = BOM3` then read the field's option id.
- Post-flip validation: re-run the audit query, expect 0 rows. Reviewer asked for this explicitly.
