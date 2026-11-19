---
name: sidecar-deploy-status
description: >-
  Check a PR sidecar's real Kubernetes deploy state on every leg (qa01 MP via
  stork kubeconfig, AWS EKS eks-skopeit-dev) using per-service recipes:
  deployment readiness, image tag vs main, pods/restarts, expected ingresses
  (and ALB rule order on EKS), warning events, PR labels. Triggers on
  "sidecar deploy status", "is my sidecar deployed", "check sidecar on qa01/eks",
  "sidecar 部署狀態", "/sidecar-deploy-status". Read-only kubectl get + gh.
  Does NOT deploy, clean up, or edit resources. For tenant-side routing proof
  use webui2-sidecar-probe.
---

# Sidecar deploy status

```bash
~/.claude/skills/sidecar-deploy-status/scripts/status.sh <recipe> <npe-suffix> [pr] [owner/repo]
# e.g. status.sh webui2 npe-pr-4071      (pr inferred from npe-pr-N, repo defaults netSkope/<recipe>)
```

Recipes in `recipes/<name>.sh` (machine config) + `recipes/<name>.md` (why).
Available: `webui2` (/mf/shell + /mf/frame, MP + AWS legs).

## Prerequisites

- Tools: `bash`, `kubectl`, `gh` (authed to netSkope), `perl` (timeout fallback on stock macOS; GNU `timeout`/`gtimeout` used if present).
- VPN on. Two kubeconfigs with read access to `ngweb-v2`: `stork-qa01-mp-npe-iad0-nc1.yaml` (qa01 MP) and `eks-skopeit-dev.yaml` (EKS, Rancher nonprod), in `~/.kube/` or `~/.nsk/`, or point `SDS_KC_MP_QA01` / `SDS_KC_EKS` at them.
- A missing leg kubeconfig only skips that leg; the other still reports.

## Report to user

Per leg: deployed? ready? image tag (date + merge sha) and whether legs match
each other; missing/unexpected ingresses; EKS ALB order sane; warnings. Then
compare with PR: label present, PR open, last image date vs latest push. If a
leg is stale, say which leg and which workflow job redeploys it (see recipe md).

## Adding a recipe

Copy `recipes/webui2.sh`; set `RECIPE_SERVICE`, `RECIPE_NAMESPACE`,
`RECIPE_RELEASE`, `RECIPE_MAIN_SELECTOR`, `RECIPE_LEGS` (`name|kubeconfig|expected ingresses|note`),
optional `recipe_extra()`. Write a matching `.md` with the expected shape.

## Facts / traps

- K8s is ground truth: `helm list` misses YAP-deployed sidecars.
- Image sha is the `pr/merge` commit, not PR head — compare date stamp in the tag and `build-info.branch`.
- Kubeconfig per leg (both need VPN):
  - `mp-qa01` (qa01 MP, stork) → `stork-qa01-mp-npe-iad0-nc1.yaml`; override `SDS_KC_MP_QA01=`.
  - `aws-eks` (EKS `eks-skopeit-dev`, via Rancher nonprod) → `eks-skopeit-dev.yaml`; override `SDS_KC_EKS=`.
  - Default lookup: `~/.kube/<file>` then `~/.nsk/<file>`.
- `system:unauthenticated` / 403 = kubeconfig token expired, not "sidecar missing". Refresh kubeconfig (nsk / Rancher) and rerun.
- EKS sidecars are not auto-cleaned when PR closes (ngweb-actions#88) — flag leftovers, don't delete.
