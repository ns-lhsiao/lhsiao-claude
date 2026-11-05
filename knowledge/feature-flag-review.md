# Global Feature Flag Rollout Review

Source: Confluence "Global Feature Flag Rollouts" (DEV space). Process gate for any GLOBAL rollout — provisioner flags, architectural cutovers (VM→k8s, LB swap, private→public cloud), global Ursa flag rollouts. Cross-reference: [cm-rollouts.md](cm-rollouts.md) for CM ticket mechanics, deployment windows table, SOP bulk scripts.

## Do's and Don'ts

1. **Scope understood first** — when does the feature take effect (client restart? delayed? immediate?)? Can rollout + verification + rollback fit inside one maintenance window?
2. **Support/customer awareness** — CMs planned well in advance so notifications go out on time. Skipping notifications must be a collective ENG + Support decision, not unilateral.
3. **Validate health, not just enablement** — do NOT stop at `"status": "success"`. Need: (a) enablement signal (service metric), (b) new traffic to nearby services (e.g. extra mariadb calls per user, new events to eventforwarder), (c) existing-functionality checks (e.g. running PDVs).
   - Cautionary tale: IMF-1271 — Tier1/2 LB cutover caused outage because traffic increase to one component was underestimated.
4. **Soak period** — after first 1–2 MPs, monitor ≥1 business day of traffic before proceeding to remaining MPs. Rules out capacity problems.
5. **Maintenance windows** — global enablements only inside the POP's allowed window. **1 CM per window** — never an umbrella CM spanning multiple days/MPs/regions.
   - Cautionary tale: IMF-1271 — flag enabled during business hours, all MPs at once.
   - Gatekeeper reference: https://gatekeeper.netskope.io/rules/maintenance-windows
6. **Capture original state** — CM comments record: pre-change state, script output, validations (dashboards, PDVs).
   - Cautionary tale: EIMF-154 — rollback impossible to do cleanly because X tenants already had the flag and needed it, but the CM had blanketed Y tenants and nobody recorded which subset was newly enabled. Revert had to target Y−X only.

## Review workflow

```
Team prepares flag for global enable
  → primary ticket + linked CMs
  → submit plan to #global-feature-flag-rollout-review (SRE + Support)
  → SRE review + sign-off [SLA: 3 days]
  → Support review + sign-off [SLA: TBD], customer notifications published
  → CMs applied in batches
```

- **SLA: 3 days** for review/sign-off — plan rollouts with that lead time.
- Contact: #global-feature-flag-rollout-review for ENG/SRE/Support questions.
- Provisioner-specific execution rules (correct provisioner host, which provisioner-pycore service to use/avoid, cache-skip to reduce side effects, rate-limit intervals): Confluence "How to add Feature Flag | Feature flag Bulk Enablement (WIP)".
