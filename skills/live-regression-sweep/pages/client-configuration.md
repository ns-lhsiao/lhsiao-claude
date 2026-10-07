---
slug: client-configuration
title: Client Configuration
nav: Settings > Security Cloud Platform > Netskope Client > Client Configuration
route: "#/settings?view=clientConfiguration"
session: lrs-cc
renderer_matrix:
  - renderer: angular
    when: always (no MF; no webui2 variant found)
    present: ["#section_client_config", "#client-config-modal (after opening a config)"]
    absent: []
flags:
  globals_regex: "client_config|nplan3211|nplan4571|nplan6711|nplan6965|dynamic_steering|granular"
  balkan_keys: []
rbac_mock:
  readonly: "POST /rbac_v3/getRoleFunctionPrivileges -> \"r\" (page reads this, NOT /api/v2/rbac/roles/me). Hides New, row menus, drag handles."
  none: "same endpoint -> empty/denied string; tooltip 'You do not have permissions to view' and modal does not open"
api:
  - "POST settings/clientConfiguration/getOUClientList"
  - "POST settings/clientConfiguration/saveClientConfig / deleteClientConfig / moveClientConfig"
  - "POST /api/v2/users/getgroups, GET /api/v2/users/attributes/ou (pickers)"
object_prefix: "e2e-cc-"
mutation:
  creates: true
  cleanup: "Delete in UI (applies immediately, no pending). Verify with getOUClientList: only original configs remain and their modify_time is unchanged."
apply_policy: none
open_questions:
  - "Does moveClientConfig notify the provisioner (not read in code)?"
  - "Is stored value of Auto re-enable duration -5 accepted verbatim?"
last_verified: 2026-10-07
---

# Client Configuration (Angular only)

Source: `neo/src/app/pages/client-config-page/` (+ `config-modal/`), PHP
`controllers/settings/Clientconfiguration.php`, `models/Client_configuration_model.php`.
After save/delete the model calls the provisioner (`notifyProvisionerService`) and NPA
(`ClientConfigChange` via qdispatcher). On provisioner timeout the API still returns success
with `warning=provisioner_timeout`, so assert that warning is absent.
Deleting or reordering configs bumps `modify_time` of OTHER configs too (observed).

## Cases

| ID | Title | Pri | Mutates | Baseline (qa.de 2026-10-07) |
|---|---|---|---|---|
| CC-01 | Renderer gate + list load (default config last, priority order, getOUClientList status/count) | P0 | N | PASS |
| CC-02 | Search by name, no-match message, clear | P1 | N | PASS |
| CC-03 | Create config -> row appears with modify_time/modify_by | P0 | Y | PASS |
| CC-04 | Edit (toggle one option) persists after reopen; modify_time bumps | P0 | Y | PASS, bumps |
| CC-05 | NO-OP save: modify_time unchanged; no provisioner_timeout warning | P0 | Y | PASS: unchanged (1791343114) |
| CC-06 | Clone (prefill, name cleared) then save as new | P1 | Y | PASS |
| CC-07 | Delete via confirm modal; default config has no delete | P0 | Y | PASS; also bumps other config's modify_time |
| CC-08 | Modal tab switching; note which flag-gated tabs exist | P1 | N | 5 tabs; Traffic Steering, AI Security, On-Device Inference absent |
| CC-09 | Validation messages (empty name, name >64, no OU/group, uninstall pw <8/>16, numeric fields) | P1 | Y | name>64 and pw>16 server-only; -5 accepted for Auto re-enable duration |
| CC-10 | Reorder between two e2e configs; order persists | P1 | Y | PASS; bumps modify_time of both |
| CC-11 | Mock getOUClientList 500 | P1 | N | toast + blank area, no empty state/retry |
| CC-12 | RBAC read-only via rbac_v3 mock | P0 | N | PASS |
| CC-13 | Observations: console errors, stale toasts, layout | P2 | N | stale red toasts persist after later success |
