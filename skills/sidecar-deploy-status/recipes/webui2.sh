# Recipe: webui2 (/mf/shell + /mf/frame), two legs.
# Sourced by scripts/status.sh. SUFFIX = npe-<x>, RELEASE = webui2-<SUFFIX>.
# Detail + why: recipes/webui2.md

RECIPE_SERVICE=webui2
RECIPE_NAMESPACE=ngweb-v2
RECIPE_RELEASE="webui2-${SUFFIX}"
RECIPE_MAIN_SELECTOR="app.kubernetes.io/name=webui2"
RECIPE_PROBE_PATHS="/mf/shell/build-info.json /mf/frame/build-info.json"

# Kubeconfig per leg: env override, else first existing of ~/.kube/<f>, ~/.nsk/<f>.
_kc() { # $1 env override value, $2 filename
  [ -n "$1" ] && { echo "$1"; return; }
  for d in "$HOME/.kube" "$HOME/.nsk"; do [ -f "$d/$2" ] && { echo "$d/$2"; return; }; done
  echo "$HOME/.kube/$2"  # not found; status.sh reports missing
}
KC_MP_QA01="$(_kc "${SDS_KC_MP_QA01:-}" stork-qa01-mp-npe-iad0-nc1.yaml)"
KC_EKS="$(_kc "${SDS_KC_EKS:-}" eks-skopeit-dev.yaml)"

# leg name | kubeconfig | expected ingress names (space sep) | note
RECIPE_LEGS=(
  "mp-qa01|$KC_MP_QA01|${RECIPE_RELEASE} ${RECIPE_RELEASE}-icaas ${RECIPE_RELEASE}-frame ${RECIPE_RELEASE}-frame-icaas|non-crane tenants; frame ingress needs webui2#4282"
  "aws-eks|$KC_EKS|${RECIPE_RELEASE} ${RECIPE_RELEASE}-mf-frame-${SUFFIX}|crane tenants (ALB group cpcs-qa01); no auto-cleanup (ngweb-actions#88)"
)

# Extra per-leg check: ALB rule order on EKS must be < mainline (shell 10 / frame 11).
recipe_extra() { # $1 leg $2 kubeconfig
  [ "$1" = aws-eks ] || return 0
  kubectl --kubeconfig "$2" -n "$RECIPE_NAMESPACE" get ing \
    -o custom-columns='NAME:.metadata.name,ORDER:.metadata.annotations.alb\.ingress\.kubernetes\.io/group\.order,PATH:.spec.rules[*].http.paths[*].path' \
    2>/dev/null | awk -v r="$RECIPE_RELEASE" 'NR==1 || $1=="webui2" || $1=="webui2-mf-frame" || index($1,r)==1'
}
