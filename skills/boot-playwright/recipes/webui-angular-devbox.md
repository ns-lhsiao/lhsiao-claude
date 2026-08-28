# Recipe: webui-angular-devbox (base)

Base recipe for validating a webui (Angular) change against the local `devbox-ui`
stack. `webui-angular-devbox-mf-client.md` and `webui-angular-devbox-mf-cfw.md`
both depend on this recipe for the underlying devbox stack — read this file first
whenever either of those points you here.

Read `../SKILL.md` first for the shared session/login/nav/reporting mechanics this
recipe builds on.

## Concept: one SLOT drives every offset

devbox-ui's `docker-compose.yml` hardcodes `container_name:` and host ports for
every service, so a second `docker compose up` collides even under a different
project name. A generated **compose override** duplicates only the two per-feature
services per slug:

- **Per-slug (duplicated):** `web` and `angular-ui` — these bind-mount
  `NS_WEB_UI_DIR`, so each feature needs its own pointed at its webui worktree.
  The override suffixes their `container_name` with the slug and offsets their
  published host port by `SLOT`.
- **Shared (single, from the base stack):** `db` (mariadb), `assets`, `mongodb`,
  `memcached`, `ms-bootstrap`, `pdfscheduler-*`, etc. The base `devbox-ui` stack
  must already be up — it owns the seeded DB, the seeded named volumes
  (`nginx-sites-active`, `company-*-volume`, `help-docs-volume`), and the
  `devbox-ui_default` network. Every per-slug `web`/`angular-ui` joins that
  network and reuses those volumes.

The DB is reached by container DNS: `web`'s `/opt/remote/mysql` hardcodes host
`mariadb` port `3306`. On the shared network the alias `mariadb` resolves to the
single base db container — so **there is no mariadb port offset**; every slug's
`web` talks to the same DB (writes are visible across slugs — keep that in mind if
two features touch the same tenant rows).

Port formula (SLOT is a 1-based integer):

| Thing                      | Base   | Offset expr        |
|----------------------------|--------|--------------------|
| devbox `web` TLS (→ 443)   | 8443   | `8443 + SLOT`      |
| devbox `angular-ui` (→ 80) | 4200   | `4200 + SLOT`      |
| development-proxy         | 9797   | `9797 + SLOT`      |

(mf-client and mf-cfw dev-server offsets are defined in their own layered recipes.)

`developer.vbox` still resolves to `127.0.0.1` (from `/etc/hosts`), but the web
container publishes TLS on `8443+SLOT`, so anything targeting this env must point
at `https://developer.vbox:<8443+SLOT>` instead of the bare hostname.

> **Per-slug ports break tenant recognition — this scheme only serves static
> assets, not logins.** webui's tenant lookup (`NS_Loader::getTenantDataByHost()`)
> does an EXACT match of `$_SERVER['HTTP_HOST']` (port included) against
> `core_data.org_info.ui_hostname`, which stores the bare hostname with no port.
> Hitting `https://developer.vbox:8445/locallogin` fails with "Could not
> recognize the tenant" even though the container is healthy. If the validation
> needs to log in or hit any tenant-scoped PHP endpoint (i.e. almost everything
> beyond loading `angular_view.txt`), skip the per-slug SLOT scheme below and
> use **Shared stack mode** instead: repoint the base `web`/`angular-ui`
> containers directly at the worktree with no port offset —
> `NS_WEB_UI_DIR=<worktree> docker compose up -d --force-recreate web angular-ui`
> (project name omitted, so it recreates the base containers) — and hit bare
> `https://developer.vbox`. Only one webui worktree can be served this way at a
> time; repoint back to primary (`docker compose up -d --force-recreate web
> angular-ui` with `NS_WEB_UI_DIR` unset) when done.

## Inputs

- **`<slug>`** — kebab-case feature descriptor. Required.
- Registry `/Users/lhsiao/ns/git/devbox-ui/.devenv-slots.json` maps slug → slot
  (gitignored, created on first use). Re-invoking the same slug reuses its SLOT;
  two different slugs never share one.

## Step 1: Resolve the worktree

