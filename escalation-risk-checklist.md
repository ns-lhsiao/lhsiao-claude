# Escalation-Risk Design Review Checklist

> Distilled from closed escalation tickets (ENG-*). Each item encodes a class of
> defect that reached a customer and forced an escalation. When a first-draft
> design is produced by an SDD tool, evaluate the design against **every category
> that is topically relevant** and, for each, either (a) point to where the design
> already handles it, or (b) add a design requirement that closes the gap.
>
> Output a short verdict table: one row per relevant category — `ADDRESSED` (cite
> where) / `GAP` (state the missing requirement) / `N/A` (say why). Do not silently pass.

---

## A. Customer-Side Failure Modes

### C1 — Destructive operations without guardrails or recovery
**Prevents:** ENG-1054908 (Mercedes-Benz: restore deleted steering exceptions), ENG-927749 (SISAP: exceptions wiped).
**Applies when** the design has any delete / purge / reset / mode-switch / disable / overwrite path, or a state change that *implicitly* deletes dependent data (e.g. Steering Mode → None → Web Traffic wipes bypass rules).
**Must answer:**
- Does the confirmation dialog **name the concrete blast radius** ("this will permanently delete X exceptions"), not a generic "Are you sure?"
- For high-impact deletes, is there **typed confirmation** (type `DELETE` / the resource name)?
- Is there **soft-delete / backup / restore** or an undo window for the deleted data?
- Are **implicit cascade deletes** (side effects of a mode/type change) surfaced to the user *before* commit?

### C2 — Unbounded bulk input causing overload
**Prevents:** ENG-1011226 (Trimble), ENG-1001668 (SIN2), ENG-872728 (Concentrix: Steering config fails to load). Root cause: a 3 MB CSV held 101,000+ rows vs a 10,000 design cap that was only in internal docs.
**Applies when** the design accepts CSV / bulk / batch / import / file upload, or writes N rows from one request.
**Must answer:**
- Is there an explicit **max-record count** enforced on **both** frontend parse and backend API — not just a file-size limit?
- Does the UI advertise the **record limit**, not a misleading "Max upload 16 MB"?
- What happens at the Nginx / gateway body & timeout limits for large payloads — graceful reject with a clear message, not a raw failure?
- Is the enforced cap consistent with the architectural cap (no doc-only limits)?

### C3 — Frontend validation gap → uncaught backend 500
**Prevents:** ENG-1056226 (MTN: notification template save → 500 on `https:///aveksa...`).
**Applies when** the design has free-text fields feeding a backend (URLs, emails, hostnames, regex, JSON, IDs).
**Must answer:**
- Is there **strict format validation** at the field (e.g. RFC URL) that blocks submit?
- Does the backend **catch malformed input** and return a structured field-level error — never an uncaught exception surfacing as a generic 500?
- Does the error map back to the **specific field** in the UI?

### C4 — Legacy data / schema incompatibility → false errors & malformed responses
**Prevents:** ENG-914205, ENG-968515 (old v2 policies with empty `activities: []` → DB error → "You are not authorized to edit policy of this type").
**Applies when** the design reads/writes data that has **older versions/schemas**, or computes over arrays/objects that may be empty/null.
**Must answer:**
- **Defensive defaulting**: does logic assume non-empty arrays / present fields? Handle empty & legacy shapes explicitly.
- Does the API guarantee a **single well-formed response** on error (no double/error+success JSON, no output after an error)?
- Does the UI **fall back to a truthful message** on parse failure, not a misleading canned string (e.g. a fake RBAC error)?

### C5 — Cross-environment artifact bleed
**Prevents:** ENG-1002359 (FedRAMP/WaTech: Commercial-only migration banner showed in FedRAMP).
**Applies when** the design introduces banners, announcements, feature availability, or migration UI that should differ by environment (Commercial vs FedRAMP/GovCloud) or compliance/region/tenant class.
**Must answer:**
- Is the publish condition gated on **environment / compliance attributes**, not just build/version?
- Is there a test for "does NOT appear in the wrong environment"?

