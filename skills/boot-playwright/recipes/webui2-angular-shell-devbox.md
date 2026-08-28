# Recipe: webui2-angular-shell-devbox

Brings up the webui2 + Angular-shell hybrid stack: **Vite + `angularHybridPlugin`,
no Docker, no devbox-ui, no static build.** React changes reflect instantly via
HMR. Standalone recipe — does not layer on `webui-angular-devbox.md`.

Read `../SKILL.md` first for the shared session/login/nav/reporting mechanics —
**except** the headless-by-default rule: this recipe's target QA tenant rejects
the headless Chrome UA, so every session here MUST be opened `--headed` (see
below).

## Architecture

```
Browser → Vite dev server (localhost:<webui2_port>)
  /ns/*           → angularHybridPlugin: proxies QA tenant HTML + serves local Angular bundles
  /mf/shell/*     → React shell (HMR)
  /api/v2/balkan  → ms-webui (local)
  /api/v2/rbac    → ms-webui (local)
  /pinger         → ms-webui (local)
  everything else → QA tenant proxy (auth, other APIs)
```

Angular still owns `window.location`. React navigates via `shell:navigate`
CustomEvents. `<balkan-shell>` custom element mounts the React root (no shadow
DOM).

## Step 0: MariaDB must be running

Both ms-webui and the webui2 auth path depend on a live MariaDB. Check before
anything else — this stack fails opaquely (mismatched "database not found" 500s)
if skipped:

```bash
if ! command -v docker &> /dev/null; then
  echo "ERROR: docker not found. Start Docker/Colima and try again (e.g. colima start)"
  exit 1
fi
if docker ps | grep -qi mariadb; then
  echo "MariaDB already running"
else
  MARIADB_CONTAINER=$(docker ps -a | grep -i mariadb | awk '{print $NF}' | head -1)
  if [ -n "$MARIADB_CONTAINER" ]; then
    docker start "$MARIADB_CONTAINER"
    for i in $(seq 1 30); do
      docker exec "$MARIADB_CONTAINER" mariadb -u root -e 'SELECT 1' >/dev/null 2>&1 \
        && echo "MariaDB ready" && break
      [ "$i" -eq 30 ] && echo "ERROR: MariaDB not ready after 30s" && exit 1
      sleep 1
    done
  else
    echo "ERROR: no MariaDB container found — create one before proceeding"
    exit 1
  fi
fi
```

## Inputs

- `--tenant <name>` — key from `~/.claude/tenants.json` (default: first entry with
  a `url`)
- `--mswebui-port <N>` — default `8080`
- `--webui2-port <N>` — default `3000`

Tenant ID must match across three places or ms-webui can't find the database:
`~/.claude/db.json` → `mariadb.tenantid`, webui2 `.env.local` → `PUBLIC_TENANT_ID`,
ms-webui env → `MS_WEBUI_TENANT_ID`. All three use the **db** tenantid, not the
proxy tenant's own ID — ms-webui picks the database from the auth header, so a
mismatch between the proxy tenant and the local DB produces "database not found."

## Step 1: Locate repos

Check `$PWD` first, then sibling directories:

- **webui2**: `turbo.json` + `apps/shell/`
- **ms-webui**: `go.mod`
- **webui (Angular)**: `src/webui/neo/src/app/util/feature.util.ts`

If any is missing, ask the user for the path.

## Step 2: Check ports

```bash
nc -z 127.0.0.1 <mswebui_port> && echo "TAKEN" || echo "free"
nc -z 127.0.0.1 <webui2_port>  && echo "TAKEN" || echo "free"
```

If taken, check what's running (`lsof -i :<port> | grep LISTEN`) — if it's already
the correct service from a previous run, skip starting it; otherwise abort and ask
for a different port.

## Step 3: Check Angular dist

```bash
DIST_DIR="<webui_path>/src/webui/system_framework/UI_Layer/dist/dev-lazy"
ls "$DIST_DIR/angular_view.txt" 2>/dev/null && echo "dist ready" || echo "MISSING"
```

If missing, ask the user to run (first build ~110s, incremental ~10–30s, keeps
running in background and auto-rebuilds):

```bash
cd <webui_path>/src/webui/neo
NODE_OPTIONS=--max-old-space-size=8192 npm run dev:watch-lazy
```

If Angular changes aren't needed and a stale `dist/dev-lazy` with
`angular_view.txt` already exists, the watch process is optional. Without the
dist folder at all, the page renders blank.

## Step 4: Write `.env.local`

Target: `<webui2_path>/apps/shell/.env.local`

```env
ENABLE_WEBUI_PROXY=true
WEBUI_PROXY_URL=<tenant_url>
PUBLIC_LOCAL_API_URL=http://localhost:<mswebui_port>
PUBLIC_TENANT_ID=<db_tenantid>
PUBLIC_LOCAL_API_PATHS=/api/v2/balkan,/api/v2/rbac,/pinger
PUBLIC_PATH_PREFIX=/mf/shell
ANGULAR_DIST_DIR=<webui_path>/src/webui/system_framework/UI_Layer/dist/dev-lazy
```

`/pinger` is required in `PUBLIC_LOCAL_API_PATHS` — the shell's auth guard calls
it on startup; without it, the call falls through to the QA proxy and can 503.

**Do NOT set `ANGULAR_BALKAN_ROUTES`** — when unset, the plugin falls back to
`public/signed_off_pages.json`, which has the correct `settings?view=xxx` redirect
entries. Setting `ANGULAR_BALKAN_ROUTES` only generates identity mappings and
can't express those redirects.

If the file already exists, show a diff and confirm before overwriting.

## Step 5: Install dependencies (skip if present)

```bash
[ -d "<webui2_path>/node_modules" ] || (cd <webui2_path> && pnpm install)
```

