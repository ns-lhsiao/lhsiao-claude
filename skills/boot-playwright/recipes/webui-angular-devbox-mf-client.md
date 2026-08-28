# Recipe: webui-angular-devbox-mf-client

Layers on top of `webui-angular-devbox.md` — **read and execute that recipe first**
to bring up the base devbox-ui stack (worktree, SLOT, `web`/`angular-ui`
containers, rbac-css stash, cert-rotation bypass). This file only covers the
mf-client-specific delta: the mf-client dev server and the development proxy.

Read `../SKILL.md` first for the shared session/login/nav/reporting mechanics.

## Port offsets (adds to the base recipe's SLOT)

| Thing                  | Base   | Offset expr        |
|-------------------------|--------|--------------------|
| mf-client dev server   | 8017   | `8017 + SLOT*100`  |
| development-proxy      | 9797   | `9797 + SLOT`       |

```bash
MFCLIENT_PORT=$((8017+SLOT*100)); PROXY_PORT=$((9797+SLOT))
```

`developer.vbox` resolves to `127.0.0.1`, but the base recipe's `web` container
publishes TLS on `8443+SLOT` — so the dev-proxy for this env must forward to
`https://developer.vbox:<WEB_TLS>`, not the bare hostname.

## Resolve the mf-client + development-proxy worktrees

Primary checkouts:
- mf-client: `/Users/lhsiao/ns/git/netskope-ng-base/frontends/mf-client` (a nested
  git repo inside the netskope-ng-base checkout)
- development-proxy: `/Users/lhsiao/ns/git/development-proxy`

Worktrees live at `/Users/lhsiao/ns/git/mf-client-<slug>` and
`/Users/lhsiao/ns/git/development-proxy-<slug>` — same slug as the base recipe's
webui worktree (this is the triad). Create off the default base with the project's
branch convention (`pr/ENG-XXXXXX/<slug>`) if absent; otherwise use as-is.

## Start mf-client dev server (worktree, offset port)

```bash
cd /Users/lhsiao/ns/git/mf-client-$SLUG
PORT=$MFCLIENT_PORT WDS_SOCKET_PORT=$MFCLIENT_PORT \
  FAST_REFRESH=false WDS_HOT=false BROWSER=none npm run start:dev
```

Run in the background. `FAST_REFRESH=false WDS_HOT=false` avoids the
`originalFactory.call is not a function` HMR crash.

## Start the development proxy (worktree, offset port + base recipe's web TLS)

The proxy hardcodes `port = 9797` in `src/main.ts` and `devServer.url =
https://developer.vbox`. Edit both in the worktree copy (uncommitted, local to
this env):

```bash
cd /Users/lhsiao/ns/git/development-proxy-$SLUG
sed -i '' "s#const port = 9797;#const port = $PROXY_PORT;#" src/main.ts
sed -i '' "s#url: \"https://developer.vbox\"#url: \"https://developer.vbox:$WEB_TLS\"#" src/main.ts
```

Set the fallback tenant: read `src/config.ts`, show the user the active
(uncommented) `fallbackServer.host`, confirm it's correct (production suffixes
`govskope.ca`/`govskope.us` are rejected by the proxy), then:

```bash
npm run dev   # run in background
```

## Wait for the micro-frontend

mf-client loads via module federation, 30–60s. Wait for a known readiness element
before asserting anything:

```bash
playwright-cli -s=<slug> eval "() => !!document.querySelector('[data-testid=\"filter-toggle-advanced\"]')"
```

## Output the per-env summary

```
Dev env "<slug>" ready (slot <SLOT>):

  Proxy URL   : http://localhost:<PROXY_PORT>
  Tenant      : <host from fallbackServer config>
  webui build : /Users/lhsiao/ns/git/webui-<slug>  (dev-lazy, watching)
  mf-client   : http://localhost:<MFCLIENT_PORT>
  devbox web  : https://developer.vbox:<WEB_TLS>  (container web-<slug>)

Open the proxy URL to test. Other slugs run on their own slots concurrently.
```

## Teardown

Base recipe covers `web`/`angular-ui` container + worktree cleanup. Additionally:

```bash
SLUG=<slug>
# stop the backgrounded mf-client / proxy processes for this env
# discard the uncommitted proxy port/url edits:
cd /Users/lhsiao/ns/git/development-proxy-$SLUG && git checkout -- src/main.ts
```