### C6 — Policy precedence & overlap confusion
**Prevents:** ENG-1057253 (Novartis: SSL DND edit silently reverts), ENG-875241 (Auchan: wrong RTP policy applied).
**Applies when** the design lets users create multiple rules/policies evaluated in an order (predefined + custom, priority lists).
**Must answer:**
- Does the UI **visually reflect the engine's evaluation order / hit precedence**?
- Is there **shadowing / conflict detection** — a warning when a new rule is fully covered by a broader rule above it, or silently reverts?

---

## B. Feature-Flag Failure Modes

### FF1 — Flag dependency deadlock (implicit coupling)
**Prevents:** ENG-1004137, ENG-988544, ENG-1000002, ENG-1001768 (Destination Profile enabled but blocked by `nplan4569_url_list_migration_phase=0`), ENG-1001894 (steering_match_criteria implicitly depends on Proxy Match).
**Applies when** the feature is guarded by a flag, or its behavior depends on another flag/phase toggle.
**Must answer:**
- Are **all co-required flags / migration-phase values documented** as a dependency set?
- If a required flag is off/at the wrong phase, does the API return an **explanatory error** (not a bare `403 forbidden`) that names the flag?
- Is the dependency discoverable in URSA / config without an escalation?

### FF2 — Release-notes GA vs flag-gated reality
**Prevents:** ENG-1003425, ENG-1000077, ENG-985122 (`nplan5195_secure_enrollment_expiration_email_notification` announced GA in 136.0.0 but default-off per tenant).
**Applies when** the feature will be announced in release notes / marketed as available.
**Must answer:**
- Is the **default-enable state** (on/off, per-tenant vs global) explicitly decided and documented?
- Is the flag's **lifecycle aligned with the GA announcement** (auto-enable on the announced version, or the RN clearly states "contact support")?

### FF3 — Multi-service / multi-flag coupling
**Prevents:** ENG-1118684, ENG-1071385 (`nplan6965_ui_client_mvp_ai_discovery_enabled` UI flag needs backend `enableEndpointAiAssetDiscovery`), ENG-1058844.
**Applies when** a UI flag and a backend flag (or flags across services) must be enabled together to function.
**Must answer:**
- Are the **paired flags documented and enabled together** (never UI-only)?
- What is the behavior if only one side is enabled — is it safe / clearly degraded, or does it silently break data processing?

---

## C. Works-as-Designed & Improvement Gaps

### WAD1 — UI exposes unsupported capability
**Prevents:** ENG-983705, ENG-988335 (CFW allows notification-template selection with no client popup), ENG-1197420, ENG-941198, ENG-1074863 (FormPost not rendering).
**Applies when** the UI offers a control/option whose backend support is partial or absent for that context (CFW/FTP/non-web, Destination Profile, missing content-inspection profile).
**Must answer:**
- Does the frontend **gate the control on actual backend capability** for the selected context?
- Are illegal combinations blocked with a **correct, specific message** — not a misleading auth error?

