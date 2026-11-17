# Crane / webui2 Rendering and the x-npe-env Sidecar

Last updated: 2026-11-14. Tickets: ENG-1419054, ENG-1419882, ENG-1419883.

How webui2 gets loaded and rendered, and whether the PR sidecar (`x-npe-env`) takes effect on each path — why, and where it was fixed.

---

## 1. One-line conclusion

**Which webui2 build runs is decided by whoever serves the first unhashed file.**

Every filename after that carries a hash baked in at build time, pointing only to other files of the same build. `x-npe-env` only changes *where* a file is fetched (the edge rewrites the path to the sidecar), never *which filename* is requested.

---

## 2. Three independent layers (don't mix them up)

| Layer | Question | Answer |
|---|---|---|
| Hosting | Where does the traffic go? | ngssl splits on `$crane_tenant` (`map $host` ← `/etc/nginx/crane_tenants.map`). crane=1 → AWS NLB; crane=0 → qa01 (PHP / ngweb_mf) |
| HTML producer | Who generates the `/ns` HTML? | Non-cutover: webui PHP `Ns::index()`; crane cutover: ms-bootstrap `AppController.root()` |
| Shell | Who ultimately controls the page? | Angular shell (webui neo) or React shell (webui2 frame) |

- ms-bootstrap does **not sit behind webui**; it is the service crane tenants use to **replace** webui PHP as the `/ns` producer.
- `/mf/frame` is **not crane-only**; it is simply the build of webui2's standalone React shell. The crane config has dedicated locations for it only because crane tenants' frame is served from AWS.

---

## 3. The two webui2 builds

The same source is built twice (`webui2/Dockerfile`):

```dockerfile
RUN PUBLIC_PATH_PREFIX=/mf/shell pnpm --filter shell build:cdn                       # → dist/
RUN PUBLIC_PATH_PREFIX=/mf/frame PROD_PATH_PREFIX=/mf/frame OUT_DIR=dist-frame \
    pnpm --filter shell build:cdn                                                    # → dist-frame/
```

| build | URL prefix | Purpose | Notes |
|---|---|---|---|
| `dist` | `/mf/shell/*` | Module Federation remote, embedded by Angular | `index.html` is deleted from the image; the Angular host is the only entry (ENG-1000627) |
| `dist-frame` | `/mf/frame/*` | Standalone React shell with its own `index.html` | What ms-bootstrap / Ns.php proxy |

**Mnemonic**:
- `dist/index.html` is unused in production and deleted from the image; only `remoteEntry.js` and assets are used. Angular embeds `<balkan-shell>` into the page — **embedded** mode: React renders only page content, Angular owns the chrome.
- `dist-frame/index.html` is the full-page React shell entry: `main.tsx` → `setShellMode('standalone')`; TopBar, Sidebar, router, auth are all React. `dist-frame/remoteEntry.js` exists but nobody uses it.
- Both are the same source with only the baked-in path prefix differing. standalone vs embedded is a runtime mode chosen by the entry point, not two different programs.

---

## 4. The `/ns` HTML → JS load chain

### 4.1 Each layer hardcodes the next layer's filename

```
/ns                                   ← fixed name, no hash
 └─ HTML hardcodes: <script src="/mf/frame/assets/index-praQZ3lv.js">
     └─ index-praQZ3lv.js hardcodes: import "./route-bootstrap-5gvgmIXt.js"
         └─ route-bootstrap-5gvgmIXt.js hardcodes: import "./dashboard-D0vFlrRg.js" …
```

main and each PR sidecar are built separately with completely different hashes. main's `index-*.js` only ever requests main's chunks, never the sidecar's.

### 4.2 How the hashed `<script>` is produced (webui2 source)

1. **Source has only the entry**: `apps/shell/index.html:146` → `<script type="module" src="/src/main.tsx"></script>`
2. **`vite build`** bundles the whole import graph from `main.tsx`, hashes each chunk by content, and replaces `src` with `index-<hash>.js`. Inter-chunk `import`s are written into the JS at this point. This is built-in Vite (rolldown) behavior; nothing custom in the repo.
3. **Prefix**:
   - `apps/shell/vite/env.ts:9-14,60`: `PROD_PATH_PREFIX` only allows `/mf/shell` or `/mf/frame`.
   - `apps/shell/vite.config.ts:41`: `base: ${env.pathPrefix}/`.
   - `vite.config.ts:49-61`: `renderBuiltUrl()` emits HTML/CSS references as `${prodPathPrefix}/${filename}`; JS dynamic imports become the runtime expression `(window.__CDN_URL__||"")+"/mf/frame/…"`.
