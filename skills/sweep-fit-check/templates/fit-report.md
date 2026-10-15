# Fit check: {{slug}}

**Verdict: {{verdict}}**   (tenant: {{tenant}}, date: {{date}}, role: {{role}})

## Reachability
- Route: `{{route}}`
- Entry point mounted: {{entry_mounted}}
- Feature flags: {{ff}}
- Control flags: {{cf}} (not readable; `unknown` unless entry evidence)
- RBAC: group `{{rbac_group}}` = {{rbac_perm}}

## Side effects (listed, never invoked)
| Action | Reversible | Effect |
|---|---|---|

## Probes (GET only)
| Path | Status | Result |
|---|---|---|

## Cases
| ID | Status | Reason |
|---|---|---|

## Untested roles
{{untested_roles}}

## Decision needed
{{gate_question}}
