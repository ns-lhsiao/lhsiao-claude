---
slug: network-profile
title: Network Location / Network Profile
nav: Policies > Profiles > Network
route: "#/profile-network-location"
session: lrs-net
renderer_matrix:
  - renderer: angular-legacy
    when: "network_locations_v2_enabled false"
    present: ["ns-network-location-page", "ns-pagination-table", "button 'New Network Location'"]
    absent: ["mf-cfw", "[data-testid=network-location-home-title]"]
  - renderer: react-mf-cfw
    when: "FF network_profile_enabled AND CF NETWORK_LOCATIONS_V2_ENABLED (isNetworkLocationsV2Enabled)"
    present: ["mf-cfw", "[data-testid=network-location-home-title]", "[data-testid=network-location-new-button]"]
    absent: ["ns-network-location-page"]
flags:
  globals_regex: "network_loc|network_profile"
  balkan_keys: []
rbac_mock:
  readonly: "Legacy: POST /rbac_v3/getRoleFunctionPrivileges {pagename:'Network Location'} -> \"r\" (roles/me has NO effect). React: roles/me group for profiles."
  none: "same endpoints, empty"
api:
  - "Legacy: POST /networkLocation/{readAllNetLocationObjs,createNetLocationObj,updateNetLocationObj,deleteNetLocationObj,uploadNetLocationCSV}; pending_changes/getPendingChanges"
  - "React: /api/v2/profiles/networks (403 'licensed feature' when FF off)"
object_prefix: "e2e-net-"
mutation:
  creates: true
  cleanup: "Legacy has NO revert. Delete in UI -> pending Deleted. Removing them requires Apply (see apply_policy)."
apply_policy: needs-apply-to-clean
open_questions:
  - "React variant: not testable until FF + CF are enabled on the tenant"
  - "Delete-in-use / integrity check (needs a referencing role, bandwidth rule, forward proxy...)"
last_verified: 2026-10-07
---

# Network Profile (dual-mount)

Legacy PHP validations: name trimmed, non-empty, <=255 chars, no control chars or `<` `>`; values are IPv4/IPv6,
CIDR, same-family ranges (NO FQDN); duplicate IPs deduped; uniqueness case-insensitive across live, pending and
buffered tables. v2 spec: name maxLength 100, duplicate -> 409, delete referenced -> 409.
No clone action, no search box in legacy; sort is ineffective.

## Cases

| ID | Title | Pri | Mutates | Baseline (qa.de 2026-10-07) |
|---|---|---|---|---|
| NP-00 | Renderer gate (legacy) + flag evidence; React BLOCKED note | P0 | N | Legacy; React BLOCKED (403 licensed feature) |
| NP-01 | List load: columns, pending markers, readAll status/count | P0 | N | PASS (76 incl. pending) |
| NP-02 | Create single IP, CIDR, range, IPv6; rows pending | P0 | Y | PASS |
| NP-03 | Value validation (999.x, /33, reversed range, FQDN, empty, dup IPs) | P0 | Y | FQDN rejected (UI + CSV); dup IPs silently deduped |
| NP-04 | Name validation (empty, 256, `<`/`>`, spaces, TAB) | P1 | Y | 256 and `<>` -> generic "Invalid parameters."; spaces trimmed; TAB -> space |
| NP-05 | Duplicate name exact + case variant (create and rename) | P0 | Y | case-insensitive; "Sorry, … already exists" |
| NP-06 | Edit value; rename | P0 | Y | PASS |
| NP-07 | Clone | P2 | Y | N-A: no clone action |
| NP-08 | Delete custom -> pending Deleted; pending-created delete behavior | P0 | Y | PASS; pending-created row shows Deleted, total unchanged |
| NP-09 | Delete-in-use | P1 | Y | BLOCKED: nothing references test profiles |
| NP-10 | Search/sort/pagination, empty state | P1 | N | PARTIAL: no search, sort ineffective |
| NP-11 | CSV upload dialog (tiny valid CSV of e2e-net names, clean up) | P2 | Y | PASS |
| NP-12 | Pending panel read-only; Apply visible (do not click inside the test) | P1 | N | PARTIAL: no revert |
| NP-13 | RBAC read-only via rbac_v3 mock | P0 | N | PASS (New disabled, Apply hidden, Delete icons gone) |
| NP-14 | Mock readAll 500 | P1 | N | looks identical to empty list; toast never auto-dismisses |
| NP-15 | Observations; compare v2 list vs legacy list | P2 | N | v2 403 -> not comparable |

## Cleanup note

The reference run needed an Apply to remove 9 test objects (76 -> 67). Follow SKILL.md "Apply policy": list pending
items and owners first, ask with explicit Apply/leave options, verify after re-login.
