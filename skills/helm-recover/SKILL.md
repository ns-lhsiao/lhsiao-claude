---
name: helm-recover
description: >-
  Diagnose and unblock stuck helm releases (pending-upgrade, pending-install,
  failed rollouts, sidecar drift) on ngweb-v2 / ngweb namespaces. Treats
  `kubectl get deploy` as ground truth (helm list is unreliable for
  YAP-deployed sidecars). Triggers on "/helm-recover", "helm pending-upgrade",
  "release stuck", "rollback failed", "sidecar missing", or any request to
  diagnose why a helm release is in a non-deployed state.
argument-hint: "<release-name> [-n <namespace>]"
allowed-tools: Bash(kubectl:*), Bash(helm:*), Bash(awk:*), Bash(grep:*), Read, AskUserQuestion
user-invocable: true
---

# Helm Recover

**Emit "Skill activated: helm-recover"**

## Why this exists

When a helm release is stuck (`pending-upgrade`, `pending-install`,
`failed`), the wrong move is to immediately retry `helm upgrade` or run
`helm rollback` — that often makes things worse. The right move is to:

1. Confirm what's actually deployed in the cluster (kubectl-as-truth, NOT
   `helm list`).
2. Identify which release attempt failed and why (rendered chart, hook
   failure, missing image, RBAC).
3. Choose the minimum recovery action.

This skill encodes the recurring patterns from the ngweb-v2 namespace
migration work.

## Inputs

- `<release-name>` — the helm release (e.g. `mf-client-npe-stg01`)
- `[-n <namespace>]` — defaults to `ngweb-v2`. Common alternatives: `ngweb`,
  `webui`.

If the release name is missing, ask once. Do not guess.

## Procedure

### 1. Snapshot helm state

```bash
helm status <release> -n <ns> --show-desc
helm history <release> -n <ns> --max 5
```

Read the current state and the last few revisions. Note:
- `pending-upgrade` / `pending-install` → an upgrade was started but never
  completed (often a hook timed out, or the previous run was killed).
- `failed` → terminal; safe to roll back.
- `deployed` → the release is fine; the user's symptom is something else.

### 2. Verify what's actually running (ground truth)

`helm list` MISSES sidecars deployed via YAP. Use kubectl Deployments
instead, filtered by the release-name convention `<service>(-npe-<suffix>)?`:

```bash
kubectl get deploy -n <ns> -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
  | awk -v svc="<service>" '$0 == svc || index($0, svc "-npe-") == 1'
```

For each matching Deployment, get image + readiness:

```bash
kubectl get deploy -n <ns> <name> \
  -o jsonpath='{.spec.template.spec.containers[*].image}{"\t"}{.status.readyReplicas}/{.status.replicas}{"\n"}'
```

Cross-reference with the version the failed helm release was trying to
deploy. If the cluster is already running the target image, recovery may be
"just clear the pending-upgrade lock" rather than re-running the upgrade.

### 3. Find the failure cause

```bash
helm get manifest <release> -n <ns> | head -200
kubectl get events -n <ns> --sort-by=.lastTimestamp | tail -40
kubectl get pods -n <ns> | grep -E '<service>|<release>'
```

For pods in CrashLoopBackOff or ImagePullBackOff:

```bash
kubectl describe pod -n <ns> <pod>
kubectl logs -n <ns> <pod> --tail=100
kubectl logs -n <ns> <pod> --previous --tail=100 2>/dev/null
```

For hook failures, look in the manifest for `helm.sh/hook` annotations and
inspect those resources directly.

### 4. Choose recovery path

Pick the smallest reversible action that fits:

**A. Cluster matches target version, helm just thinks it's mid-upgrade**
- The lock is the only problem. Use `helm rollback` to the last `deployed`
  revision (which will be a no-op for the cluster but resets helm's status):

  ```bash
  helm rollback <release> <last-deployed-revision> -n <ns>
  ```

  If even that fails, the nuclear option is to manually edit the
  release secret:

  ```bash
  kubectl -n <ns> get secret -l owner=helm,name=<release> --sort-by=.metadata.creationTimestamp
  # Identify the most recent secret. Patch its `release` field's status from
  # pending-upgrade → deployed. (Confirm with the user before doing this.)
  ```

  This is destructive enough that it MUST be confirmed with the user.

**B. Cluster is on the wrong version and we want to retry the upgrade**
- Confirm there's no in-flight reason for the original failure (image
  exists, RBAC fixed, etc.).
- Retry: `helm upgrade --install <release> ... -n <ns>`. Use the same
  values file and chart version that the original attempt used.
- If the original was an apply via the deployment pipeline (drone, helm-ci),
  prefer re-running the pipeline over a manual `helm upgrade`.

**C. Failed terminally and we want to revert**

  ```bash
  helm rollback <release> <previous-deployed> -n <ns>
  ```

**D. Sidecar drift (Deployment exists but no helm release, or vice versa)**
- This is common with YAP-deployed sidecars. Don't try to "fix" it with
  helm — touching the helm release will conflict with YAP. Instead, report
  the drift and let the user decide.

### 5. Verify

After any recovery action, re-run step 2. Confirm:
- `helm status` shows `deployed`
- All Deployments report `readyReplicas == replicas`
- No pods in CrashLoopBackOff / ImagePullBackOff
- `kubectl get events` shows nothing alarming in the last minute

### 6. Report

Output a compact summary:

```
Release:     mf-client-npe-stg01 (ngweb-v2)
Was:         pending-upgrade (rev 47, started 2026-05-12 19:02 UTC)
Cluster:     mf-client:v202605.2-rc3 — 3/3 ready
Cause:       hook job timed out (post-install/migrate-db, 5m)
Action:      helm rollback to rev 46 (no-op for cluster, status now deployed)
Verify:      helm status deployed | 3/3 ready | events clean
```

## Operator details from LEARNINGS

- **`helm list` is not authoritative.** Sidecars deployed via YAP do not
  register as helm releases. Use `kubectl get deploy` filtered by the
  `<service>(-npe-<suffix>)?` convention.
- **Webui namespace pattern for MP-prod POPs**: `<dc>-mp-prod--webui`
  (e.g. `dfw3-mp-prod--webui`), NOT `c4-<dc>`. Confirm the namespace before
  running anything.
- **The `app.kubernetes.io/instance` label** works as a fallback only for
  helm-deployed sidecars; it's unreliable for YAP-deployed ones. Prefer
  Deployment-name filtering.

## Don't

- Don't blindly run `helm rollback` without first confirming what's running.
  Rollback to the wrong revision can take a healthy cluster down.
- Don't manually edit helm release secrets without explicit user confirmation.
  This is destructive.
- Don't run `helm uninstall` on a stuck release "to start fresh" — that
  deletes all the resources, including healthy ones.
- Don't trust `helm list` for sidecar inventory.