4. **Post-build processing**: `apps/shell/vite/plugins.ts:736-770` `cdnPlaceholderPlugin` / `patchProductionHtml()`:
   - `"/mf/frame/assets/…"` → `"{{CDN_URL}}/mf/frame/assets/…"`
   - `<script type="module" crossorigin` → adds `nonce="{{NONCE}}"`
   - Module Federation's `hostInit-<hash>.js` is injected at this stage too.
5. **Pod nginx replaces placeholders at serve time**: `webui2/deploy/nginx/default.conf:33-35`
   ```nginx
   sub_filter '{{CDN_URL}}' '';            # same origin → empty string
   sub_filter '{{NONCE}}'   '$request_id';
   ```
6. After PHP or ms-bootstrap fetch this HTML, they swap the nonce for the session nonce to match the CSP header.

### 4.3 `x-npe-env` only changes "where to fetch"

```
browser requests /mf/frame/assets/route-bootstrap-5gvgmIXt.js
edge rewrites to /mf/frame/npe-pr-3893/assets/route-bootstrap-5gvgmIXt.js   ← different location, same filename
sidecar lacks this hash → 404 → @crane_mf_npe_fallback → main → 200
```

Analogy: the HTML is a printed menu listing kitchen A's dish numbers; the header only tells you to order from kitchen B. Kitchen B doesn't have A's dish numbers, so it sends you back to A.

---

## 5. Two kinds of HTML — the difference is where the hash lives

| | React shell HTML (frame `index.html`) | Angular HTML (`neo_view` / ms-bootstrap Angular template) |
|---|---|---|
| Does the HTML contain a webui2 hash? | **Yes**, hardcoded `index-<hash>.js` | **No** |
| Where the webui2 hash comes from | The HTML itself | When Angular runs, the browser fetches `${balkan_s3_cloudfront_url}/mf/shell/remoteEntry.js` (fixed name, no-cache); the hash is inside that file |
| First unhashed file | `/ns` | `/mf/shell/remoteEntry.js` |
| Who fetches it | **server** (Ns.php / ms-bootstrap curl `webui2.ngweb-v2`) | **browser** (with header, through the edge) |
| Header effective before the fix? | ❌ | ✅ (when same-origin) |

---

## 6. `/ns` shell decision

| Tenant | Producer | Condition | Result | Source |
|---|---|---|---|---|
| Non-cutover | webui PHP `Ns::index()` | `NG_BALKAN_SHELL_ENABLED` && `isLoginComplete()` && `ngBalkanShellEnabled()` | Server-side curl `http://webui2.ngweb-v2/mf/frame/index.html`, swap nonce → **React**; failure → 503, no fallback to Angular (avoids an infinite reload loop) | webui#19174 (ENG-1356940, 2026-11-03) |
| Non-cutover | same | Otherwise (not logged in, MFA, TOS, flag off) | `neo_view` → **Angular** | `Ns.php` |
| crane | ms-bootstrap `root()` | `globals.ng_balkan_shell_enabled` (**no login-state check**) | Fetch `${REACT_SHELL_SERVICE}/mf/frame/index.html`, swap nonce → **React**; failure → 503 | `app.controller.ts:42-53, getReactShellHtml()` |
| crane | same | flag off | Fetch `${ANGULAR_UI_SERVICE}/ng/dist/prod-lazy/angular_view.txt` into the `index` template → **Angular** | `getAngularIndexScripts()` |

After a non-cutover tenant logs in, Angular's `LoginService.loadPostAuthConfigs()` sees the flag on, does `history.replaceState('/ns#<target>')` then `location.reload()`, and this time PHP returns React. This is the "Angular shell → frame handoff".

---

## 7. The four main combinations and sidecar support

|  | HTML producer = PHP | HTML producer = ms-bootstrap |
|---|---|---|
| **shell = Angular** | ① non-cutover, flag off → ✅ | ③ crane, flag off → ✅ |
| **shell = React** | ② non-cutover, flag on → ❌ before fix, ENG-1419883 / webui#19476 | ④ crane, flag on → ❌ before fix, ENG-1419882 / ms-bootstrap#433 |

- ① ③: the browser fetches `/mf/shell/remoteEntry.js` itself, with the header, through ngssl's generic block. ⚠️ If `balkan_s3_cloudfront_url` is a CloudFront URL, the request bypasses ngssl and the sidecar is ineffective (qa01's actual value not yet confirmed).
- ② ④: the entry hash is in the HTML the server curls; the server doesn't send the header, so it always gets main.
- Hitting `/mf/frame/<route>` directly: no server-side proxy; the edge `^/mf/(frame)` rewrite returns the sidecar's `index.html` — ✅ for both tenant types.

