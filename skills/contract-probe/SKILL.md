---
name: contract-probe
description: >-
  Probe a v2 (or any JSON) HTTP API to discover its real request contract by
  sending progressively-shaped payloads and surfacing every 422 / 4xx error
  body. Useful when working with hand-rolled fetchers or undocumented endpoints
  where the OpenAPI spec is missing or stale, and the only way to learn
  required fields is to ask the server. Triggers on "/contract-probe", "probe
  the API", "what does this endpoint require", "find required fields", or any
  request to reverse-engineer a request shape from live 422 responses.
argument-hint: "<METHOD> <URL> [optional: starting payload as JSON or @file]"
allowed-tools: Bash(curl:*), Bash(jq:*), Read, Write, AskUserQuestion
user-invocable: true
---

# Contract Probe

**Emit "Skill activated: contract-probe"**

## Why this exists

Hand-rolled fetchers drift silently from the real API contract — TypeScript
sees only the hand-typed shape, MSW serves the hand-built shape, vitest
passes, and the bug surfaces only against a live tenant. v2 endpoints reject
unknown properties with `"unexpected property"` and require fields that aren't
documented anywhere. This skill probes the live endpoint to learn the real
contract.

Recurring examples in this codebase:
- `client/config/bulkdelete` required `action`, `scope`, `idempotencyToken`
  (none documented; only discovered via a live 422).
- `saveOUConfigV2` field set differs from the survey live-probe.
- `/api/v2/...` endpoints reject unknown fields strictly.

## Inputs

Parse `$ARGUMENTS` for:
- HTTP method (GET, POST, PUT, PATCH, DELETE)
- Full URL (or path — ask for tenant/host if missing)
- Optional starting payload (inline JSON or `@/path/to/payload.json`)

If anything is missing, ask via `AskUserQuestion` once. Don't proceed with
guesses for the URL or method.

## Procedure

### 0. Establish auth

The user generally hits dev/staging tenants through the local development
proxy at `http://localhost:9797`. If the URL points there, no auth header is
needed (the proxy handles it). Otherwise, ask whether the request needs a
bearer token / cookie / `x-netskope-*` header; do not invent auth values.

### 1. Probe with the empty body (POST/PUT/PATCH only)

```bash
curl -sS -i -X "$METHOD" "$URL" \
  -H 'content-type: application/json' \
  -d '{}'
```

Capture status + response body. Most v2 endpoints respond with a 422 listing
ALL violations of required fields and unknown-property rejections at once.
Parse the body (it's usually `{ "error": { "details": [...] } }` or similar)
and extract:
- Required fields the server wants
- Type/format expected for each
- Any forbidden fields the body mentioned

### 2. Iterate

Build a minimal candidate payload from step 1. Send again. Repeat until the
response stops being 422 — then you've found the minimum viable shape.

If the response becomes 4xx for a different reason (auth, not-found, wrong
verb), report and stop — that's a configuration problem, not a contract
problem.

If the response becomes 2xx, also send a probe with a deliberately
unknown property to confirm the endpoint rejects unknowns. This tells the
caller whether the API is strict or permissive.

### 3. Compare with the user's hand-rolled shape (optional)

If the user supplies an existing payload (or points to a `*.api.ts` /
`*.ts` file), diff it against the discovered minimum:
- Fields the user sends that the server rejected (extras to remove)
- Fields the user omits that the server requires (gaps to add)
- Fields with mismatched types

### 4. Report

Output a compact contract summary:

```
Endpoint: POST /api/v2/clientconfiguration/client/config/bulkdelete
Status:   200 OK with minimal payload

Required fields:
  - action            string (enum: delete)
  - scope             string (enum: selective | all)
  - ids               string[]
  - idempotencyToken  string (uuid)

Strictness: rejects unknown properties (422 "unexpected property")

Diff vs. submitted shape:
  + action            (missing — required)
  + scope             (missing — required)
  + idempotencyToken  (missing — required)
  - extraDebugFlag    (rejected — not in schema)
```

Then offer to write the discovered shape to a TypeScript `interface` /
`type` (in a path the user names) or to a JSON fixture for MSW.

## Safety

- **Never probe a production tenant.** Confirm the host is dev / staging /
  local proxy before sending. If unsure, ask.
- **Never use destructive verbs (DELETE, bulkdelete) against a real
  resource.** For mutating endpoints, prefer using a known-throwaway id, or
  pause and ask the user to provide one.
- Cap at ~10 probe iterations — if the contract isn't converging, surface what
  you've learned and stop. Don't spam the API.
- Redact any auth values from the report output.

## Don't

- Don't write the TypeScript types unless the user asks.
- Don't silently accept the first 2xx — also confirm strictness with one
  unknown-property probe so callers know whether to be paranoid about extras.
- Don't treat the v2 live-probe artifact (e.g. files under
  `migrations/pages/<page>/survey/`) as authoritative for required fields —
  it samples populated data only and misses optional fields and required
  fields that happened to be omitted in the sample.
