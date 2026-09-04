---
name: fedramp-preprod-kubeconfig
description: >
  Set up kubectl / k8s access to the FedRAMP PreProd management-plane clusters
  (stork-fed01-mp-preprod-iad3-nc1, stork-fed02-mp-preprod-dfw2-nc1) so you can
  check pod health, read logs, or verify a patch (e.g. FIPS check) after a
  deploy. Use when the user says: "setup fedramp preprod kubeconfig",
  "connect to fedramp preprod k8s", "get fedramp preprod credentials",
  "fedramp preprod rancher", "kubectl on fed preprod", "check pods on
  fed-mp-preprod", "拿 fedramp preprod credential", "連 fedramp preprod",
  "rancher.betagovskope.io 連不上", "fedramp preprod rancher tunnel 壞了",
  or is blocked bringing up the tshuttle tunnel / nsk kubeconfig for FedRAMP
  PreProd. Guides through teleport login, the tshuttle tunnel (fed02-first),
  the Rancher API key, nsk kubeconfig download, and kubectl verification, and
  runs a read-only diagnostic that says exactly which step is blocking you.
  If the user wants to DEPLOY a patch (Jenkins / one_button_webui / cdjenkinsfedh),
  use fedramp-preprod-one-button-webui instead -- a different tunnel + access path. If the
  request is a bare "fedramp preprod 連不上 / tunnel 壞了" with no rancher-vs-jenkins
  signal, ask which one before picking. Does NOT deploy patches.
  Does NOT cover FedRAMP/PBMM PROD (US-citizen + NOC only) or Kibana.
---

# fedramp-preprod-kubeconfig

Gets you from nothing to a working `kubectl` against the FedRAMP **PreProd** MP
clusters. Anyone (even non-US) can access PreProd, unlike Prod.

This is a **guide + diagnostic** skill, not a one-shot script: the two commands
that actually build the tunnel (`tshuttle`) and clear stale routes
(`route delete`) both need `sudo`, so they must be run by the user in a real
terminal. The agent's job is to run the read-only diagnostic, tell the user
exactly which step is blocking, and hand them the precise next command.

## Hard rules

- **Never run `sudo` on the user's behalf, and never try to background
  `tshuttle`.** It needs an interactive sudo prompt and must stay in the
  foreground of a terminal the user controls. Hand the command over; do not
  attempt it via the Bash tool (it will fail with "a terminal is required").
- **Never print or ask the user to paste the Rancher API token into the
  conversation.** The token is a long-lived bearer credential. The user edits
  `~/.nsk/configuration` themselves. The diagnostic reads only whether a
  non-placeholder token exists, never its value.
- **`tsh login` opens a browser for Okta-gov and cannot be backgrounded by the
  agent** -- it times out waiting for the callback. Give the user the command
  to run themselves.

## First move: run the diagnostic

Resolve the script path once, then run it. It is read-only (no sudo, no
mutation) and tells you which of the 5 steps is blocking:

```bash
DIAG=$(ls \
  ~/.claude/skills/fedramp-preprod-kubeconfig/scripts/diagnose.sh \
  .claude/skills/fedramp-preprod-kubeconfig/scripts/diagnose.sh \
  2>/dev/null | head -1)
zsh "$DIAG"
```

It prints an `[OK]/[FAIL]` line per step and a single "Next step" block with the
exact command to unblock. Relay that to the user. Re-run after each step they
complete.

## The 5 steps (what the diagnostic checks)

### 1. Teleport login

```bash
tsh login --proxy teleport.betagovskope.io
```

Opens a browser -> Okta-gov. User must complete it (has a short timeout). This
is a **separate** login from commercial `teleport.netskope.io`; both profiles
coexist in `tsh status`. Valid ~12h.

### 2. tshuttle tunnel (fed02-first)

Routes `10.246.0.0/16` through a teleport SSH jump host so
`rancher.betagovskope.io` becomes reachable. Run in a terminal that **stays
open** (foreground, holds the tunnel):

```bash
# fed02 (DFW2, DR site) first -- empirically more reliable than fed01
tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
  -r knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net 10.246.0.0/16

# fed01 (IAD3, active) fallback
tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
  -r knode01.c1.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net 10.246.0.0/16
```