### Walkthrough of case ② (`npe-pr-3893`, `/ns#/private-apps`)

1. `/ns` before login: ngssl → `$webui_pass` → `Ns::index()`, `isLoginComplete()=false` → Angular login page.
2. Log in on Angular → `reloadIntoBalkanShell()` → `replaceState('/ns#/private-apps')` + `reload()`.
3. `/ns` again: all three conditions hold → `getBalkanShellHtml()` curls `webui2.ngweb-v2/mf/frame/index.html`. **No header, straight to main's Service** → main's HTML (`route-bootstrap-5gvgmIXt`). **The sidecar is lost at this step.**
4. The browser fetches assets by main's hashes → edge rewrites to sidecar → 404 → fallback → main → 200.
5. The page is fully functional, but running main.

Contrast: hitting `/mf/frame/private-apps` directly gets the sidecar's `route-bootstrap-DvgR58Nj`.

---

## 8. ngssl edge routing (qa01 `ngsslwebui01`)

### 8.1 Crane maps (`aws_crane/upstream_map_definition.conf`)

| Variable | crane=1 | crane=0 | Used for |
|---|---|---|---|
| `$crane_webui_proxy_pass` | `http://aws_nlb` | `$webui_pass` | `/ns`, `/login`, `/ng/`, static files |
| `$crane_mf_proxy_pass` | `http://aws_nlb` | `$ngweb_mf_pass` | `/mf/frame/*` |
| `$crane_mf_host_header` | `$http_host` | `ngweb-fe` | `/mf/frame/*` |
| `$mp_webui_proxy_pass` | api-gateway | `$webui_pass` | `/ns/.+` (post-auth API) |

`x-npe-env` is first validated by the map at `webui_proxy.nginx.conf` L187 (`^npe-[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$`); an invalid value becomes an empty string.

### 8.2 Location match order (main server block)

| Order | Source | Location | npe rewrite | 404 fallback |
|---|---|---|---|---|
| L919 | `ngweb_mf_route_mappings.conf` | `~ ^/mf/(frame)/remoteEntry\.js$`, `build-info`, `~ ^/mf/(frame)(/\|$)` | ✅ | ✅ `@crane_mf_npe_fallback` |
| L985 | `webui_proxy.nginx.conf` | `~ .*remoteEntry.js$` (shell and other MFs) | ✅ | ✅ `@mf_npe_fallback` |
| L1062 | `webui_proxy.nginx.conf` | `~ ^/mf` | ✅ | ✅ |
| L1208 | `webui_route_mappings.conf` L19 | `~ ^/ns/?$` (**entry HTML**) | ❌ not needed (handled by the producer) | — |

The crane `/mf/frame` block applies to **all tenants**; non-cutover tenants enter it too, the map just routes them back to `ngweb_mf`.

### 8.3 Pod side (webui2 `deploy/nginx/default.conf`)

- `^~ /mf/frame/` L178: strips `/mf/frame/npe-*/` and re-matches with `last`.
- `@frame_fallback`: if the last path segment has an extension → real 404 (lets the edge fall back); otherwise → SPA `index.html`.
- `^~ /mf/shell/`: also strips the npe segment.

---

## 9. Fix (PRs submitted)

Both repos share one rule: try the sidecar first only when all three hold:
1. The tenant host equals an entry in `NPE_SIDECAR_TENANT_DOMAINS` (currently `['qa.boomskope.com']`) or ends with `.<entry>`. Suffix match, case-insensitive, port stripped. To open stg later, add `'stg.boomskope.com'`.
   - webui reads `$_SERVER['HTTP_HOST']` (`NS_Loader` uses it to look up the tenant DB).
   - ms-bootstrap reads `req.tenantUrl` (filled by `tenant-info.middleware.ts` from core DB `uiHostname`).
2. `x-npe-env` matches `NPE_ENV_HEADER_PATTERN`, the same regex as the edge.
3. The existing shell decision already chose React.