Primary checkout: `/Users/lhsiao/ns/git/webui`. Worktree lives at
`/Users/lhsiao/ns/git/webui-<slug>` (parent dir of primary — never edit inside
primary).

```bash
SLUG=<slug>
git -C /Users/lhsiao/ns/git/webui worktree add \
  /Users/lhsiao/ns/git/webui-$SLUG -b pr/ENG-XXXXXX/$SLUG   # or reuse existing
WORKTREE=/Users/lhsiao/ns/git/webui-$SLUG
git -C "$WORKTREE" rev-parse --abbrev-ref HEAD   # confirm branch
```

> Re-grep every target symbol INSIDE the worktree before any Read-by-offset or
> Edit — the worktree sits on a different commit than primary; line numbers
> recorded during primary exploration drift (hundreds of lines is common).

## Step 2: Assign the SLOT

```bash
SLUG=<slug>
REG=/Users/lhsiao/ns/git/devbox-ui/.devenv-slots.json
[ -f "$REG" ] || echo '{}' > "$REG"
SLOT=$(python3 - "$REG" "$SLUG" <<'PY'
import json,sys
reg,slug=sys.argv[1],sys.argv[2]
d=json.load(open(reg))
if slug not in d:
    used=set(d.values()); s=1
    while s in used: s+=1
    d[slug]=s; json.dump(d,open(reg,'w'),indent=2)
print(d[slug])
PY
)
WEB_TLS=$((8443+SLOT)); ANGULAR=$((4200+SLOT)); PROXY_PORT=$((9797+SLOT))
echo "slug=$SLUG slot=$SLOT web_tls=$WEB_TLS proxy=$PROXY_PORT"
```

## Step 3: Worktree one-time setup (gitignored, not covered by `git worktree add`)

```bash
# 1. vendor/ — a REAL COPY, never a symlink. Symlinking causes
#    "Cannot redeclare rangeMatch()" — CodeIgniter's helper loader
#    double-includes via the symlink's resolved path back into primary. No
#    symlink variant works (including `git worktree add --detach`) — copy.
rsync -a --exclude='.git' \
  /Users/lhsiao/ns/git/webui/src/webui/system_framework/vendor/ \
  "$WORKTREE/src/webui/system_framework/vendor/"
mkdir -p "$WORKTREE/src/webui/system_framework/company_icons" \
         "$WORKTREE/src/webui/system_framework/company_logos"

# 2. neo/node_modules — symlink is fine (no CodeIgniter-style double-load), but
#    ONLY if lockfiles are byte-identical. A mismatch silently serves the wrong
#    dep tree — verify first, abort on any diff.
diff /Users/lhsiao/ns/git/webui/src/webui/neo/package-lock.json \
     "$WORKTREE/src/webui/neo/package-lock.json" \
  && ln -s /Users/lhsiao/ns/git/webui/src/webui/neo/node_modules \
     "$WORKTREE/src/webui/neo/node_modules"

# 3. dev-lazy Angular bundle — build once.
cd "$WORKTREE/src/webui/neo"
node --max_old_space_size=8192 ./node_modules/@angular/cli/bin/ng build \
  --configuration devLazy \
  --output-path ../system_framework/UI_Layer/dist/dev-lazy \
  --deploy-url /UI_Layer/dist/dev-lazy/
```

Re-run step 3's build after any Angular source change (~2–3 min). For ongoing
iteration, run watch mode instead of a one-shot build:

```bash
cd "$WORKTREE/src/webui/neo"
export NODE_OPTIONS=--max_old_space_size=8192
npm run dev:watch-lazy -- --source-map=false   # run in background
```

Steps 1–2 above are one-time per worktree.

## Step 4: Bring up per-slug `web` + `angular-ui` on the shared network

**Precondition:** the base `devbox-ui` stack is already up (`docker compose ps`
shows `mariadb`, `assets`, etc. healthy) — it owns the seeded DB, the seeded named
volumes, and the `devbox-ui_default` network the per-slug containers join.

