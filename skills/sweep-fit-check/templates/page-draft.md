---
slug: {{slug}}
title: {{title}}
nav: {{nav}}
route: "{{route}}"
session: {{session}}
kind: {{kind}}
renderer_matrix:
  - renderer: {{renderer}}
    when: {{when}}
    present: []
    absent: []
flags:
  globals_regex: ""
  balkan_keys: []
ff: []
cf: []
rbac_group: {{rbac_group}}
rbac_mock:
  readonly: "GET /api/v2/rbac/roles/me with the group read-only"
  none: "GET /api/v2/rbac/roles/me -> {apiGroups: []}"
probes: []
critical_probes: []
side_effects: []
blocked_cases: {}
needs_design: {}
case_roles: {}
object_prefix: ""
mutation:
  creates: false
  cleanup: ""
apply_policy: none
open_questions: []
last_verified: {{date}}
---

# {{title}}

## Cases

| ID | Title | Pri | Mutates | Baseline (last observed) | qe_ref |
|---|---|---|---|---|---|