The sidecar URL is derived from `REACT_SHELL_SERVICE`: append `-<env>` to the first host label, e.g. `http://webui2.ngweb-v2` → `http://webui2-npe-pr-3893.ngweb-v2`. This matches the webui2 sidecar chart's `fullnameOverride: "webui2-{{ SUFFIX }}"` in the same namespace as main. **(Corrected 2026-11-16, webui#19476 review)** The earlier claim "the server hits the Service directly, so the missing `/mf/frame` ingress doesn't matter" was wrong: the server only gets the HTML; the browser's follow-up `/mf/frame/assets/<sidecar hash>.js` still goes edge → qa01 `webui2-mf-frame` ingress → **main** Service, the sidecar hash 404s (fallback to main also 404s) → blank `/ns`. Live test (`--resolve` with an off-list host to force the non-crane path): the sidecar's `index-*.js`/`hostInit-*.js` 404 with and without the header; `/mf/frame/index.html` with the header on the non-crane path also returns main. **Only on the crane path (AWS ALB) with the header are sidecar chunks 200**, so ms-bootstrap#433 is unaffected and webui#19476 is affected. The PHP path needs the webui2 sidecar chart to render `ingress.frame.pathPrefix: /mf/frame/<suffix>` (rewriteTarget `/mf/frame/$2`), which was blocked by `ngweb-actions` `sidecar_cleanup.yaml` deleting ingresses only by name. On the non-crane path the sidecar frame assets **are actually reachable via the existing `/mf/shell/<env>/mf/frame/assets/<hash>.js`** (verified 200 with and without the header; edge fallback makes the double prefix work, contrary to the review comment's "also 404"); bundle chunk imports are relative and CSS deps/locales use the `window.__CDN_URL__` prefix, so in theory PHP could rewrite `/mf/frame/` in the HTML and set `__CDN_URL__=/mf/shell/<env>` to avoid the ingress, but this is **not browser-verified end to end**. Also: the header regex allows up to 67 chars; with `webui2-` prepended, env ≥57 chars (label > 63), a trailing `-`, `_`, or uppercase yields an invalid DNS label and silently falls back to main.

**(2026-11-17) Fixing the PHP path**: ngweb-actions#91 (cleanup deletes ingresses by label) → webui2#4282 (MP sidecar template enables `ingress.frame.pathPrefix: /mf/frame/{{ SUFFIX }}` + `rewriteTarget: /mf/frame/$2`) → webui#19476 `f5e48e3a` (nonce check + RFC 1123 label validation). Merge in that order; ingress-nginx regex path precedence not yet verified live on qa01. Note: the AWS leg template already had `/mf/frame/{{ SUFFIX }}`; only the MP leg was missing it.

If the sidecar returns 200 with content, use it; otherwise fetch main as before. 503 only when main also fails. Shell decision, nonce, and metrics unchanged.

| Repo | PR | Ticket | Main files |
|---|---|---|---|
| webui | netSkope/webui#19476 → `develop` | ENG-1419883 | `controllers/Ns.php`, `config/constants.php`, `tests/controllers_no_db/ns/nsTest.php` |
| ms-bootstrap | netSkope/ms-bootstrap#433 → `main` | ENG-1419882 | `src/app.controller.ts`, `src/common/npe-sidecar.ts`, `src/constants/general.constants.ts` |
| service | netSkope/service#111366 (draft, **do not merge**, superseded by #433) | ENG-1419054 | `aws_crane/webui_route_mappings.conf`, `upstream_map_definition.conf` |

Test results: webui PHPUnit `nsTest.php` 99/99, `controllers_no_db` 0 failures; ms-bootstrap jest 230/230, 100% coverage on changed files.

### Why not the nginx bypass (#111366)

#111366 had the edge fetch `/mf/frame/<env>/index.html` directly for crane `/ns` requests with the header, skipping ms-bootstrap. Problems:
- nginx can't read the tenant DB's `ng_balkan_shell_enabled`, so ③ (flag off) with the header gets **forced into React**.
- ms-bootstrap#433's code would never execute.
- No domain restriction.
- Declaring `error_page` in `/ns` makes that location **stop inheriting** server-level `error_page` (maintenance page, 507, 404), affecting all tenants. That's why the split version moved the npe logic into the internal location `/__ns_npe_frame`.

---

## 10. qa01 ngssl current state (2026-11-14)

- The hotfix **has been reverted and is live** (not by us; check with whoever did ENG-1421154):
  - `aws_crane/webui_route_mappings.conf` matches service `develop` (md5 `787b9ca0`), reverted 2026-11-12 13:59.
  - The `$ns_frame_npe_env` map in `aws_crane/upstream_map_definition.conf` is gone. On 2026-11-13 14:07 an **ENG-1421154 reporting cutover** map was added; pre-change backup is `.erased-202611131357`.
  - Live test: cpcs-auth-3 with `x-npe-env: npe-pr-4071` on `/ns` returns main `index-praQZ3lv`; the sidecar is `index-DjRXN8tB`.
