---
name: webui-devbox-playwright
description: >-
  Point devbox-ui's web container at a webui git worktree and run headless
  Playwright validation against Angular Settings pages (e.g. Steering
  Configuration) without mutating primary's git state. Covers the
  cert-rotation-notice cookie bypass and the view/subview query-param
  navigation quirk that make Settings sub-pages loadable locally.
user-invocable: true
allowed-tools:
  - Bash
  - Read
---

# webui devbox Playwright validation

Validate an Angular change in a webui worktree against the local `devbox-ui`
stack, headless, without the old commit → checkout-hash → stash-reapply dance.

## Prerequisites

- `devbox-ui` docker-compose stack already running (`cd
  /Users/lhsiao/ns/git/devbox-ui && docker compose ps`).
- A webui worktree with your change checked out.
- Playwright installed in a throwaway dir: `mkdir -p /tmp/pw-runner && cd
  /tmp/pw-runner && npm init -y && npm install playwright`.
- Credentials in `/Users/lhsiao/.claude/skills/mf-client-playwright/.env`
  (`NS_TEST_USERNAME`, `NS_TEST_PASSWORD`) — shared with the mf-client skill.

## One-time worktree setup

The worktree needs three things `git worktree add` doesn't give you (all
gitignored, so they don't come from git):

```bash
WORKTREE=/path/to/webui-worktree

# 1. vendor/ — a REAL COPY, never a symlink (symlinking causes
#    "Cannot redeclare rangeMatch()" — CodeIgniter's helper loader
#    double-includes via the symlink's resolved path back into primary).
rsync -a --exclude='.git' \
  /Users/lhsiao/ns/git/webui/src/webui/system_framework/vendor/ \
  "$WORKTREE/src/webui/system_framework/vendor/"
mkdir -p "$WORKTREE/src/webui/system_framework/company_icons" \
         "$WORKTREE/src/webui/system_framework/company_logos"

# 2. neo/node_modules — symlink is fine here (no CodeIgniter-style double-load).
#    Verify lockfiles are byte-identical first.
diff /Users/lhsiao/ns/git/webui/src/webui/neo/package-lock.json \
     "$WORKTREE/src/webui/neo/package-lock.json"
ln -s /Users/lhsiao/ns/git/webui/src/webui/neo/node_modules \
  "$WORKTREE/src/webui/neo/node_modules"

# 3. dev-lazy Angular bundle — build once in the worktree.
cd "$WORKTREE/src/webui/neo"
node --max_old_space_size=8192 ./node_modules/@angular/cli/bin/ng build \
  --configuration devLazy \
  --output-path ../system_framework/UI_Layer/dist/dev-lazy \
  --deploy-url /UI_Layer/dist/dev-lazy/
```

Re-run step 3 after any Angular source change in the worktree (~2–3 min).
Steps 1–2 are one-time per worktree.

## Point the web container at the worktree

```bash
cd /Users/lhsiao/ns/git/devbox-ui
NS_WEB_UI_DIR=/path/to/webui-worktree \
  docker compose up -d --force-recreate web
```

`--force-recreate` is required — the bind-mount source path is fixed at
container creation, not re-read on a plain restart. Verify with:

```bash
docker inspect web --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' \
  | grep system_framework
```

## Apply `rbac-css` in the worktree (login prerequisite, not cosmetic)

Without this stash, login fails outright with "We encountered a backend
error" — this is a *different* failure than anything downstream, so if you
see this message specifically, check the stash first.

```bash
cd /path/to/webui-worktree
git stash list | grep rbac-css   # find the index, usually stash@{1}
git stash apply "stash@{1}"
```

Discard it from the worktree's working tree when done
(`git checkout -- <the 2 modified files>`) — never commit it.

## Bypass the cert-rotation dashboard blocker

The authenticated dashboard hangs on "We seem to be experiencing some issues
currently" unless `enable_cert_rotation_notice` is force-disabled. There's no
backend for `RPMGMTSERVICE`/`AUTHMGMTSERVICE` in this devbox, so
`Cert_rotation.php`'s SAML-forward-proxy call never resolves. `HTTP_DEV_ENVIRONMENT`
being on locally lets `NSConfig::getControlConfig()` honor a per-session
control-flag cookie override — set it before navigating anywhere:

```js
await context.addCookies([{
  name: 'control_ENABLE_CERT_ROTATION_NOTICE',
  value: '0',
  domain: 'developer.vbox',
  path: '/',
}]);
```

## Navigate to a Settings sub-page correctly

Two non-obvious requirements, confirmed working for Steering Configuration —
apply the same pattern to other `/settings/*` pages:

1. **Use the `view`/`subview` query params**, not a bare route hash:
   ```
   #/settings/steering-configuration?view=steering_config&subview=summary
   ```
   A bare `#/settings/steering-configuration` with no query params can fail
   to resolve correctly.

2. **Navigate twice.** The first navigation to a Settings sub-page routes you
   back to `#/dashboard` — this is expected, not a failure. Re-issue the same
   hash assignment a second time and it lands correctly:
   ```js
   await page.evaluate((hash) => { window.location.hash = hash; }, STEERING_HASH);
   await page.waitForTimeout(4000);
   await page.evaluate((hash) => { window.location.hash = hash; }, STEERING_HASH); // 2nd time — lands
   ```

## Be patient with list-data loading — don't declare failure early

The page shell (sidebar, breadcrumb, page title, static copy) renders
immediately and correctly once you're past the two blockers above. The
**list data itself** (e.g. the Steering Configuration list, backed by
`getSteeringList`) can take well over a minute to populate — this devbox
proxies some data calls toward external QA/NPE hosts that resolve slowly or
retry before succeeding, not necessarily failing outright.

**Do not conclude "this page is broken" from a 4–6 second wait.** Poll for
the actual expected content (e.g. `"configuration found"` text, or a known
row selector) for at least 60 seconds before treating it as a genuine
failure:

```js
let found = false;
for (let i = 0; i < 12; i++) {
  await page.waitForTimeout(5000);
  const bodyText = await page.locator('body').innerText().catch(() => '');
  if (/configuration found|<expected text>/i.test(bodyText)) { found = true; break; }
}
```

A prior investigation in this environment initially concluded "Settings pages
are permanently blocked by devbox backend connectivity" — that conclusion was
wrong; the underlying page loads fine, just slowly, and the earlier probe
gave up after a few seconds.

## Standard headless launch config

Reuses the same headless-Chrome workaround as `mf-client-playwright` (the
webui browser-detection gate rejects the literal `HeadlessChrome` UA string):

```js
const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--no-sandbox', '--ignore-certificate-errors'],
});
const context = await browser.newContext({
  ignoreHTTPSErrors: true,
  viewport: { width: 1920, height: 1080 },
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
});
```

Login flow (locallogin form + `#username`/`#password`/`#btn-sign-in`, wait
for hash to leave `/login`, dismiss `text=skip this step` wizard if present)
is identical to `mf-client-playwright`'s pattern — reuse that skill's login
snippet rather than duplicating it here.

## Teardown

```bash
cd /Users/lhsiao/ns/git/devbox-ui
docker compose up -d --force-recreate web   # NS_WEB_UI_DIR unset → back to primary
cd /path/to/webui-worktree
git checkout -- <the rbac-css-modified files>   # discard, keep the stash entry
```
