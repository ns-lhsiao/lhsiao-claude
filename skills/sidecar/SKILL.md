---
name: sidecar
description: >-
  Explain, inspect, and route ngweb-v2 PR sidecar deployments. Use when a user
  asks about sidecar deploys, mentions "sidecar", "npe sidecar", "pr sidecar",
  "on-demand deploy", references a PR + tenant and wants to test the branch on
  their tenant, or invokes /sidecar. Read-only: answers questions, inspects a
  PR's sidecar deploy run/status, computes the release name,
  and explains how to route a tenant to the sidecar via the `x-npe-env` header.
  Does NOT trigger deploys or approve environment gates — it tells the user how,
  it does not do it.
---

# ngweb-v2 PR Sidecar Deployments

A **sidecar** is a branch-isolated Helm release deployed alongside the main
service in the same Kubernetes namespace (`ngweb-v2`), so a PR branch can be
tested on a real tenant without touching the running primary service. Isolation
is by Kubernetes label + a per-suffix Ingress path — **not** by namespace.

This skill is **read-only knowledge + inspection**. It answers sidecar
questions, inspects a given PR's sidecar deploy, computes the release name, and
explains how to point a tenant at the sidecar via the `x-npe-env` header. It never
triggers a deploy or approves an environment gate; when action is needed it
tells the user the exact step to take themselves.

## When to use

- "explain sidecar" / "how do PR sidecars work" → knowledge section below
- "check the sidecar for PR <url>" → **Inspect a PR's sidecar** flow
- "/sidecar <service> from pr <url> and how do I apply it on <tenant>" →
  Inspect + **Route a tenant to a sidecar**
- "why isn't my sidecar up" → Inspect + troubleshooting

## Caveman mode

Conversational text follows the active caveman level. Any command, release
name, URL, label, or config value is a technical token — reproduce verbatim,
never abbreviate.

---

## Core knowledge

### Release naming

```
{service}-npe-{suffix}
```

The suffix is sanitized by `generate_pr_deployment.sh`:
`sed 's/[^a-zA-Z0-9-]/-/g'` → lowercase → **`cut -c1-10`** (max 10 chars) →
strip leading/trailing `-`. So `deployment_suffix: pr-123` → release
`mf-client-npe-pr-123`. A long suffix is silently truncated to 10 chars — a
collision source worth checking.

### Two ways a sidecar is triggered

Both are thin **caller** workflows in the service repo that invoke the SAME
reusable workflow `netSkope/ngweb-actions/.github/workflows/on-demand-sidecar-deploy.yml@develop`.
The reusable workflow itself is `workflow_call` only.

| Mode | Caller file | Trigger | Suffix | Gate |
|------|-------------|---------|--------|------|
| **Auto PR sidecar** | `.github/workflows/pr-sidecar.yaml` | `pull_request: [opened, synchronize, reopened, closed]` on `master`/`staging` | `pr-{PR_number}` | `auto-pr-sidecar` GitHub environment (Required reviewers). Fork PRs skipped (no secrets). |
| **Manual on-demand** | `.github/workflows/on-demand-sidecar-deploy.yml` | `workflow_dispatch` | operator-supplied `deployment_suffix` input | none (engineer-driven) |

Key consequences:
- **Auto**: opening/pushing a PR fires a deploy; a reviewer must approve the
  `auto-pr-sidecar` environment before the `deploy` job runs (the `approval`
  gate job exists solely so `environment:` can be declared — reusable caller
  jobs can't declare `environment:` directly). Closing the PR (merged or
  abandoned) fires cleanup.
- **Manual**: run via Actions → "Sidecar On demand Deploy" → Run workflow, with
  `deployment_suffix` (required) + `clusters` (default `qa01`). No approval gate.
- Both target NPE clusters (default `qa01`; npa01 also available).
- **Suffix namespace hygiene**: `pr-*` suffixes are reserved for the auto flow
  (keyed to PR number + persisted state). A manual on-demand deploy should use a
  different suffix (e.g. `dev`, `demo`) to avoid colliding with an auto sidecar.

### Version tag

The sidecar image/chart tag comes from `prepare_version_tag.sh`. On a PR event
with a `pr/*` head it is `0.0.0-pr.{num}.{timestamp}.{sha}`; otherwise it falls
through per branch rules. The tag is NOT the release name — release name is
`{service}-npe-{suffix}`.

### Where artifacts live (NPE)

Sidecars publish to the **develop** repos and register a manifest with the NPE
template:
- docker → `ngweb-develop-docker`
- app + YAP (`cd-{service}`) helm → `ngweb-develop-helm`
- manifest template → `manifest_template_npe.mt.yml`

NPE `deployEnv.prod: false`, so a sidecar never runs ep-falcon
`commercial:prod` promotion — develop-helm having no promotion policy is
irrelevant for sidecars (unlike the prod pipeline).

### Cleanup