If it says `route: File exists` / `add net 10.246.0.0: File exists`, a stale
reject route is in the way -- see step 3, then rerun.

If it says `target host ... is offline or does not exist`, the jump-host name
drifted. Get the current name: `tsh ls --cluster fedhigh-preprod | grep knode01.c1.fed0`.

### 3. Clear a stale route (only when the tunnel is down)

tshuttle leaves a `10.246/16` reject route (`!`) behind on exit; it blocks the
next tunnel. Clear it (user runs; needs sudo):

```bash
sudo route delete 10.246.0.0/16
```

The diagnostic treats this route as benign when the tunnel is already up.

### 4. Rancher API key -> ~/.nsk/configuration

`nsk` talks to the Rancher API and needs a bearer token per profile. With the
tunnel up:

1. Browser: `https://rancher.betagovskope.io/dashboard`
   -> avatar (top-right) -> **Account & API Keys** -> **Create API Key**
   -> scope "no scope", copy the **Bearer Token** (`token-xxxxx:...`, shown once).
2. User edits `~/.nsk/configuration`, replacing the placeholder under
   `[fedramp-preprod]`:

   ```ini
   [fedramp-preprod]
   endpoint = "https://rancher.betagovskope.io/v3"
   token = "token-xxxxx:<the long string>"
   insecure = false
   ```

Verify (agent can run this; safe, read-only):

```bash
nsk cluster list --profile fedramp-preprod
```

401 -> token expired/wrong. A list of clusters -> good. The WebUI MP clusters
are `stork-fed01-mp-preprod-iad3-nc1` and `stork-fed02-mp-preprod-dfw2-nc1`.

### 5. Download kubeconfig + verify kubectl

```bash
# one cluster
nsk cluster kubeconfig --profile fedramp-preprod --name stork-fed02-mp-preprod-dfw2-nc1

# or all WebUI MP clusters at once (helper populated with the right names)
~/.nsk/download_kubeconfigs.sh fedramp_preprod
```

The file lands in `~/.nsk/<cluster>.yaml` (helper also copies to `~/.kube/`).

**Use the rancher-proxy context only.** Each kubeconfig has two contexts:
- `<cluster-name>` -> `server: https://rancher.betagovskope.io/k8s/clusters/c-xxxx` -- **works** (goes through the tunnel).
- `<cluster-name>-kmaster0X` -> `server: https://198.18.x:6443` -- **always times out**; `198.18.x` is NOT in the tunnel route (`10.246/16`). Do not use.

```bash
export KUBECONFIG=~/.nsk/stork-fed02-mp-preprod-dfw2-nc1.yaml
kubectl config use-context stork-fed02-mp-preprod-dfw2-nc1   # NOT the -kmaster one
kubectl get pods -n <webui-namespace> --request-timeout=60s
```

## kubectl over the tunnel is SLOW -- this is expected

The tunnel is an SSH-tunneled route, so latency is high and throughput low.
Measured: a cluster-wide `namespaces` list (~147 KB) took 20-30s and sometimes
timed out. Small requests (discovery, single-namespace pod list) are fine.

- Always scope: `-n <namespace>`, name a specific resource. Avoid cluster-wide
  `get all` / unscoped `get ns`.
- Add `--request-timeout=60s` so kubectl doesn't give up mid-transfer.
- First command after download is slowest (API discovery). Don't read one
  timeout as "it's broken" -- rerun scoped.

## When things are stuck: rescue

If the tunnel won't come up after clearing the route, see
`references/known-issues.md` for the full teleport/route/NS-client reset
sequence (it sometimes takes a couple of tries + a reboot -- a known pain
point, not misconfiguration).

## Scope / non-goals

- **Deploy a patch to FedRAMP PreProd?** Different path entirely -- Jenkins
  (`cdjenkinsfedh.fed02-mp-preprod...`) + okta group
  `fedh-cdjenkins-preprod-webui-ncd` + YubiKey. No tunnel/credential needed.
  Only the post-deploy FIPS verification (`dpkg -l | grep fips` inside the
  webui pod) comes back here.
- **FedRAMP/PBMM PROD**: not covered. Inside the boundary; US-citizen + NOC
  only. Ask NOC in `#gov-services_ngs-channel`.
- **Kibana / ELK logs**: not covered here.
