# API Contracts & Jira

## v2 / API Contract Hygiene

- **Tenant edge does NOT publish OpenAPI specs**. All discovery paths return 404 (`/apidocs/swagger.json`, `/v2/api-docs`, etc.). Workaround: `gh pr diff <num> --repo netSkope/api-gateway-endpoints` returns the YAML directly.
- **v2 live probe is a partial sample, not a schema**. Fields absent from sampled rows aren't necessarily rejected. Cross-reference Confluence §4.x schema and legacy Angular payload before dropping a field. v2 explicitly rejects unknowns with 422 `"unexpected property"`. Failure: 422 on create after "fixing" a payload, or fields silently disappear on edit round-trip.
- **Hand-rolled fetchers + hand-rolled MSW = silent contract drift**. TS sees the hand-typed response, MSW serves the hand-built shape, vitest passes, bug appears live. Mirror a proven legacy fetcher's exact request envelope and `data`/`result` wrapper.
- **Verify wire unit before refactoring on field name**. `maxTimeoutSeconds` may carry minutes. Don't multiply by 60 everywhere on a name alone — probe a live config first. Failure: a value of `30` displays "30 seconds" in v2 but "30 minutes" in v1.
- **Form unit dropdowns don't auto-convert**. `min` ↔ `hr` toggles are cosmetic unless `onChange` multiplies by 60 and `value` divides by 60. Keep storage normalized to one unit; translate at the input boundary; adjust `min`/`max` per unit.
- **bulkdelete request shape** (`/clientconfiguration/client/config/bulkdelete`): `{ action: "delete", scope: "selective", ids, idempotencyToken }`. Missing any → 422. Cap 250 ids/req; rate limit 4 req/sec (vs 50/sec for per-item CRUD).
- **bulkdelete 202 response**: only `jobId` is load-bearing. **bulkstatus response**: `{ jobId, status, action, totalAffected (int64), message, createdAt, completedAt }` — NO `processed`/`total`/`errors[]`. Status enum has 5 values: `accepted | in_progress | completed | failed | cancelled`. A poll loop terminating only on `completed|failed` spins until timeout on `cancelled`.
- **Idempotency token belongs at the call site**, not inside the HTTP function. Generating in the fetcher creates a new token per retry, defeating the purpose. Generate in `mutationFn` or via `useRef`, pass as parameter.
- **`/api/v2/users/getgroups` SAML field semantics are inverted**. For `collectionId: 'default'`: `row.id` is BOTH the wire id AND the user-visible group name (the substring filter `id.co` matches against it; legacy mf-client `searchV2UG` maps both label and value from `row.id`). `row.displayName` is NOT used for this collection — preferring `row.displayName` over `row.id` paints a non-name string into the picker and submits it as the wire id, triggering a misleading "OU/Group already exists" on save. For `collectionId: 'jit_default'` (SAML): `row.scimId` = wire id, `row.id` = display name. Also: scimId batch lookup MUST include `collectionId: 'jit_default'` in the filter or rows render as raw UUIDs.
- **Angular `processMonthlyVersions`**: legacy v1 `specificversions` is a SUPERSET of `goldenversions`. The monthly dropdown = `specificversions.filter(v => !goldenSet.has(v))`. v2 `/client/versions` flips the schema — each release carries `golden` and `specific` independently; the v2-equivalent is `release.specific && !release.golden`. Aliasing `monthly = specific` lists golden majors as monthly hotfixes.

## Jira & CM API

