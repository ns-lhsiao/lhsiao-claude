# Recipe: webui2 (/mf/shell + /mf/frame)

Release `webui2-<suffix>` in `ngweb-v2`, two legs deployed from one
`ci:sidecar-approved:<suffix>` label (webui2 `cicd-pr.yaml`).

| Leg | Cluster / kubeconfig | Serves | Expected ingresses | Deployed by |
|---|---|---|---|---|
| mp-qa01 | `stork-qa01-mp-npe-iad0-nc1` | non-crane tenants: `/mf/shell/<sfx>`, `/mf/frame/<sfx>` via ngssl → icaas | `<rel>`, `<rel>-icaas` (shell regex `/mf/shell/<sfx>(/\|$)(.*)`), `<rel>-frame`, `<rel>-frame-icaas` (webui2#4282) | `service_cicd.yaml` sidecar (ngweb-actions) |
| aws-eks | `eks-skopeit-dev` (Rancher nonprod) | crane tenants: ngssl → AWS NLB/ALB group `cpcs-qa01` | `<rel>` (`/mf/shell/<sfx>` Prefix, order 5), `<rel>-mf-frame-<sfx>` (`/mf/frame/<sfx>`, order 6) | webui2 jobs `publish_manifest_sidecar_aws` → `trigger_yap_sidecar_aws`, Spinnaker app `webui2-sidecar-aws` |

Health rules:
- Sidecar ALB order must be < mainline (`webui2` 10, `webui2-mf-frame` 11); first match wins.
- Both legs should carry the same image date/sha. Skew = one leg's pipeline didn't run/finish
  (2026-11-18: MP `202611180427.7c53d7e`, EKS `202611160709.f6f4a8a` → crane tenants saw the older frame).
- Frame on MP leg needs `-frame` ingresses; if missing, non-crane `/ns` sidecar frame assets 404.
- EKS leftovers after PR close are expected until ngweb-actions#88; report, don't delete.
