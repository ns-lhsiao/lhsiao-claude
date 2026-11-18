# Recipe: webui2 (/mf/shell + /mf/frame), two legs.
# Sourced by scripts/status.sh. SUFFIX = npe-<x>, RELEASE = webui2-<SUFFIX>.
# Detail + why: recipes/webui2.md

RECIPE_SERVICE=webui2
RECIPE_NAMESPACE=ngweb-v2
RECIPE_RELEASE="webui2-${SUFFIX}"
RECIPE_MAIN_SELECTOR="app.kubernetes.io/name=webui2"
RECIPE_PROBE_PATHS="/mf/shell/build-info.json /mf/frame/build-info.json"

# leg name | kubeconfig | expected ingress names (space sep) | note
RECIPE_LEGS=(
  "mp-qa01|$HOME/.kube/stork-qa01-mp-npe-iad0-nc1.yaml|${RECIPE_RELEASE} ${RECIPE_RELEASE}-icaas ${RECIPE_RELEASE}-frame ${RECIPE_RELEASE}-frame-icaas|non-crane tenants; frame ingress needs webui2#4282"
  "aws-eks|$HOME/.kube/eks-skopeit-dev.yaml|${RECIPE_RELEASE} ${RECIPE_RELEASE}-mf-frame-${SUFFIX}|crane tenants (ALB group cpcs-qa01); no auto-cleanup (ngweb-actions#88)"
)

# Extra per-leg check: ALB rule order on EKS must be < mainline (shell 10 / frame 11).
recipe_extra() { # $1 leg $2 kubeconfig
  [ "$1" = aws-eks ] || return 0
  kubectl --kubeconfig "$2" -n "$RECIPE_NAMESPACE" get ing \
    -o custom-columns='NAME:.metadata.name,ORDER:.metadata.annotations.alb\.ingress\.kubernetes\.io/group\.order,PATH:.spec.rules[*].http.paths[*].path' \
    2>/dev/null | awk -v r="$RECIPE_RELEASE" 'NR==1 || $1=="webui2" || $1=="webui2-mf-frame" || index($1,r)==1'
}
