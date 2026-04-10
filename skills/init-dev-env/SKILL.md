---
name: init-dev-env
description: >-
  Set up the local webdev environment: build webui, start mf-client dev server,
  start development proxy, and output the proxy URL for testing.
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Grep
---

# Init Dev Env

Spin up the full local web-development stack so the user can test in a browser.

## Steps

Run each step sequentially — later steps depend on earlier ones being ready.

### 1. Build webui (dev:webui alias)

```bash
cd /Users/lhsiao/ns/git/webui/src/webui/neo && export NODE_OPTIONS=--max_old_space_size=8192 && npm run build:dev-lazy -- --source-map=false
```

This is a long-running build. Run it and wait for completion before proceeding.

### 2. Start mf-client dev server

```bash
cd /Users/lhsiao/ns/git/netskope-ng-base/frontends/mf-client && npm run start:dev
```

Run this in the background — it stays running as a dev server.

### 3. Start the development proxy

Before starting, read the fallback server config so the user knows which tenant
is being proxied:

```bash
cat /Users/lhsiao/ns/git/development-proxy/src/config.ts
```

Display the **uncommented** `host` value from `fallbackServer` so the user can
confirm the correct tenant.

Then start the proxy:

```bash
cd /Users/lhsiao/ns/git/development-proxy && npm run dev
```

Run this in the background — it stays running.

### 4. Output the testing URL

The development proxy listens on **http://localhost:9797**. Print this URL along
with the active fallback tenant so the user has a single summary:

```
Dev environment ready!

  Proxy URL : http://localhost:9797
  Tenant    : <host from fallbackServer config>

Open the proxy URL in your browser to test.
```
