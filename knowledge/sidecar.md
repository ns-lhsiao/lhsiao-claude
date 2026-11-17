# ngweb-v2 PR Sidecar — General Rules

Last updated: 2026-11-17. Special cases: [sidecar-webui2.md](sidecar-webui2.md) (incl. AWS leg), [sidecar-webui.md](sidecar-webui.md), [sidecar-ms-bootstrap.md](sidecar-ms-bootstrap.md).
For operations (inspect a run, compute the release name, explain header injection) use the `/sidecar` skill; this file records *why* things behave the way they do and the traps hit so far.

---

## 1. One-liner

A sidecar is an extra branch-isolated Helm release `{service}-npe-{suffix}` in the same namespace (`ngweb-v2`), isolated by **Kubernetes labels + a suffix-scoped Ingress path**, not by namespace. The user-facing URL is unchanged; only the request header `x-npe-env: npe-<suffix>` is added.

## 2. Routing in the general case (99% of mf-* / ms-*)

| Traffic | Who honors the header | Mechanism | Fallback |
|---|---|---|---|
| `/mf/*` (mf static assets, `remoteEntry.js`) | **ngssl** (edge nginx, `service` repo) | **Path rewrite**: `/mf/<app>/x` → `/mf/<app>/<env>/x`, then proxied to `ngweb_mf`/ngweb-fe; the sidecar Ingress matches the `/mf/<app>/<suffix>` prefix and the pod (or Ingress rewrite-target) strips the env segment | 404 → `@mf_npe_fallback` retries the original path (main) |
| `/api/v2/*` (ms-*, v2 APIs) | **api-gateway** (Kong, `api-gateway-controller`) | **Upstream host rewrite**: the `ns-upstream-target-overrider` plugin rewrites `ms-<svc>.ngweb[-v2]` → `ms-<svc>-<env>.ngweb[-v2]`; path untouched | NXDOMAIN → default upstream; sidecar exists but 0 healthy pods → **502** (intentionally no fallback) |

- Header validation: `^npe-[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$` (map in ngssl `webui_proxy.nginx.conf`; invalid → empty string = no sidecar routing).
- NPE only (`boomskope.com` / `enable_npe_env_routing`); prod ignores the header.
- One header drives both the mf and ms halves, but **mf and ms are separate releases**: an mf-client PR only deploys `mf-client-npe-<suffix>`; to test a backend change you also need `ms-<svc>-npe-<suffix>`.

**The exception** is any case where the first unhashed file is *not* fetched by the browser through the edge — when a server fetches the HTML itself, the header does not travel automatically. webui2's `/ns` is exactly this (see [sidecar-webui2.md](sidecar-webui2.md)).

## 3. Lifecycle

| Item | Rule |
|---|---|
| Release name | `{service}-npe-{suffix}`; `deployment_suffix` input is sanitized: non-`[a-zA-Z0-9-]` → `-`, lowercase, **`cut -c1-10`** (applied to the input, before `npe-`), strip leading/trailing `-` |
| Auto suffix | `pr-{PR number}` (only truncated at 8-digit PR numbers) |
| Trigger | Current: service repo `cicd-pr.yaml` → ngweb-actions `service_cicd.yaml` integrated lifecycle; **the approval label `ci:sidecar-approved:npe-<suffix>` is the record** (`ci:sidecar-denied` is mutually exclusive; multiple approval labels → fail closed). Legacy: `pr-sidecar.yaml` (`auto-pr-sidecar` environment gate) / `on-demand-sidecar-deploy.yml` (`workflow_dispatch`, has a deprecation spec) |
| Artifacts | docker `ngweb-release-docker` (PR build) / helm `ngweb-release-helm`; sidecar values override the image back to release-docker because mainline stack files pin the develop/master track |
| Deploy | Always via an in-cluster pipeline (Hubble manifest → YAP/Spinnaker); **GH runners have no kubeconfig — no direct `helm upgrade`** |
| Values | `sidecar-value-template.yaml` (`{{ SUFFIX }}`) renders to `sidecar-value.yaml`, placed as the **last** entry of the pipeline overrides pattern so it wins over mainline stack values |
| Cleanup | PR close → `sidecar_cleanup.yaml`: Deployment/Service/HPA by `app.kubernetes.io/name={release}`; since ngweb-actions#91 (merged 2026-11-17) Ingresses are swept by label too (previously only by name `{release}`, `{release}-icaas`, orphaning any extra Ingress). `--ignore-not-found`, safe to rerun |
| Idle reaping | sidecar-terminator (10-day idle, ngweb-actions#81); only reaches Rancher-managed clusters |
| Clusters | NPE: qa01 (default), npa01; aliases in `ngweb-actions/configs/clusters.conf` |

## 4. Verification

- **mf**: `curl -H 'x-npe-env: npe-pr-N' https://<tenant>/mf/<app>/build-info.json` (mf-client: `/mf/client/build-info-json`) and check `deploymentSuffix`.
- **ms**: no build-info; compare responses with/without the header, or check sidecar pod logs. "Works without the header" does **not** prove the sidecar is serving (NXDOMAIN silently falls back).
- **K8s ground truth**: `kubectl get deploy -n ngweb-v2 | grep -- '-npe-'`. `helm list -n ngweb-v2` misses YAP-deployed sidecars.

## 5. General traps

- **`ngweb_mf` returns 401, not 404, for a missing env build**; `@mf_npe_fallback` only catches 404 → final 401, or `error_page 401 =404` swaps in the 174 KB static 404 page. `/npe-ngssl-check` only audits static config — pair it with a live curl.
- **Chart defaults can grow a sidecar Ingress on a mainline path**: any ingress the sidecar values don't override (e.g. webui2 `ingress.frame.pathPrefix` defaults to `/mf/frame`) will claim the mainline path under the sidecar's name. When adding a new Ingress kind, the sidecar template must explicitly disable it or switch it to a suffixed path.
- **Shared-namespace Helm ownership collisions**: non-release-scoped resources (fixed-name ServiceAccount, ExternalName Service, etc.) must be disabled in the sidecar overlay or they fight the main release for ownership (client-oppy lesson).
- **DNS label length**: the header regex allows 67 chars, but `<service>-<env>` must be a valid Service name (≤63, no `_`/uppercase/trailing `-`). Any server code that builds a sidecar host itself must do RFC 1123 validation, or it silently hits main.
- **zsh `curl ${h:+-H "$h"}`** doesn't word-split → leading space in the header → nginx `400`. Use an array.
- **Labels added with `GITHUB_TOKEN` do not trigger other workflows** (recursion guard); label-driven flows need a PAT/App token or `workflow_dispatch`.

## 6. Authoritative docs

- Whole picture: https://netskope.atlassian.net/wiki/spaces/ENG/pages/7810187526
- How to traffic sidecar deployment (User): https://netskope.atlassian.net/wiki/spaces/ENG/pages/7749108007
- ngweb-actions specs: `openspec/specs/service-cicd-sidecar-lifecycle`, `sidecar-label-based-cleanup`, `sidecar-suffix-resolution`, `sidecar-terminator`
