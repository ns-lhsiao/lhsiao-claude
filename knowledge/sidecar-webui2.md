# Sidecar Special Case: webui2 (incl. AWS leg)

Last updated: 2026-11-17. General rules: [sidecar.md](sidecar.md). Deep dive on the render chain: [crane-webui2-render.md](crane-webui2-render.md), [crane-frame-index-serving.md](crane-frame-index-serving.md).

---

## 1. Why webui2 is special

For a normal mf, the entry (`remoteEntry.js`) is fetched by the browser through ngssl, so the header just works. webui2 has two entries:

| build | URL | Entry | Who fetches the entry |
|---|---|---|---|
| `dist` | `/mf/shell/*` | `remoteEntry.js` (embedded in Angular) | browser → edge → header ✅ |
| `dist-frame` | `/mf/frame/*` | `index.html` (full-page React shell, standalone) | on `/ns`, a **server-side fetch** (Ns.php / ms-bootstrap) → header not forwarded ❌ |

Core rule: **whoever serves the first unhashed file decides which build runs.** Every later chunk hash is baked into that HTML/JS; `x-npe-env` only changes *where* a file is fetched, not *which filename*. The sidecar lacks main's hashes → 404 → fallback to main → 200, so **the page looks fine but is running main** (the most common misread).

## 2. The four combinations (as of 2026-11-17)

|  | `/ns` producer = webui PHP (non-cutover) | `/ns` producer = ms-bootstrap (crane) |
|---|---|---|
| Angular shell (flag off) | ① ✅ browser fetches `/mf/shell/remoteEntry.js` itself | ③ ✅ same |
| React shell (flag on) | ② webui#19476 merged, **but still needs webui2#4282 (open)** or the page is blank | ④ ✅ ms-bootstrap#433 merged |

- Hitting `/mf/frame/<route>` directly: no server proxy, ✅ for both tenant types.
- ①③ exception: if `ns.globals.balkan_s3_cloudfront_url` is a CloudFront URL, requests bypass ngssl → sidecar ineffective.
- Why ② is still blocked: the server getting the sidecar HTML is not enough — the browser's follow-up `/mf/frame/assets/<sidecar hash>.js` still goes edge → qa01 `webui2-mf-frame` Ingress → **main** Service → 404 (fallback to main also 404) → blank page. The MP sidecar needs its own `/mf/frame/<suffix>` Ingress. Fix order: ngweb-actions#91 (cleanup sweeps Ingress by label, **merged**) → webui2#4282 (MP template enables `ingress.frame.pathPrefix: /mf/frame/{{ SUFFIX }}` + `rewriteTarget: /mf/frame/$2`). ingress-nginx regex path precedence not yet verified live.

## 3. Which leg serves which tenant (ngssl splits on `$crane_tenant`)

| Tenant | `/mf/frame/*` | `/mf/shell/*`, `/ns` |
|---|---|---|
| crane=1 (`/etc/nginx/crane_tenants.map`, e.g. cpcs-auth-3) | `$crane_mf_proxy_pass` = `aws_nlb` → **AWS leg** | `/ns` → aws_nlb → ms-bootstrap |
| crane=0 | `$ngweb_mf_pass` → **MP leg** | `/ns` → `$webui_pass` → Ns.php |

The crane `/mf/frame` block (`ngweb_mf_route_mappings.conf`) applies to every tenant; the map just sends non-crane back to `ngweb_mf`. Crane tenants are served by `conf.d/aws_crane/*.conf`, **not** the rtp configs; `/npe-ngssl-check` scanning `webui_proxy*.nginx.conf` won't see them.

## 4. MP leg

- Release `webui2-npe-<suffix>`, namespace `ngweb-v2`, qa01/npa01; pipeline `deployment/helm/yap/pipeline-sidecar`, app `webui2-sidecar`.
- Template `charts/webui2/stacks/sidecar-value-template.yaml`:
  - `ingress.pathPrefix: /mf/shell/{{ SUFFIX }}(/|$)(.*)` — the lib chart's pathPrefix helper only appends the capture group for `mf-*` chart names; webui2 isn't `mf-*`, so the regex is spelled out, paired with rewrite-target `/$2`.
  - `ingress.frame.pathPrefix: ""` — **must stay off**, otherwise the chart default `/mf/frame` renders a sidecar-named Ingress on the mainline frame path. #4282 switches it to the suffixed form.
  - `icaas.enabled: true`, `ingressClassName: icaas-nginx-int-ngweb`.
- Trigger: `cicd-pr.yaml` → `service_cicd.yaml` (`sidecar_enabled: true`). `labeled` events also trigger: balkan-pr-scope auto-stamps `ci:sidecar-approved:npe-pr-<N>` on rollout-page PRs, no human gate.

## 5. AWS leg (cpcs, eks-skopeit-dev)