```bash
cd /Users/lhsiao/ns/git/devbox-ui
OVR="compose.$SLUG.override.yml"
cat > "$OVR" <<YAML
networks:
  default:
    name: devbox-ui_default
    external: true
volumes:
  nginx-sites-active: { external: true, name: devbox-ui_nginx-sites-active }
  company-icons-volume: { external: true, name: devbox-ui_company-icons-volume }
  company-logos-volume: { external: true, name: devbox-ui_company-logos-volume }
  help-docs-volume: { external: true, name: devbox-ui_help-docs-volume }
services:
  web:
    container_name: web-$SLUG
    ports: !override ["$WEB_TLS:443"]
  angular-ui:
    container_name: angular-ui-$SLUG
    ports: !override ["$ANGULAR:80"]
YAML

NS_WEB_UI_DIR=/Users/lhsiao/ns/git/webui-$SLUG \
  docker compose -p webui-$SLUG -f docker-compose.yml -f "$OVR" \
  up -d --force-recreate --no-deps web angular-ui
```

> Verify external volume names against your machine first —
> `docker volume ls | grep devbox-ui` — the `devbox-ui_` prefix is the base
> project name; adjust if the base stack runs under a different `-p`.
>
> The `!override` tag on `ports:` is required (Compose v2.24+, confirmed on
> v2.40.3) — without it, `docker compose -f base.yml -f override.yml`
> CONCATENATES the two files' `ports:` lists instead of replacing them, so the
> per-slug container also tries to claim the base stack's port (`4200`, `443`)
> and fails with `Bind for :::4200 failed: port is already allocated`.

`--force-recreate` is required — the bind-mount source path is fixed at container
creation, not re-read on a plain restart. Verify the mount and DB reachability:

```bash
docker inspect web-$SLUG \
  --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' \
  | grep system_framework
docker exec web-$SLUG getent hosts mariadb   # resolves → base db container IP
```

No DB seeding needed — every slug shares the base stack's single seeded mariadb.

## Step 5: Apply the `rbac-css` stash (login prerequisite, not cosmetic)

Without this, login fails outright with "We encountered a backend error" — this is
a login gate, not a styling issue. Apply to the worktree working tree temporarily
(uncommitted); discard in teardown.

```bash
cd "$WORKTREE"
git stash list | grep rbac-css        # find the index, usually stash@{1}
git stash apply "stash@{1}"           # keeps the stash entry; only applies
```

## Step 6: Bypass the cert-rotation dashboard blocker

The authenticated dashboard hangs on "We seem to be experiencing some issues
currently" unless `enable_cert_rotation_notice` is force-disabled — there's no
backend for `RPMGMTSERVICE`/`AUTHMGMTSERVICE` in this devbox, so
`Cert_rotation.php`'s SAML-forward-proxy call never resolves.
`HTTP_DEV_ENVIRONMENT` being on locally lets `NSConfig::getControlConfig()` honor a
per-session control-flag cookie override — set it before navigating anywhere:

```bash
playwright-cli -s=<slug> cookie-set control_ENABLE_CERT_ROTATION_NOTICE 0 \
  --domain developer.vbox --path /
```

## Step 7: Navigate to a Settings sub-page correctly

Two non-obvious requirements, confirmed for Steering Configuration — apply the
same pattern to other `/settings/*` pages:

1. **Use `view`/`subview` query params**, not a bare route hash:
   ```
   #/settings/steering-configuration?view=steering_config&subview=summary
   ```
   A bare `#/settings/steering-configuration` with no query params can fail to
   resolve correctly.

2. **Navigate twice.** The first navigation to a Settings sub-page routes you back
   to `#/dashboard` — expected, not a failure. Re-issue the same hash assignment a
   second time and it lands correctly:
   ```bash
   playwright-cli -s=<slug> eval "() => { window.location.hash = '<hash>'; }"
   sleep 4
   playwright-cli -s=<slug> eval "() => { window.location.hash = '<hash>'; }"   # 2nd time — lands
   ```

## Step 8: Be patient with list-data loading

