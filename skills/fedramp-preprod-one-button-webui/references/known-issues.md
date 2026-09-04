# FedRAMP PreProd deploy Jenkins -- known issues

Field-tested. Source: DO wiki "Fedramp Pre-prod self-service deployments"
(page 4336386132), plus live verification of the one_button_webui pipeline.

## The deploy tunnel is NOT the rancher tunnel

Most common confusion. The deploy Jenkins lives behind a floating IP that is
NOT in the rancher subnet:

| target | route |
|---|---|
| deploy Jenkins fed02 (primary) | `10.149.192.172/32` |
| deploy Jenkins fed01 (DR) | `10.159.195.6/32` |
| rancher (kubeconfig skill) | `10.246.0.0/16` |

A tunnel that routes only `10.246.0.0/16` reaches rancher but NOT the deploy
Jenkins (curl to it just times out / HTTP 000). Route the Jenkins IP, or route
both in one tunnel:

```bash
tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
  -r knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net \
  10.149.192.172/32 10.246.0.0/16
```

Observed: a `/32` host route added by tshuttle may not show under
`netstat -rn | awk '/UCSc/'` (that only lists the /16-style entries), yet the
host is still reachable. Trust a curl to `/login` (200/403) over the route
listing.

## fed02 vs fed01

fed02 (DFW2) = **Primary** -- deploy here. fed01 (IAD3) = **DR**, only when the
DR stack is made active. Each has its own Jenkins floating IP and its own
tshuttle jump-host command. (Note: this is the OPPOSITE default from the plain
tsh/rancher setup, where fed01 is the "active" MP but flaky -- for deploy,
fed02 is genuinely the primary Jenkins.)

## Jenkins UI freezes / times out

DO wiki FAQ, in order:
1. Disable Juniper (or any VPN that intercepts DNS).
2. Clean the packet filter (macOS): `sudo pfctl -F all`
3. Delete the stale route and retry tshuttle:
   - primary: `sudo route -n delete 10.149.192.172`
   - DR: `sudo route -n delete 10.159.195.6`
4. `tsh logout` then re-login and retry.
5. Disable NSClient and retry (time-offset teleport issue workaround).

## "refused to connect" / permissions

- "cdjenkinsfedh... refused to connect" can be a teleport time-offset issue
  (gravitational/teleport#4192). Report in `#teleport` with debug logs:
  `tsh login --proxy teleport.govskope.io -d`.
- Permissions error on `tsh ssh`: set your teleport login explicitly --
  `export TELEPORT_LOGIN=<username>` where `<username>` is your fedramp okta
  username BEFORE the `@govskope.us` part.

## Tunnel dies silently

The tshuttle process can drop (terminal closed, teleport hiccup) while the
rancher tunnel on a different route stays up -- so rancher works but the deploy
Jenkins suddenly times out. Re-check with a curl to the Jenkins `/login`; if
000, the deploy tunnel is gone, rebuild it.

## one_button_webui: do NOT click Build to "test"

There is no safe dry-run of the trigger itself from the agent's side. Verifying
access = logging in and SEEING the job + its parameters. Actually building
deploys into FedRAMP. `VP_APPROVAL=FALSE` allows a dryrun WITHIN a real build
run, but that is still a deliberate, user-initiated action with a real TICKET,
not a connectivity test.

## Pipeline reachability quick ref

- Primary: `https://cdjenkinsfedh.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net/`
- DR: `https://cdjenkinsfedh.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net/`
- Job: `.../job/one_button_webui/`