**Why it exists**: the frame originally lived only on AWS (`ingressFrameEks.yaml`) and MP sidecars have no frame Ingress, so the AWS leg was the only place to preview a frame change on a PR. MP mainline now serves `/mf/frame` itself (webui2#3809), but MP sidecars still can't until #4282 lands.

**Implementation** (webui2 `cicd-pr.yaml`, re-enabled by webui2#4119 on 2026-11-12):
- **Standalone jobs, not via ngweb-actions**: ngweb-actions#80 (integrated aws-leg inputs) is **closed / abandoned**. Current flow is webui2's own `publish_manifest_sidecar_aws` → `trigger_yap_sidecar_aws`.
- Reuses `needs.cicd.outputs.tag`, no second docker build; chart version `${TAG}-aws`, uploaded to `ngweb-release-helm/webui2/`.
- Manifest: `ngweb-actions/.github/actions/build-and-publish-manifest@develop` with `yap-pipeline-config-dir: deployment/helm/yap-aws/pipeline-sidecar`, `manifest-template: manifest_template_sidecar_aws.mt.yml`, `force-trigger-yap: 'true'`; Spinnaker app `webui2-sidecar-aws`.
- Suffix is read live from the PR's labels (`gh pr view --json labels`, not the dispatch-time event snapshot), same rules as the MP leg's `resolve_sidecar_suffix`: `ci:sidecar-denied` + approval → fail; multiple approvals → fail; release must match `^webui2-npe-[a-z0-9]([a-z0-9-]{0,8}[a-z0-9])?$`. **One label, one suffix, one header deploys both legs.**

**Template `charts/webui2/stacks/aws/sidecar-value-template.yaml`** (cannot be merged with the MP one):
- `isAwsEnvironment: true` is a global chart switch (lib chart renders an ALB Ingress instead of nginx/icaas); putting it in the MP template breaks MP clusters.
- ALB `pathType: Prefix` is a **literal match — no regex, no rewrite** → `ingress.pathPrefix: /mf/shell/{{ SUFFIX }}`, and the env segment is stripped by the **pod nginx** (`deploy/nginx/default.conf`).
- **Both rules are required**: `pathPrefix: /mf/shell/<suffix>` + `ingress.aws.additionalPathPrefixes: [/mf/frame/<suffix>]`. A frame page pulls `/mf/shell/...` assets; missing either rule mixes in mainline.
- ALB group: `group.name: cpcs-qa01`, `load-balancer-name: ns-cpcs-nonprod-qa01-alb-use1` (joins the mainline ALB).
- **Rule order**: ALB group rules evaluate lowest order first, first match wins; the mainline `/mf/shell` Prefix also matches env-prefixed paths, so sidecar rules must sort **before** mainline (smaller number): sidecar shell `group.order: "5"`, frame `groupOrderOffset: 4` → 6; mainline shell 10 / frame 11. Before first deploy, confirm no other service holds 5/6 in the group. **Very few concurrent AWS sidecars fit** (7 is the only reserved slot).

**Cleanup gap**: eks-skopeit-dev is not Rancher-managed (`nsk cluster list` shows no cpcs), so `sidecar_cleanup.yaml`'s clusters.conf + `RANCHER_TOKEN` can't reach it → **AWS sidecars outlive their PR** (1 pod + 2 Ingresses). The EKS sidecar-terminator is ngweb-actions#88 (open). Clean up manually for now.

## 6. Verification

```bash
H=https://cpcs-auth-3.qa.boomskope.com      # crane → AWS leg; use a non-crane tenant for the MP leg
E=npe-pr-4071
curl -s "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1                         # main
curl -s -H "x-npe-env: $E" "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1       # should differ from main
curl -s -H "x-npe-env: $E" "$H/mf/frame/index.html" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1  # the sidecar itself
curl -s -H "x-npe-env: $E" "$H/mf/frame/build-info.json"                                 # deploymentSuffix
```

DevTools reading: `/ns` document directly contains `/mf/frame/assets/index-*.js` → ②④ (hash chosen by the server); `/ns` is Angular and later loads `/mf/shell/remoteEntry.js` → ①③. **If the first unhashed file is right, everything after it is right.**

## 7. Traps

- "Page works with the header" ≠ running the sidecar — always compare `index-<hash>.js`.
- Don't confuse `/ns` with `/ns/.+`: the latter is post-auth API (`getStaticGlobals` etc.; crane routes it via `$mp_webui_proxy_pass` to api-gateway). Adding a rewrite there breaks the API.
- On the non-crane path, sidecar frame assets are actually reachable via `/mf/shell/<env>/mf/frame/assets/<hash>.js` (verified 200), so rewriting the HTML could theoretically avoid a new Ingress — but never browser-verified end to end; #4282 is the real fix.
- Local webui2 checkouts drift far behind origin/master; `git fetch` before citing line numbers.