### WAD2 — Orphaned references vs active inventory (split data source)
**Prevents:** ENG-944161 (Omnicom: can't filter policies for deleted users), ENG-900078 (SCIM group rename not honored in Steering), ENG-904484 (no audit logs for custom categories).
**Applies when** search/autocomplete reads one source (active inventory) while stored config reads another (snapshot string / hardcoded name).
**Must answer:**
- Can admins **search/filter for referenced-but-inactive** entities (deleted users still in a policy)?
- On **rename/delete of a referenced entity** (SCIM group), do all consumers (Steering/Client Config) update, or is the old name hardcoded → match failure / fallback?

### WAD3 — Data volume & memory / pagination ceilings
**Prevents:** ENG-975774 (Concentrix: ~1.1 GB CSV export → `ERR_INCOMPLETE_CHUNKED_ENCODING`), ENG-1275759 (Wistron: infinite load, no pagination for groups/OUs), ENG-987424 (Morgan Stanley: slow non-standard ports tab).
**Applies when** the design lists, exports, or downloads data that scales with a large tenant.
**Must answer:**
- Is large export **streamed / chunked / server-side**, not built as one browser Blob (which dies past ~500 MB)?
- Do list/dropdown reads have **pagination or server-side search** — no hardcoded `LIMIT 100`?
- Was performance considered at enterprise scale, not just default-tenant size?

### WAD4 — Audit gaps & security-UX ambiguity
**Prevents:** ENG-897485 (PSIRT: viewing/copying Secure Enrollment Tokens not audited), ENG-1176580, ENG-1084530 (SWIFT: wrong help bubble), ENG-965169 (bypass delete didn't update `steering_config_v2.modify_time`).
**Applies when** the design touches sensitive data (tokens/secrets), mutations, or user-facing help/tooltips.
**Must answer:**
- Are **sensitive reads/copies and all mutations emitting audit events** (compliance requirement)?
- Do mutations **write back `modify_time` / last-edit** on the parent object so audit/overview stays truthful?
- Are **tooltips/help text semantically accurate** (e.g. "egress source IP" vs actual client IP)?

---

## D. Release Coordination & State Consistency

### M1 — Same-page cross-version / cross-repo release coordination
**Prevents:** ENG-975193, ENG-975879 ("Profile ID is required" — `nplan5196` default true in classic but mf-client default not yet deployed, so effective flag still false; deploy rescheduled Apr 13 → Apr 16 due to freeze).
**Applies when** the feature spans multiple repos/artifacts (classic + mf-client + backend) with independent default-flag states and deploy timelines.
**Must answer:**
- Is there a **cross-repo dependency map** and the **effective default-flag state** in each artifact?
- Is the **deploy ordering / timeline** (and freeze windows) analyzed so the feature isn't half-live?

### M2 — State desync / phantom pending changes
**Prevents:** ENG-914867 (FedRAMP/Two Six: DB errors → phantom "Pending Changes" → Apply Changes hangs, blocks RTP policy creation).
**Applies when** the UI maintains a client-side state machine of pending/committed changes against backend state.
**Must answer:**
- On a **read/load API failure**, does the frontend avoid marking a non-existent transaction as "Pending"?
- Is there **reconciliation** so the client "pending diff" reflects a real backend diff (no dead-end Apply)?

---

## E. Frontend State, Input & Rendering Failure Modes

### FE1 — Async state race & edit-time hydration failure
**Prevents:** ENG-1285496 (JLL: Devices search returns wrong user), ENG-1151684 (search shows previously searched device), ENG-867457 (Action resets "User Alert" → "Alert" when editing an RTP Category policy), ENG-864832 (Inline Login "From User" constraint not shown after save), ENG-1078216 (RTP policy description hidden when Firewall app selected).
**Applies when** the design has search/filter/typeahead that re-queries on every change, an **edit form that rehydrates a saved object** into UI controls, or controls whose option lists load asynchronously (Action dropdown, conditional/collapsed sections).
**Must answer:**
- Are **stale responses discarded** (cancel the in-flight request / request-id / latest-wins) so an out-of-order API reply cannot overwrite newer search results?
- Does rehydration **map every persisted field to a visible control**, and **auto-expand** conditional/collapsed fields when a saved value exists?
- Is validation **deferred until async option lists have loaded**? A saved value must never be silently downgraded to a default (e.g. `User Alert` → `Alert`) just because its option was not there yet.
- Is there a **round-trip test**: open an existing saved object with each non-default value and confirm it displays and re-saves unchanged?

### FE2 — Input sanitization gap & cross-DB case-sensitivity mismatch
**Prevents:** ENG-1148819 (regression: Custom Cloud App domain trailing whitespace still not sanitized post 139.0.0), ENG-1011624 (Morgan Stanley: same, leading/trailing whitespace), ENG-855407 ("Invalid group" due to trailing space in group name), ENG-1086200 (SSL decryption policy errors on edit).
**Applies when** the design accepts free-text identifiers (domains, URLs, user/group names) that are stored and later matched by the engine, or compares UI-entered names against values kept in more than one datastore.
**Must answer:**
- Are leading/trailing **whitespace and tab (`\t`) characters trimmed** on **both** the frontend and the API — not UI-only?
- Is **case handling consistent across stores** (e.g. Mongo lowercase vs MariaDB mixed-case)? Does the dropdown/validation compare case-insensitively instead of throwing "Invalid group / Invalid value"?
- Does the sanitization cover **every entry path** (form, paste, CSV import, API), with a regression test so a later fix does not silently undo it?

### FE3 — Silent drop, error swallowing & fake 200 OK
**Prevents:** ENG-1163945 (On-Prem Infrastructure KMIP certificate validation error missing — "Saved Successfully" shown), ENG-1143602 (Destination Profile UI silently drops entries above 9,999 vs documented 100,000 limit).
**Applies when** the design has an API that can fail on business validation, or a UI that caps/filters/truncates user input (paste, file upload, list entry). Overlaps with **C2** — check both.
**Must answer:**
- Does the API use **HTTP status codes that reflect failure**, rather than `200 OK` with `{status: "error"}` in the payload?
- Does the frontend **check the business-level result before showing a success toast**?
- Does every UI-side cap **match the documented / architectural limit** (no hardcoded value that contradicts the docs)?
- Is over-limit input **rejected loudly** (state the count and the limit, point to the API/bulk path) — never silently truncated?

### FE4 — Type coercion, serialization, deduplication & rendering defense
**Prevents:** ENG-995976 (Cencora: Devices export "All Rows (up to 500,000)" fails — `limit=NaN` → 400), ENG-1016407 ("Dedicated IP Ranges" shows `[object Object]` after R137), ENG-933001 (duplicate rows in Steering Exceptions tab), ENG-849351 (Venable: inconsistent domain steering exceptions), ENG-942578 (user groups render as `a.. a.. a..` after enabling Device Tags).
**Applies when** the design computes numbers for query params (page/limit/total), refactors a data model that templates read from, merges paged/added items into client state, or renders a variable-length list of tags/chips.
**Must answer:**
- Are computed numeric values **guarded against empty/`NaN`** before being serialized into query parameters or request bodies?
- After a data-model change, do templates **read nested fields explicitly** (e.g. `item.ip_range`) instead of stringifying the whole object?
- Is client state **merged by stable key (deduplicated)** across pagination, tab switches and add-item flows?
- Do large tag/group arrays use **pagination, collapse or virtual scrolling** so layout cannot break at enterprise scale?

---

## F. Access Control & Backend Resilience

### RBAC1 — Undefined custom-role properties & over-broad API permission
**Prevents:** ENG-944197 (Deloitte: cannot configure RTP policies with custom role — `TypeError` on `o.aiSecSelected`), ENG-1268089 (Deloitte: RBAC-role users cannot view Devices page), ENG-1218294 (admin with URL-list Manage-only role can Apply Changes, bypassing approval).
**Applies when** the design adds a permission/feature key, gates UI or API by role, or exposes deploy/apply-type endpoints.
**Must answer:**
- Does the frontend **tolerate permission keys that are absent** for existing custom roles (optional chaining / explicit defaults), so a newly added permission cannot crash the whole wizard?
- Does **RBAC v3 composite / fine-grained permission** resolve correctly in every allowed-roles list, not only for Tenant Admin?
- Does each endpoint check the **specific permission for the action** (e.g. `POST /api/v2/policy/urllist/deploy` needs Apply/Deploy, not just Manage), so the **Request Approval flow cannot be bypassed** via API?
- Is there a test with a **custom role lacking the newest permission** and a **restricted role attempting deploy**?

### R1 — Downstream latency & cache miss causing whole-page timeout
**Prevents:** ENG-898881 (DFW3: RTP policy page slow / intermittent errors), ENG-880594 (Jubilant Foodworks: Inline policy page "We seem to be experiencing some issues currently").
**Applies when** a page or API synchronously calls downstream microservices (e.g. `swg-profile`) or depends on cached state (Redis feature-flag matrix per tenant/custom role) to render.
**Must answer:**
- Do synchronous downstream calls have **timeouts, a circuit breaker and graceful degradation** (partial page / cached fallback) instead of surfacing a 504?
- On a **cache-key miss/expiry**, is there a **fallback rebuild path** that does not block the request or cause a full-query stampede?
- Can a **non-critical dependency being slow or down** still leave the main page loadable?

---

## How to use this checklist
1. Read the design.
2. Select every category above that is topically relevant to the design.
3. For each, emit a row: **category · verdict (ADDRESSED / GAP / N/A) · evidence or the missing requirement**.
4. Fold every `GAP` back into the design as an explicit requirement or open question before implementation starts.