The page shell (sidebar, breadcrumb, title, static copy) renders immediately once
past Steps 6–7. The **list data itself** (e.g. Steering Configuration's
`getSteeringList`) can take well over a minute — this devbox proxies some data
calls toward external QA/NPE hosts that resolve slowly or retry before succeeding.

**Do not conclude "this page is broken" from a 4–6 second wait.** Poll for the
actual expected content for at least 60 seconds before treating it as a failure:

```bash
for i in $(seq 1 12); do
  sleep 5
  playwright-cli -s=<slug> eval "() => /configuration found|<expected text>/i.test(document.body.innerText)" \
    && break
done
```

A prior investigation in this environment initially concluded "Settings pages are
permanently blocked by devbox backend connectivity" — wrong; the page loads fine,
just slowly, and the earlier probe gave up after a few seconds.

## Driving a PHP endpoint directly (e2e validation without a flaky page load)

When the goal is validating a backend (PHP/CodeIgniter) change rather than a UI
render — e.g. a duplicate-guard, a save endpoint, anything reachable via an
authenticated POST — skip navigating the Angular page entirely and drive the
endpoint from an authenticated in-page `fetch()`. This sidesteps two devbox
footguns that make page-navigation-based validation flaky for some Settings
pages (parallel initial-load XHRs racing a CSRF token, and pages that take a
long time to mount their guard logic):

1. **Never recompute the CSRF token from `<meta name="ns-csrf-hash">`.** That
   meta tag is only correct at initial page bootstrap; `CsrfTokenStore` can
   refresh it later via `/login/getToken` without updating the tag, so it goes
   stale mid-session. A token built from the stale tag fails server-side
   validation (`NS_Security::csrf_verify()`) with "CSRF Token
   mismatch-CSRF attack suspected" (401), which can cascade into further 401s
   and a silent bounce to `#/login?reason=loggedout` — easy to misread as an
   RBAC/permission denial. Always pull the LIVE token instead:
   ```js
   const token = window.ns.getCsrfToken();
   ```
2. **Skip cookie-cloning into curl — POST via `page.evaluate` + `fetch()`
   instead.** The session cookie (`ci_session`) is `httpOnly`, so
   `document.cookie` returns `""`; you'd need `state-save`/`storageState()` to
   extract it for curl, and then get the `Content-Type`/CSRF field name exactly
   right. Simpler and more reliable to stay in-page:
   ```bash
   playwright-cli -s=<slug> eval "async () => {
     const token = window.ns.getCsrfToken();
     const body = new URLSearchParams({ /* ...endpoint fields..., */ token });
     const resp = await fetch('/settings/<controller>/<method>', {
       method: 'POST',
       credentials: 'same-origin',
       headers: {
         'Content-Type': 'application/x-www-form-urlencoded',
         'X-Requested-With': 'XMLHttpRequest', // required or PHP treats it as non-ajax
       },
       body: body.toString(),
     });
     return { status: resp.status, text: (await resp.text()).slice(0, 800) };
   }"
   ```
   This reuses the real session and the real live token with zero
   encoding/header risk, and still gives you the actual JSON error/success body
   to assert on.

   Worked example (ENG-868849, PR #18659 — `Clientconfiguration::saveClientConfig`'s
   group-scim-id duplicate guard). Curl-equivalent shown for readability — the
   call actually ran as the in-page `fetch()` above, reusing the live session
   cookie and live token; `<session>`/`<token>` are real per-request secrets,
   never paste them literally into a report:
   ```
   curl 'https://developer.vbox/settings/clientConfiguration/saveClientConfig' \
     -H 'Cookie: ci_session=<session>' \
     -H 'X-Requested-With: XMLHttpRequest' \
     --data-urlencode 'id=-1' \
     --data-urlencode 'name=E2E-Test-B-StaleName' \
     --data-urlencode 'ou_or_group=0' \
     --data-urlencode 'ou_or_group_name=UG2-renamed-simulated' \
     --data-urlencode 'group_scim_id=8f19eeea-47f7-455f-b264-06b821598e9f' \
     --data-urlencode 'token=<token>'
   ```
   Result — `HTTP 200`:
   ```json
   {"status":"error","netskopeRequestId":"...","errorCode":"General Error","errors":["Group already exists"],"warnings":[""]}
   ```
   Report the request AND the literal response body verbatim (not just
   "passed"/"rejected") — a PR reviewer (or the user) will ask for the raw
   curl+result if only given a prose summary; capture it the first time so you
   don't have to re-run the whole session to answer that follow-up.