- So **until ms-bootstrap#433 is deployed, crane `/ns` won't pick up the sidecar**; hitting `/mf/frame/<route>` directly still works.
- Leftover backups: `webui_route_mappings.conf.broken-20261112101409`, `.hotfix-v1-20261112103605` — remove after #433 is verified.
- This VM serves **all** qa01 tenants. Always back up first, then `sudo nginx -t -c /etc/nginx/nginx-sslwebui.conf` (`-c` required); coordinate before reloading (`sudo supervisorctl signal HUP nginx`).

---

## 11. Verification

### Find "the first unhashed file" in DevTools

| What you see | Meaning |
|---|---|
| `/ns` document response contains `/mf/frame/assets/index-*.js` | React shell (②④); hash decided by the server |
| `/ns` is Angular, later loads `/mf/shell/remoteEntry.js` | Angular embedded (①③) |
| `route-bootstrap-*.js` URL is `/mf/shell/assets/…` | ①③ |
| `route-bootstrap-*.js` URL is `/mf/frame/assets/…` | ②④ |
| `ns.globals.balkan_s3_cloudfront_url` is non-empty | ① goes through CDN; sidecar won't apply |

If the first one is right, everything after is right; if it's wrong, no amount of header on later requests helps.

### curl

```bash
H=https://cpcs-auth-3.qa.boomskope.com
curl -s "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1                               # main
curl -s -H 'x-npe-env: npe-pr-4071' "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1   # should differ after the fix is deployed
curl -s -H 'x-npe-env: npe-pr-4071' "$H/mf/frame/index.html" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1  # the sidecar itself
curl -s -H 'x-npe-env: npe-pr-4071' "$H/mf/frame/build-info.json"                             # deploymentSuffix
```

### Post-deploy acceptance checklist

- Non-cutover `*.qa.boomskope.com`, flag on: `/ns` with header → sidecar; without → main; `npe-foo` → main.
- crane `*.qa.boomskope.com`, flag on: same.
- crane, flag off, with header → still Angular.
- Tenants outside the qa domain with the header → unaffected.

---

## 12. Traps

- **zsh `curl ${h:+-H "$h"}`**: zsh doesn't word-split, so the whole thing becomes one argument and the header goes out with a leading space; nginx returns `400 Bad Request`. This once made us think nginx was returning intermittent 400s. Use an array: `args=(-H "$h"); curl "${args[@]}"`.
- **zsh `$R:apps/...`**: `:a` is parsed as a modifier. Write `"${R}:apps/..."`.
- **Stale local checkout**: local webui2 master was 50 commits behind origin, which made the first render-flow report wrong (embedded fixture, LD stage, pinger method). `git fetch` and compare against `origin/master` before citing.
- **Don't confuse `/ns` with `/ns/.+`**: `/ns/.+` is post-auth API (`getStaticGlobals` etc.); adding a rewrite there breaks the API.
- **ms-bootstrap `.env.test`**: `REACT_SHELL_SERVICE="localhost"` isn't a valid URL; specs must override it with a real URL in `beforeEach` and restore in `afterEach`.
- **ms-bootstrap flag cache is request-scoped**: `TenantDbFactory` is `Scope.REQUEST`, and scope propagates upward, so flag changes don't need a pod restart.

---

## 13. Related docs

- [sidecar.md](sidecar.md): sidecar general rules; cases [sidecar-webui2.md](sidecar-webui2.md) (incl. AWS leg), [sidecar-webui.md](sidecar-webui.md), [sidecar-ms-bootstrap.md](sidecar-ms-bootstrap.md)
- [crane-frame-index-serving.md](crane-frame-index-serving.md): the return path of `dist-frame/index.html` from build, pod nginx, through PHP / ms-bootstrap to the browser (with diagrams)
- `all-html/eng-1419054-ns-npe-sidecar/crane-asset-routing-explainer.html`: crane asset routing explainer
- `all-html/eng-1419054-ns-npe-sidecar/webui2-render-modes.html`: render modes overview table
- `all-html/eng-1419054-ns-npe-sidecar/ns-shell-npe-sidecar-webui-msb.html`: webui + ms-bootstrap fix report
- `all-html/webui2-render-flow/webui2-render-flow.html`: full render flow (revised against `origin/master`)
- OpenSpec: webui `openspec/specs/balkan-shell-npe-sidecar/`; global `pr-deployment-exp/openspec/specs/ms-bootstrap-react-shell-npe-sidecar/`; `changes/ns-npe-sidecar-crane-routing/` (not yet archived; archive as superseded after #433 is verified)
