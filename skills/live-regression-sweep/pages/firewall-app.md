---
slug: firewall-app
title: App Definition > Cloud and Firewall Apps (Firewall App)
nav: Policies > App Definition > Cloud and Firewall Apps tab
route: "#/settings?view=manage_custom_apps"
session: lrs-fw
renderer_matrix:
  - renderer: angular
    when: "balkan_phase1_rc_custom_cloud_firewall_apps key absent in balkan_features_enabled AND nplan_4497_casbinline_enable_ngweb_customapps false"
    present: ["#public-app-rule-section", "ns-pagination-table[tableId=app_rules_list]", "#apply-changes"]
    absent: ["[data-testid=app-definition-search]", "[data-testid=public-app-rules-tab]"]
  - renderer: webui2-angular-element
    when: "rc flag on AND nplan_4497... false"
    present: ["[data-testid=public-app-rules-tab]"]
    absent: ["[data-testid=app-definition-search]"]
  - renderer: webui2-react
    when: "rc flag on AND nplan_4497_casbinline_enable_ngweb_customapps true"
    present: ["[data-testid=app-definition-search]", "[data-testid=new-app-btn]"]
    absent: ["#public-app-rule-section"]
flags:
  globals_regex: "cloud_firewall|casbinline|customapps|inline_policy_enh"
  balkan_keys: ["balkan_phase1_rc_custom_cloud_firewall_apps"]
rbac_mock:
  readonly: "Angular: POST /rbac_v3/getRoleFunctionPrivileges -> \"r\". React: GET /api/v2/rbac/roles/me apiGroup `custom_apps`."
  none: "same endpoints, empty"
api:
  - "Angular: POST /settings/manage_custom_apps/{getCustomAppsRules,saveCustomAppRule,deleteCustomAppRule,toggleCustomAppRule,revertCustomAppRule,applyChangesForCustomAppsRules}"
  - "React: /api/v2/services/casbinline/customapp/{getrules,rule,pendingchanges,deploy,steering}"
object_prefix: "e2e-fw-"
mutation:
  creates: true
  cleanup: "Row Revert / revert API for every own rule (including the custom app created before the rule is saved). Verify no `e2e-fw-` item in list, Manage Custom Apps and Pending Changes."
apply_policy: none
open_questions:
  - "Does casbinline (React path) enforce the same delete referrers as PHP (Bandwidth traffic class rule, Endpoint Content Control policy)?"
last_verified: 2026-10-07
---

# Firewall App (App Definition)

There is no separate Firewall App sub-tab: Firewall is a creation type ("New App Definition Rule" dropdown) and a
row Type. Tab title: "Cloud & Firewall Apps" when `cloud_firewall` AND `inline_policy_enhancements_enabled`, else
"Cloud Apps". Other agents on the same shared account may leave their own pending rules; do not touch them.
Angular save sends `app_type="Firewall App"` (not `tuple_rule`). `getCustomAppsRules` ignores limit/offset/searchStr/sortBy
and returns the whole list; search/sort/paging are client-side.

## Cases

| ID | Title | Pri | Mutates | Baseline (qa.de 2026-10-07) |
|---|---|---|---|---|
| FW-01 | Renderer gate, tab title, add-dropdown options | P0 | N | Angular; "Cloud & Firewall Apps"; both options |
| FW-02 | List load: Type column, pending triangle, single getCustomAppsRules call | P0 | N | PASS |
| FW-03 | Create Firewall App (dst IP + TCP 443); row pending | P0 | Y | PASS |
| FW-04 | Create Cloud App | P1 | Y | PASS; custom app is created BEFORE rule validation and is not pending |
| FW-05 | Edit rule (name locked, rule_id sent) | P0 | Y | PASS |
| FW-06 | Field validation (empty, duplicate, 127 chars, port 99999, `a-b`, bad IP) | P1 | Y | 127 chars -> "Not a valid Application name…"; 60 chars OK; protocol None / IP 256 N-A (options: TCP, UDP, TCP/UDP, ICMP) |
| FW-07 | Search by name and definition; no-match; clear; no new request | P1 | N | PASS (client-side) |
| FW-08 | Sort Last Modified + page size | P1 | N | FAIL: header click does nothing; order stays by Rule ID |
| FW-09 | Delete -> struck-through Deleted pending; Revert restores | P0 | Y | PASS |
| FW-10 | Bulk select/Delete; select-all; enable/disable | P1 | Y | PARTIAL: no per-row toggle or bulk Disable (N-A); exclusive=true untested |
| FW-11 | Pending changes modal; Apply visible, NOT clicked | P1 | Y | PASS |
| FW-12 | Delete-in-use | P1 | Y | BLOCKED: no referenced existing object |
| FW-13 | RBAC read-only (mock rbac_v3) | P0 | N | FAIL: New App Definition Rule stays enabled; dialog opens without Save |
| FW-14 | Mock list 500 | P1 | N | two identical toasts + empty list that looks like "no rules" |
| FW-15 | Observations: console, double fetch | P2 | N | |