3. **For a real before/after proof, do the counterfactual in the SAME live
   session.** Since PHP is live-mounted from the worktree, no rebuild is
   needed: `git checkout <parent-branch> -- <file-with-the-fix>` to temporarily
   strip the change, rerun the identical `fetch()` call and confirm the bug
   reproduces, then `git checkout HEAD -- <file>` to restore. Clean up any rows
   the counterfactual call inserted (check the tenant DB directly, e.g. `docker
   exec web mysql -h mariadb -u root -p1234 <tenant_db> -e "select ..."`) before
   moving on.

   Same worked example, fix stripped — result was `HTTP 500` with an empty
   body (an unrelated pre-existing crash later in the save path, not the
   guard rejecting anything). An empty/500 response is NOT itself proof the
   bug reproduced — confirm via the DB that the row actually got inserted:
   ```
   mysql> select id,name,ou_or_group,ou_or_group_name,group_scim_id from client_config;
   id=4  name=UG2_Config          ou_or_group=0  ou_or_group_name=UG2                        group_scim_id=8f19eeea-...
   id=6  name=E2E-Test-C-NoFix    ou_or_group=0  ou_or_group_name=UG2-renamed-simulated-2     group_scim_id=8f19eeea-...
   ```
   Row 6 shares `group_scim_id` with row 4 under a different
   `ou_or_group_name` — the exact collision the fix closes — confirming
   `validateData()` did not reject it before the unrelated crash. Delete the
   row, restore the fix, rerun once more to confirm the rejection is back.
4. **Confirm RBAC via `ms-rbac` directly if a page/action looks denied** —
   don't assume seed-data is missing. `curl localhost:3022/roles/<roleId> -H
   "x-netskope-tenantid: <id>" -H "x-netskope-user-role-id: <roleId>" -H
   "x-netskope-user-id: <email>" -H "x-netskope-trid: any-string"` returns the
   role's real `apiGroups` list with permissions — a bare curl without these
   headers 500s on an unrelated version-middleware check and can be
   misdiagnosed as "no permission data seeded".
5. **Feature flags have no cookie override (control flags do).** If the
   change under test is gated by a feature flag (not a control flag), the
   `control_<NAME>` cookie trick (see the cert-rotation section above) does
   NOT apply — feature flags are read from session data with no local DB
   row to flip. Fastest local override: a temporary `DEVBOX-TEMP`-tagged
   early-return in `_isFeatureEnabled()`
   (`application/helpers/show_feature_helper.php`) for the specific flag name,
   same pattern as the existing `isRegenerateNeeded()` session-driver
   workaround. Revert before finishing.

Confirmed end-to-end 2026-08-28 validating ENG-868849 (PR #18659,
`Clientconfiguration::saveClientConfig`'s new group-scim-id duplicate guard).

## Standard headless launch

```bash
playwright-cli -s=<slug> open   # headless by default — webui's browser-detection
                                 # gate rejects a literal HeadlessChrome UA, but
                                 # playwright-cli's chrome channel already avoids that
```

## Teardown

Remove only this env's two containers. **Never `down` the project** — the network
and named volumes are external/shared with the base stack; `down` on the per-slug
project leaves them alone, but `--volumes`/`--remove-orphans` would not, so avoid
those flags entirely.

```bash
SLUG=<slug>
docker rm -f web-$SLUG angular-ui-$SLUG
# discard the applied rbac-css working-tree changes (the stash entry survives):
cd /Users/lhsiao/ns/git/webui-$SLUG && git checkout -- <the rbac-css-modified files>
```

Freeing a slot for good: remove the slug's entry from
`/Users/lhsiao/ns/git/devbox-ui/.devenv-slots.json` and delete
`compose.<slug>.override.yml`.