## Step 6: Start ms-webui

```bash
cd "<webui2_path>" && \
  MS_WEBUI_DIR="<mswebui_path>" \
  PORT=<mswebui_port> \
  MS_WEBUI_TENANT_ID=<db_tenantid> \
  bash scripts/dev-backend.sh > /tmp/mswebui.log 2>&1 &
MSWEBUI_PID=$!
```

If `scripts/dev-backend.sh` doesn't exist (older webui2 checkout), fall back to
starting ms-webui directly:

```bash
cd "<mswebui_path>" && \
  PORT=<mswebui_port> \
  MS_WEBUI_TENANT_ID=<db_tenantid> \
  GIN_MODE=debug \
  go run ./cmd/ms-webui/ > /tmp/mswebui.log 2>&1 &
MSWEBUI_PID=$!
```

Wait for health, kill on failure rather than leaving an orphaned process:

```bash
for i in $(seq 1 30); do
  curl -sf http://localhost:<mswebui_port>/healthz > /dev/null 2>&1 && echo "ms-webui ready" && break
  [ "$i" -eq 30 ] && echo "ERROR: ms-webui failed after 30s" && kill $MSWEBUI_PID 2>/dev/null && break
  sleep 1
done
```

## Step 7: Start Vite dev server

```bash
cd "<webui2_path>" && \
  pnpm --filter shell dev --port <webui2_port> > /tmp/vite-angular-shell.log 2>&1 &
VITE_PID=$!
```

Wait for health, kill on failure:

```bash
for i in $(seq 1 15); do
  nc -z 127.0.0.1 <webui2_port> 2>/dev/null && grep -q "\[hybrid\] serving" /tmp/vite-angular-shell.log \
    && echo "Vite ready" && break
  [ "$i" -eq 15 ] && echo "ERROR: Vite failed after 15s" && kill $VITE_PID 2>/dev/null && break
  sleep 1
done
curl -sf "http://localhost:<webui2_port>/ns/signed_off_pages.json" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'signed_off_pages: {len(d)} entries')"
```

Expect 34+ entries.

## Step 8: Report

```
## Angular Shell + webui2 Local Dev

### Services
[ok] ms-webui       http://localhost:<mswebui_port>  (tenant <db_tenantid>)
[ok] Vite dev       http://localhost:<webui2_port>/ns/
[ok] Angular dist   <dist_dir>  (N bundles)
[ok] signed_off     N entries from public/signed_off_pages.json

### Proxy
[ok] QA tenant      <tenant_url>
[ok] Local paths    /api/v2/balkan, /api/v2/rbac, /pinger → localhost:<mswebui_port>
```

## Login — MUST be headed, not headless

The QA tenant blocks the headless Chrome UA with "Safari 0 is not supported" —
this is the one recipe where `../SKILL.md`'s headless default does NOT apply:

```bash
playwright-cli -s=<slug> open --headed http://localhost:<webui2_port>/ns/#/login
```

Then follow `../SKILL.md`'s login flow as written. After login, navigate to any
migrated page, e.g. `http://localhost:<webui2_port>/ns/#/settings/certificates`.

If nav still links to the old Angular page instead of React, clear the cache
(30-minute TTL, persists across Vite restarts — always clear after changing
`signed_off_pages.json`):

```bash
playwright-cli -s=<slug> sessionstorage-delete balkan_pages
playwright-cli -s=<slug> reload
```

## Iterate

- **webui2/React code**: Vite HMR handles it automatically, no rebuild needed.
- **Angular code**: wait for `dev:watch-lazy`'s incremental build (~10–30s); Vite's
  file watcher detects the dist change and reloads Angular bundles automatically.
- **`signed_off_pages.json`**: edit `<webui2_path>/apps/shell/public/signed_off_pages.json`
  → restart Vite → clear `sessionstorage.balkan_pages` → reload.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Safari 0 is not supported" / stuck on spinner after login | Headless Chrome UA rejected by QA tenant | Reopen the session with `--headed` |
| `[hybrid] ANGULAR_DIST_DIR not found` | Angular dist doesn't exist yet | Run `npm run dev:watch-lazy` and wait for first build |
| Nav points to old Angular page instead of React | (1) stale `balkan_pages` cache, or (2) `signed_off_pages.json` keys don't match Angular `NavigationStart.url` format | Clear the sessionStorage cache; check `href:` values in `navbar-config.service.ts` |
| Settings left-nav not highlighting correctly | React route URL doesn't start with `/settings/` | Confirm the page is under `_authenticated/settings/` in webui2 routes; check `nav-config.ts` and `signed_off_pages.json` `webui2_route` |
| `Invariant failed: Could not find an active match from "/_authenticated/..."` | Stale `webui2_route` in `balkan_pages` cache | Clear `sessionstorage.balkan_pages` and reload |
| ms-webui 400 "missing x-netskope-tenantid" | Request not going through the local proxy path | Confirm `PUBLIC_LOCAL_API_PATHS` includes `/api/v2/balkan` |
| RBAC timeout / "Request timed out: GET /api/v2/rbac/roles/me" | `/api/v2/rbac` (or `/pinger`) missing from `PUBLIC_LOCAL_API_PATHS` | Add it and restart Vite |

## Stop services

```bash
lsof -ti:<webui2_port> | xargs kill 2>/dev/null
lsof -ti:<mswebui_port> | xargs kill 2>/dev/null
playwright-cli -s=<slug> close   # only if the user is done with the session
# Angular watch-lazy: kill manually if started, or leave running for next session
```

To restore the plain (non-hybrid) webui2 shell, the third-party `/wb:setup:webui2-shell`
command overwrites `.env.local` back to the pure React config — this recipe does
not wrap or depend on it, but it's the known way back.
