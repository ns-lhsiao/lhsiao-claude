---
slug: devices
title: Devices
nav: Settings > Security Cloud Platform > Netskope Client > Devices
route: "#/settings/device-management"
session: lrs-dev
renderer_matrix:
  - renderer: react-mf-client
    when: "ng_devices_enabled true (CF NG_DEVICES_ENABLED AND FF ng_devices_enabled)"
    present: ["<mf-client> element", "[data-testid=devices-header]", "[data-testid=devices-table]"]
    absent: ["section#devices-page"]
  - renderer: angular-legacy
    when: "ng_devices_enabled false"
    present: ["section#devices-page", "#devices-page-filter"]
    absent: ["<mf-client>"]
flags:
  globals_regex: "devices|unenroll"
  balkan_keys: []
rbac_mock:
  readonly: "GET /api/v2/rbac/roles/me with apiGroup `devices` read-only (register in the SAME run-code call as navigation)"
  none: "same endpoint -> {apiGroups: []} -> ForbiddenPage / 403 Not Authorized"
api:
  - "GET /api/v2/events/datasearch/clientstatus (list, detail, count, export with header x-netskope-sqs-tag: exportDeviceList)"
  - "GET /api/v2/events/datasearch/clientstatusevent"
  - "POST /api/v2/events/datasearch/delete/clientstatus"
  - "/api/v2/devices/device/tags*, /api/v2/platform/savedfilters, /api/v2/devices/support/*"
object_prefix: "(none: page is READ-ONLY, never mutate real devices)"
mutation:
  creates: false
  cleanup: "Nothing created. Column preferences DO persist per account; restore to the starting set at the end (Restore Default dropped Device Tags last run: 7 -> 6 columns)."
apply_policy: none
open_questions:
  - "Unenroll action: flag nplan4533_unenroll_devices_support is true but no menu entry found; extra gate?"
last_verified: 2026-10-07
---

# Devices (mf-client)

Source: webui wrapper `neo/src/app/pages/devices-page/` (`ns-ng-web-wrapper`, remote `client`,
module `./App`, element `mf-client`); React in the mf-client repo. Safety: open dialogs and cancel;
never confirm delete, enable/disable client, fail-close, logs, OTP, unenroll, or bulk apply.

## Cases

| ID | Title | Pri | Mutates | Baseline (qa.de 2026-10-07) |
|---|---|---|---|---|
| DV-01 | Renderer gate + list GET status, limit=20 | P0 | N | React mounted |
| DV-02 | List load: rows vs count call | P0 | N | PASS |
| DV-03 | Search/filter, saved filters presence, clear | P0 | N | PASS |
| DV-04 | Sort by column; note first-click direction | P1 | N | PASS |
| DV-05 | Pagination next/prev/page size | P1 | N | PARTIAL: tenant has 2 devices, offset not testable |
| DV-06 | Column customization persists across re-navigation | P2 | Y (pref) | Restore Default lost Device Tags |
| DV-07 | Row actions menu; view-details panel; event history | P0 | N | PASS |
| DV-08 | Bulk selection menu, manage-tags entry, cancel | P0 | N | PASS |
| DV-09 | Tag panel opens (no save); client-control buttons visible but NOT clicked | P1 | N | PASS |
| DV-10 | Export carries x-netskope-sqs-tag header + success toast | P1 | N | PASS |
| DV-11 | Empty state via no-match filter | P1 | N | PASS |
| DV-12 | Mock list GET 500 -> error state | P1 | N | FAIL: table stays on Loading skeleton >45 s, no message |
| DV-13 | RBAC read-only (mock): row menu only View Detail, bulk/tag Add disabled | P0 | N | PASS |
| DV-14 | RBAC none -> 403 Not Authorized | P0 | N | PASS |
| DV-15 | Deep link with host/user query params | P2 | N | applied on remount only |
| DV-16 | Unenroll action visible when flag on (do not confirm) | P2 | N | FAIL: not found |
| DV-17 | Observations: console, layout, load time | P2 | N | 11 CSP inline-style errors; table 1332px wide at 1280 viewport |