- **`POST /rest/api/3/search` is removed** — use `/rest/api/3/search/jql` (same body).
- **Jira `assignee` on create gets overridden** by component default assignee. Always follow create with `PUT /rest/api/3/issue/<KEY>/assignee -d '{"accountId":"..."}'` (HTTP 204).
- **QA Test Recommendations field** is `customfield_12503`, accepts ADF doc (not plain text). Discover field IDs with `GET /issue/<KEY>?expand=names`.
- **Root Cause Analysis field** is `customfield_11701` (ENG project). Schema says `textarea` but **rejects plain string** (`400 Operation value must be an Atlassian Document`) — send ADF `{"version":1,"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":...}]}]}`. Find it via `GET /issue/<KEY>/editmeta` grep `root|cause` in field names.
- **CM `security` field** can't be set on create ("not on appropriate screen"). Omit it.
- **CM `customfield_16792` (Type of Change)** is a cascading select: `{"id":"PARENT","child":{"id":"CHILD"}}`. Software > Feature Flag = `13191` / `28422`.
- **Atlassian MCP fallback to curl**: tools may not be exposed even when `mcp.json` configures the server. Use `curl -s -u "USER:TOKEN" "https://SITE/rest/api/3/..."`. Env vars: `ATLASSIAN_API_TOKEN`, `ATLASSIAN_USER_EMAIL`, `ATLASSIAN_SITE_URL` (NOT `ATLASSIAN_EMAIL`/`ATLASSIAN_SITE`).
- **Those `ATLASSIAN_*` vars are NOT exported into the shell** — they exist only inside `~/.claude/mcp.json` at `mcpServers.atlassian.env`. Symptom: `curl -u "$ATLASSIAN_USER_EMAIL:$ATLASSIAN_API_TOKEN"` returns non-JSON HTML → `json.decoder.JSONDecodeError: Expecting value: line 1 column 1`; `env | grep ATLASSIAN` returns nothing; `${!v}` gives zsh `bad substitution`. Fix: read the values inside a `python3 -c` one-liner (`json.load(open(os.path.expanduser('~/.claude/mcp.json')))['mcpServers']['atlassian']['env']`) and build the Basic auth header there. Never echo them.
- **Confluence page fetch by ID**: `GET /wiki/api/v2/pages/<id>?body-format=storage` with the Basic header above. The `/wiki/rest/api/content/<id>?expand=body.storage` v1 path also works.
- **`~/.claude/mcp.json` contains plaintext tokens** — never commit. The config repo's `.gitignore` excludes it.
- **`PAYLOAD=$(python3 -c '...json.dumps...'); echo "$PAYLOAD" > file.json` corrupts multi-line JSON in zsh.** zsh's builtin `echo` interprets backslash escapes by default (unlike bash) — every literal `\n` inside the JSON string gets turned into a *real* newline byte, producing invalid JSON (raw control char inside a string). Symptom here: `curl -X PUT` on a Jira `description` field returned `204` (looked successful) but the stored text had all newlines silently collapsed — lines ran together with no separator at all, because Jira's parser tolerated/dropped the bad control chars. Fix: never round-trip JSON through `echo` in this shell. Build the payload in one `python3 -c` that writes the file directly (`json.dump(payload, open(path,'w'))`), or use `printf '%s' "$PAYLOAD" > file.json` (printf does not do escape interpretation the way zsh `echo` does). Always sanity-check with `python3 -c "import json; json.load(open(path))"` before curling.

## Save Jira attachments with their real file extension BEFORE `Read` (2026-09-14)
- Downloading a ticket attachment via
  `curl -u "$EMAIL:$TOKEN" -L "<attachment content URL>" -o /tmp/x/5148232.img`
  and then `Read`-ing it made Read treat the JPEG/PNG as **text** and dump ~44k tokens of binary
  garbage into context (truncated mid-file). Read dispatches on **file extension**, not sniffed
  content type.
- Fix: derive the extension from the attachment's `filename` / `mimeType` in the issue JSON
  (`.fields.attachment[] | {filename, mimeType, content}`) and save as `.png`/`.jpg`/`.pdf`.
  If already saved wrong, `mv foo.img foo.png` then Read — no re-download needed.
- Ticket screenshots are often the decisive evidence (a DevTools network capture on ENG-1277661
  contained the exact API response body that confirmed root cause), so this path is worth getting
  right the first time rather than avoiding.

## mcp.json Atlassian env key names (2026-10-08)
- Guessing `JIRA_USERNAME`/`JIRA_API_TOKEN` read None → every `/rest/api/3/issue/*` returned 404 (anonymous, not 401). Real keys in `~/.claude/mcp.json` → `mcpServers.atlassian.env`: `ATLASSIAN_SITE_URL`, `ATLASSIAN_USER_EMAIL`, `ATLASSIAN_API_TOKEN`.
