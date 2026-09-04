---
name: fedramp-preprod-one-button-webui
description: >
  Deploy a WebUI patch to the FedRAMP PreProd management-plane stacks via the
  self-service one_button_webui Jenkins pipeline. Use when the user says:
  "deploy patch to fedramp preprod", "fedramp preprod deploy", "run
  one_button_webui on fed preprod", "deploy webui to fed02-mp-preprod",
  "部署 patch 到 fedramp preprod", "fedramp preprod jenkins 連不上", "cdjenkinsfedh
  連不上", or is bringing up / troubleshooting the deploy-Jenkins tunnel for
  FedRAMP PreProd. Guides through teleport login, the deploy-Jenkins tunnel
  (routes the Jenkins floating IP, NOT the rancher subnet), okta-group +
  YubiKey access, and the one_button_webui parameters, and runs a read-only
  diagnostic that confirms reachability. Does NOT trigger builds automatically
  (outward action -- needs a real in-flight patch + explicit go-ahead). For
  getting kubectl/rancher access (pod health, post-deploy FIPS check), see the
  fedramp-preprod-kubeconfig skill. Does NOT cover FedRAMP/PBMM PROD (NGS/NOC
  deploys prod).
---

# fedramp-preprod-one-button-webui

Deploys a WebUI patch to FedRAMP **PreProd** via the self-service
`one_button_webui` Jenkins pipeline. Distinct from the kubeconfig/rancher path:
different tunnel target, different access (okta group + YubiKey, no API key).

This is a **guide + diagnostic** skill. `tshuttle` and `route delete` need
`sudo` (run by the user in a real terminal); the Jenkins login needs a browser
+ YubiKey. The agent runs the read-only diagnostic, says which step blocks, and
hands over the exact command.

## Hard rules

- **NEVER trigger a build.** Triggering `one_button_webui` deploys code into a
  FedRAMP environment -- an outward, hard-to-reverse action. Only the user
  clicks Build, only with a real in-flight patch and explicit go-ahead. The
  agent verifies access and prepares parameters; it does not deploy.
- **Never run `sudo` for the user, never background `tshuttle`.** Interactive
  sudo + must stay foreground. Hand the command over.
- **`tsh login` and the Jenkins UI login open a browser** (Okta-gov + YubiKey);
  the agent can't complete them. Give the user the command / URL.

## Deploy tunnel vs kubeconfig tunnel (read this first)

The two FedRAMP PreProd paths route DIFFERENT targets:

| | deploy (this skill) | kubeconfig skill |
|---|---|---|
| tunnel route | `10.149.192.172/32` (fed02 Jenkins floating IP) | `10.246.0.0/16` (rancher subnet) |
| jump host | fed02 knode01 (same) | fed02 knode01 (same) |
| access | okta group `fedh-cdjenkins-preprod-webui-ncd` + **YubiKey** | rancher API key |
| target | `cdjenkinsfedh.fed02-mp-preprod...` | `rancher.betagovskope.io` |

They can share ONE tunnel by routing both:
```bash
tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
  -r knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net \
  10.149.192.172/32 10.246.0.0/16
```
Deploy needs rancher too, for the post-deploy FIPS check (that step lives in
the kubeconfig skill), so routing both up front saves a rebuild.

## First move: run the diagnostic

```bash
DIAG=$(ls \
  ~/.claude/skills/fedramp-preprod-one-button-webui/scripts/diagnose.sh \
  .claude/skills/fedramp-preprod-one-button-webui/scripts/diagnose.sh \
  2>/dev/null | head -1)
zsh "$DIAG"
```

Read-only. Checks tsh session, /etc/hosts mapping, and Jenkins reachability,
then prints the exact next command. Okta-group + YubiKey can only be confirmed
by the user logging into the UI (the script says so).

## Access setup (one-time)

- **Teleport betagovskope**: file an IO ticket (e.g. IO-26899). `tsh login
  --proxy teleport.betagovskope.io`.
- **Okta group** `fedh-cdjenkins-preprod-webui-ncd`: file an IO ticket (e.g.
  IO-33515) with your govskope user + manager approval. Group format:
  `fedh-cdjenkins-preprod-<team>-ncd`.
- **YubiKey** (Version 5 FIPS): required for FedRAMP MFA. Corp ticket; ships
  physically, request early.
- **/etc/hosts**: map the Jenkins floating IPs (needs sudo):
  ```
  10.149.192.172 cdjenkinsfedh.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net
  10.159.195.6   cdjenkinsfedh.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net
  ```

## Bring up the tunnel + log in

fed02 = **Primary**, fed01 = **DR** (only if DR stack is made active). Each has
its own floating IP. Run in a terminal that stays open:

```bash
# fed02 primary (deploy only)
tshuttle -e 'tsh ssh --proxy teleport.betagovskope.io' \
  -r knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net 10.149.192.172/32
```

Then browser: `https://cdjenkinsfedh.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net/`
Log in (Okta-gov + YubiKey). Seeing the `one_button_webui` job = okta group is
active.

## one_button_webui parameters (verified from the live pipeline)

Fill these for a WebUI MP patch deploy:

| Parameter | Value / note |
|---|---|
| `REGIONS` | **America** (fed preprod is US) |
| `POP_TYPES` | **MP** |
| `POPS` | `fed02-mp-preprod` (primary) or `fed01-mp-preprod` (DR) |
| `STORK_COMPONENT_NAME` | **webui** |
| `RELEASE` | version of webui to deploy |
| `STORK_RELEASE` | stork component version (VER inside storkify) |
| `NAMESPACE` | target namespace (required for stork) |
| `TICKET` | **required**, `ENG-12345` format |
| `VP_APPROVAL` | TRUE only with VP approval on red days / prod lock; FALSE = dryrun allowed |
| `DEPLOY_TYPE` | deployment type |
| `RUN_QE_PDV` | run QE PDV stage? |
| `SLACK_CHANNEL` | your patch channel(s), CSV |

Other params (`STORK_DEPLOY_*`, `DOCKER_REGISTRY`, `PDV_*`, `CLUSTER_NAME`
[legacy pops only], `BYPASS_*`) default via stack config -- leave unless you
have a specific reason.

"Deploy to primary (listed at top of pipeline)" per the patch runbook -- use
`fed02-mp-preprod` unless DR is active.

## After deploy: verify FIPS

Deploy done -> verify the build is FIPS-compliant (if not, ping EP team
immediately). This needs kubectl/rancher access -- switch to the
**fedramp-preprod-kubeconfig** skill, then in the webui pod:

```bash
dpkg -l | grep fips     # should list fips packages
```

## When stuck

Jenkins UI freezes / times out (DO wiki FAQ): disable Juniper/any VPN that
intercepts DNS, `sudo pfctl -F all` (clean packet filter), delete the stale
route (`sudo route -n delete 10.149.192.172`), `tsh logout`, retry the tunnel.
Permissions error on `tsh ssh` -> `export TELEPORT_LOGIN=<govskope-username>`
(the part before `@govskope.us`). "refused to connect" can be a teleport
time-offset issue -- report in `#teleport`. See `references/known-issues.md`.

## Scope / non-goals

- **Getting kubectl / checking pods / FIPS check**: fedramp-preprod-kubeconfig.
- **FedRAMP/PBMM PROD deploy**: not covered. File the NGS deployment ticket
  (7-day SLA); NGS/NOC deploys prod. PBMM deploy day = 3, FedRAMP = day 4.
- **Build creation / artifactory distribution** (steps 10.1-10.2): commercial
  build with `TRIGGER_FEDRAMP_BUILD`, then EP ticket to distribute. See the
  patch runbook, not this skill.