Auto: PR close. Manual: `on-demand-sidecar-cleanup.yml` (`workflow_dispatch`,
`deployment_suffix` + `clusters`). Both delete via `kubectl` with
`--ignore-not-found` (idempotent):
- Deployment, Service, HPA by label `app.kubernetes.io/name={release}`
- Ingress by name `{release}` and `{release}-icaas`

---

## Inspect a PR's sidecar

Given a PR URL (e.g. `https://github.com/netSkope/mf-client/pull/123`):

1. Parse `{owner}/{repo}` and PR number from the URL.
2. Read the PR head branch and number:
   ```
   gh pr view {num} --repo {owner}/{repo} --json number,headRefName,state,title
   ```
3. Find the sidecar deploy run. Auto sidecars run the `pr-sidecar.yaml`
   workflow keyed by PR number; find recent runs and match:
   ```
   gh run list --repo {owner}/{repo} --workflow pr-sidecar.yaml --json databaseId,headBranch,event,status,conclusion,createdAt --limit 20
   ```
   For a manual deploy, use `--workflow "<Service> SideCar On demand Deploy"`
   (the caller's `name:`), matched by the operator's suffix, not PR number.
4. Inspect the deploy job — the **PR Deployment Config** step summary carries
   the computed suffix, release name, and the route line:
   ```
   gh run view {runId} --repo {owner}/{repo}
   gh run view {runId} --repo {owner}/{repo} --log | grep -iE "deploy suffix|route to sidecar|Route to|npe-"
   ```
   If the run failed, `gh run view {runId} --repo {owner}/{repo} --log-failed`.
5. Compute the release name yourself as a cross-check:
   `{service}-npe-{sanitized-suffix}` (auto suffix = `pr-{num}`; apply the
   10-char truncation rule).

Report: mode (auto/manual), release name, target clusters, run status, and — if
the deploy succeeded — the route info below.

## Route a tenant to a sidecar

Tenant traffic is routed to a sidecar by **injecting the `x-npe-env` request
header** whose value is the sidecar suffix (e.g. `npe-pr-1242`, `npe-dev-louis`)
— NOT by changing the URL. The URL the user visits is unchanged
(`https://{tenant}/mf/client/...`). One header controls both microfrontend
assets and microservice APIs, via two different mechanisms:

| Traffic | Layer | Mechanism | Where it lives |
|---------|-------|-----------|----------------|
| `/mf/*` (microfrontend assets) | **ngssl (nginx)** | nginx **rewrites the path** `/mf/<app>/…` → `/mf/<app>/<env>/…` before proxying to ngweb-fe; 404 on the env asset falls back to the original path | the **service repo's** nginx config |
| `/api/v2/*` (microservice APIs) | **api-gateway (Kong)** | the `ns-upstream-target-overrider` plugin **rewrites the upstream host** `ms-<svc>.ngweb[-v2]` → `ms-<svc>-<env>.ngweb[-v2]`; path untouched; NXDOMAIN falls back to default upstream | **api-gateway-controller** (Kong plugin config) |

So: **mf → nginx path rewrite (service repo); ms → api-gw-controller host
rewrite (Kong).** Header value is validated against
`^npe-[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$` and the whole feature is gated to NPE
(`boomskope.com` domain / `enable_npe_env_routing`) — prod ignores the header.

Authoritative references:
- **Whole picture** (architecture, both mechanisms):
  https://netskope.atlassian.net/wiki/spaces/ENG/pages/7810187526
- **How to traffic sidecar deployment (User)** (step-by-step):
  https://netskope.atlassian.net/wiki/spaces/ENG/pages/7749108007

Steps to test a branch on tenant `https://{tenant}`:

1. Install the **ModHeader** Chrome extension (HTTP header injector).
2. Add request header `x-npe-env: <sidecar-suffix>` (e.g. `x-npe-env: npe-pr-1242`).
3. Visit the tenant normally — `https://{tenant}/mf/client/...` now serves the
   sidecar build; any `/api/v2/...` call routes to the matching `ms-*-<env>`
   sidecar if one exists.
4. **Verify**: open `https://{tenant}/mf/client/build-info-json` (or
   `build-info.json`) and confirm the reported deployment suffix is the expected
   one. Wrong/absent suffix = header not taking effect (or the sidecar isn't
   deployed yet — the ms path silently falls back on NXDOMAIN).

Confirm the sidecar suffix from the deploy run before stating the header value
(auto suffix = `pr-{num}` → header value `npe-pr-{num}`; the release is
`{service}-npe-pr-{num}`). The suffix must satisfy the regex above.

---

## What this skill will NOT do

- Trigger `workflow_dispatch` deploys or cleanups
- Approve the `auto-pr-sidecar` environment gate
- Modify cluster state

For those, tell the user the exact manual step (Actions → Run workflow with
inputs X/Y, or approve the pending environment on the run page) and stop.

## Cross-references

- `create-indie-mf-sidecar` — builds the sidecar pipeline wiring (the inverse
  of this skill; use when a service has no sidecar workflows yet).
- Cluster aliases resolve via `ngweb-actions/configs/clusters.conf`.
