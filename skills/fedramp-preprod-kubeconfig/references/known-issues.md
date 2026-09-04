# FedRAMP PreProd k8s access -- known issues & rescue

Field-tested notes. Several correct the official Confluence page
"How to Handle Compliance (FedRAMP/PBMM) Tickets" / "Set up (and use)
Teleport in local", which have stale details.

## Corrections to Confluence

| Confluence says | Reality |
|---|---|
| jump host `knode01.c1.fed01-**dp**-preprod.nc1.iad3...` | it's `-**mp**-preprod` (management plane), not `dp`. Confluence has the wrong node. |
| use fed01 (IAD3) | fed01 is often slow/flaky. **Use fed02 (DFW2, DR site) first**; fall back to fed01. |
| (implies kubectl just works) | kubectl works but is **slow** over the tunnel; the `-kmaster0X` direct contexts never work (wrong subnet). |

Always confirm the live jump-host name rather than trusting a doc:

```bash
tsh ls --cluster fedhigh-preprod | grep 'knode01.c1.fed0'
```

## Tunnel won't come up -- full reset sequence

From Confluence, and it really does sometimes need 2-3 tries + a reboot.
This is a known pain point, not a misconfiguration. Run in order (user does
the sudo/reboot steps):

1. Connect to **Juniper VPN**.
2. Turn **off** NS Client (Netskope client) -- it hijacks routing.
3. Log out of Compliance Okta (top-right) at
   `https://nskp-fed.okta-gov.com/app/UserHome`.
4. `tsh logout`
5. Clear leftover routes (the `rclean` helper, or by hand):
   ```bash
   for ip in $(netstat -rn | awk '/UCSc/ {print $1}'); do sudo route delete "$ip"; done
   ```
6. **Reboot** the laptop (network changes often need a reboot to take effect).
7. `tsh login --proxy teleport.betagovskope.io`
8. Bring the tunnel up again (fed02-first):
   ```bash
   tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
     -r knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net 10.246.0.0/16
   ```

Verify with `ping rancher.betagovskope.io` (a "Can't find host" from nslookup
can still mean it's working; "No route to host" means it isn't).

## "No route to host" but I thought the tunnel was up

The tshuttle process died (check `ps aux | grep tshuttle`) but left the
`10.246/16` reject route (`!`) behind. That route makes every packet fail fast
with "No route to host" -- looks like a network problem, is actually a dead
tunnel + stale route. Fix: clear the route (step 5 above) and rebuild.

## kubectl times out / super slow

Expected. The tunnel is SSH-tunneled -> high latency, low throughput.

- Cluster-wide `get ns` (~147 KB) measured at 20-30s, sometimes > timeout.
- Scope everything: `-n <namespace>`, name the resource, `--request-timeout=60s`.
- First call after downloading a kubeconfig runs full API discovery (many
  small round-trips) and is the slowest; subsequent scoped calls are quicker.
- Only the rancher-proxy context works. The `-kmaster0X` context points at
  `198.18.x:6443`, which is not inside the tunnel route `10.246.0.0/16`, so it
  always times out. `kubectl config use-context <cluster-name>` (no `-kmaster`).

## nsk returns 401

Token under `[fedramp-preprod]` in `~/.nsk/configuration` is missing, still the
placeholder, or expired. Regenerate the Rancher API key
(`https://rancher.betagovskope.io/dashboard` -> Account & API Keys) and paste
the new bearer token in. The tunnel must be up for `nsk` to reach Rancher at
all -- a 401 (vs a hang) actually confirms the tunnel is working.

## WebUI PreProd MP clusters

| Cluster | Site | Role |
|---|---|---|
| `stork-fed01-mp-preprod-iad3-nc1` | IAD3 | active |
| `stork-fed02-mp-preprod-dfw2-nc1` | DFW2 | DR (use as jump host first) |

PBMM PreProd (`stork-pbmm01-mp-preprod-...`) exists too; add to
`~/.nsk/download_kubeconfigs.sh` if you need it.
