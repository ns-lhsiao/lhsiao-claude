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

The **raw `deployment_suffix` input** is sanitized by
`generate_pr_deployment.sh`: `sed 's/[^a-zA-Z0-9-]/-/g'` → lowercase →
**`cut -c1-10`** (max 10 chars) → strip leading/trailing `-`. Then `npe-` is
prepended and used as the release's suffix. So input `pr-123` → release
`mf-client-npe-pr-123`.

The 10-char cut applies to the **input, before** the `npe-` prefix — it does
NOT cap the full `npe-…` string. The auto flow's input is `pr-{num}`, which only
exceeds 10 chars at an 8-digit PR number, so auto sidecars are never truncated.
Truncation (and the collision it can cause between two long suffixes that share
their first 10 chars) is only a concern for **manual** on-demand suffixes.

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
3. Find the sidecar deploy run. The auto flow keys the release on the **PR
   number**, but the run is listed by its head branch — which is NOT
   necessarily `pr/*` (e.g. PR #1205, head `feature/ENG-867168/…`, still
   produced release `mf-client-npe-pr-1205`). So match on the `headRefName` you
   got in step 2, whatever its prefix:
   ```
   gh run list --repo {owner}/{repo} --workflow pr-sidecar.yaml --branch {headRefName} --json databaseId,event,status,conclusion,createdAt --limit 10
   ```
   For a manual deploy, use `--workflow "<Service> SideCar On demand Deploy"`
   (the caller's `name:`), matched by the operator's suffix, not PR number.
4. Inspect the deploy job. The authoritative suffix is a `::notice::` log line
   `Deployment suffix: npe-pr-{num}` emitted by the deploy job — grep for it:
   ```
   gh run view {runId} --repo {owner}/{repo}
   gh run view {runId} --repo {owner}/{repo} --log | grep -iE "Deployment suffix:|Resolved clusters:|npe-"
   ```
   Job status per job: `gh api repos/{owner}/{repo}/actions/runs/{runId}/jobs --jq '.jobs[] | {name, status, conclusion}'`.
   If the run failed, `gh run view {runId} --repo {owner}/{repo} --log-failed`.
5. Compute the release name yourself as a cross-check:
   `{service}-npe-{suffix}`. For the auto flow the suffix is `pr-{num}`, so the
   release is `{service}-npe-pr-{num}` (no truncation — `pr-{num}` only exceeds
   10 chars at an 8-digit PR number).

Report: mode (auto/manual), release name, target clusters, run status, and — if
the deploy succeeded — the route info below.

### Reading run status & quick lookups

- **`waiting` / `pending` run, deploy job not started** = the auto flow is
  parked at the `auto-pr-sidecar` environment approval gate. A reviewer must
  approve it on the run page before deploy runs — the sidecar does NOT exist
  yet. This skill does not approve it (see the "will NOT do" section).
- **Auto vs manual from a bare release name**: a `…-npe-pr-{num}` suffix ⇒ auto
  (keyed on PR number); any other suffix (`npe-dev`, `npe-demo`, …) ⇒ manual
  on-demand.
- **Only have a branch, need the PR number**:
  `gh pr list --repo {owner}/{repo} --head {branch} --state all --json number,state`.
- **Multi-cluster**: the deploy resolves each alias in `pr_clusters` (default
  `qa01`) via `clusters.conf`; the `Resolved clusters:` notice line lists the
  full cluster names actually targeted.

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
   The SAME header drives both the mf and ms sidecars — set it once.
3. Visit the tenant normally (URL unchanged) — every request now carries the
   header and is steered per the two mechanisms above.

The header is shared, but a frontend (`mf-*`) and a backend (`ms-*`) are
SEPARATE sidecar releases; each must be deployed for its half of the routing to
take effect. A `mf-client` PR only ships the `mf-client-npe-{suffix}` release —
`/api/v2/*` calls still route to whatever `ms-*-npe-{suffix}` sidecar exists (or
fall back to the default upstream if none). To exercise a backend change you
need that `ms-*` service's own sidecar deployed under the same suffix.

### Verify — microfrontend (`/mf/*`)

Open `https://{tenant}/mf/client/build-info-json` (or `build-info.json`) and
confirm the reported deployment suffix matches. Wrong/absent suffix = header not
taking effect, or the mf sidecar isn't deployed.

### Verify — microservice (`/api/v2/*`)

The ms path rewrites the upstream HOST, not the URL, so there is no
build-info page at a rewritten path. Confirm routing by either:
- comparing an `/api/v2/<segment>` response with vs without the `x-npe-env`
  header (a behavior/response difference means the sidecar is serving), or
- checking the Kong / ms-* sidecar pod logs for the request.

Note the fallbacks: an absent-header or NXDOMAIN (PR closed / not-yet-deployed /
reaped) request silently routes to the default `ms-<svc>.ngweb[-v2]` upstream —
so "it still works without the header" does NOT prove the sidecar is serving. A
deployed ms sidecar with 0 healthy pods returns 502 (intentionally NOT a
fallback). This half was not exercised in-session — treat the ms verification
steps as derived from the Whole picture doc, and confirm against it.

Confirm the sidecar suffix from the deploy run before stating the header value
(auto suffix = `pr-{num}` → header value `npe-pr-{num}`; releases are
`mf-<svc>-npe-pr-{num}` / `ms-<svc>-npe-pr-{num}`). The suffix must satisfy the
regex above.

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
