---
slug: <kebab-slug>
title: <Page title as shown in UI>
nav: <Menu > Path>
route: "#/..."
session: <=15 chars>
renderer_matrix:
  - renderer: <angular|react-mf-xxx>
    when: <flag condition that selects it>
    present: ["<selector>"]
    absent: ["<selector>"]
flags:
  globals_regex: "<regex over window.ns.globals keys>"
  balkan_keys: []
rbac_mock:
  readonly: "<url + response shape>"
  none: "<url + response shape>"
api: ["<METHOD path>"]
object_prefix: "e2e-xx-"
mutation:
  creates: <true|false>
  cleanup: <how objects are removed and verified>
apply_policy: <none|needs-apply-to-clean>
open_questions: []
last_verified: YYYY-MM-DD
---

# <Page title>

Notes: source map, quirks.

## Cases

| ID | Title | Pri | Mutates | Baseline (last observed) |
|---|---|---|---|---|
| XX-01 | Renderer gate + list load | P0 | N | |
