---
slug: service-profile
title: Service (service profiles)
nav: Policies > Profiles > Service
route: "#/service-profile"
session: lrs-svc
renderer_matrix:
  - renderer: react-mf-profiles
    when: "service_profile_v2_enabled true (CF SERVICE_PROFILE_V2_ENABLED AND FF)"
    present: ["mf-service-profile", "[data-testid=service-profiles-container]", "[data-testid=table_service-profile]"]
    absent: ["ns-pagination-table[tableId=service-profile-list]"]
  - renderer: angular-legacy
    when: "flag off — DEAD: PHP Service_profile controller deleted (ENG-916538), nothing serves /Service_profile/*. Do not test."
    present: []
    absent: []
flags:
  globals_regex: "service_profile|ssl_dnd_service"
  balkan_keys: []
rbac_mock:
  readonly: "GET /api/v2/rbac/roles/me with apiGroup `objects_service` read-only"
  none: "same endpoint -> {apiGroups: []} -> NotAuthorized page"
api:
  - "GET /api/v2/profiles/serviceobjects?filter&limit&offset&sortby&sortorder"
  - "POST /api/v2/profiles/serviceobjects?interactive=true; PATCH/DELETE .../{id}?interactive=true"
  - "POST .../serviceobjects/deploy?all=true (NEVER call), POST /pending_changes/sendForApproval (NEVER)"
object_prefix: "e2e-svc-"
mutation:
  creates: true
  cleanup: "Pending changes modal -> revert own items, or delete pending-created objects. Verify with list GET filtered by prefix: total unchanged, every item APPLIED, 0 pending."
apply_policy: none
open_questions:
  - "QOS service delete-in-use 409 text (needs a policy referencing a custom service)"
last_verified: 2026-10-07
---

# Service profile (React, mf-profiles)

Source: webui `neo/src/app/pages/service-profile/` (wrapper, remote `profiles`, `./ServiceProfile`);
React in mf-profiles `src/components/ServiceProfile/`. Predefined rows: only View + Clone enabled.
Stable testids: `table-actions-service-profile` (NEW SERVICE), `view|clone|edit|delete`,
`service-sidepanel-save-action`, `view-pending-changes-button`, `service-profile-table-name-<name>`.

## Cases

| ID | Title | Pri | Mutates | Baseline (qa.de 2026-10-07) |
|---|---|---|---|---|
| SV-01 | Renderer gate + nav shows only v2 entry; list GET status/sort | P0 | N | React mounted |
| SV-02 | List load; predefined rows only view+clone | P0 | N | PASS |
| SV-03 | Create custom `TCP 443, 8080-8090` -> POST status, row pending | P0 | Y | PASS |
| SV-04 | Port validation (0, 65536, `80-`, `90-80`, abc, ICMP+port, empty) | P0 | Y | Save never disabled; inline "Invalid port number/range" on click, no POST |
| SV-05 | Name validation (empty, >100, `<script>`) | P1 | Y | FAIL: 113 chars accepted (202); closing script tag left in stored name |
| SV-06 | Duplicate name exact + case variant | P1 | Y | 409 "The service object name 'X' conflicts with an existing service object."; case-insensitive; also vs pending |
| SV-07 | Edit custom service (PATCH) | P0 | Y | PASS |
| SV-08 | Clone custom + predefined | P1 | Y | PASS |
| SV-09 | Delete custom -> DELETE status; pending-created delete behavior | P0 | Y | PASS |
| SV-10 | Delete-in-use | P1 | Y | BLOCKED: needs deploy + policy reference |
| SV-11 | Search/filter by name and type, empty state | P1 | N | PASS |
| SV-12 | Sort + pagination request params | P1 | N | PASS |
| SV-13 | Pending changes modal: list own items, revert; Apply visible, NOT clicked | P1 | Y | PASS |
| SV-14 | RBAC read-only (mock) | P0 | N | FAIL: custom rows have no View action; New Service disabled with tooltip |
| SV-15 | RBAC none -> NotAuthorized | P1 | N | PASS |
| SV-16 | Mock list 500 | P1 | N | FAIL: shows "0 Services Found" empty state, no error |
| SV-17 | Observations: console errors | P2 | N | CSP inline-style, TypeError reading 'error' in MFE bundle, 404 on serviceProfile locale |
