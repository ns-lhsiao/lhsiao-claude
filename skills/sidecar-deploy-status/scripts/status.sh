#!/usr/bin/env bash
# Sidecar deploy status across legs (read-only kubectl get/describe + gh).
# Usage: status.sh <recipe> <npe-suffix> [pr-number] [owner/repo]
set -uo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
RECIPE="${1:?usage: status.sh <recipe> <npe-suffix> [pr] [repo]}"
SUFFIX="${2:?usage: status.sh <recipe> <npe-suffix> [pr] [repo]}"
PR="${3:-}"; REPO="${4:-netSkope/$RECIPE}"
case "$SUFFIX" in npe-*) ;; *) SUFFIX="npe-$SUFFIX";; esac
[ -f "$DIR/recipes/$RECIPE.sh" ] || { echo "no recipe: $DIR/recipes/$RECIPE.sh"; ls "$DIR/recipes"; exit 2; }
# shellcheck source=/dev/null
. "$DIR/recipes/$RECIPE.sh"
K() { timeout 45 kubectl --kubeconfig "$KC" -n "$RECIPE_NAMESPACE" "$@"; }

echo "# sidecar deploy status: recipe=$RECIPE release=$RECIPE_RELEASE ns=$RECIPE_NAMESPACE"
HEAD=""
if [ -z "$PR" ]; then case "$SUFFIX" in npe-pr-[0-9]*) PR="${SUFFIX#npe-pr-}";; esac; fi
if [ -n "$PR" ] && command -v gh >/dev/null; then
  read -r HEAD STATE LABELS < <(gh pr view "$PR" -R "$REPO" --json headRefOid,state,labels \
    -q '[.headRefOid[0:7], .state, ([.labels[].name|select(startswith("ci:sidecar"))]|join(","))]|@tsv' 2>/dev/null)
  echo "PR $REPO#$PR state=${STATE:-?} head=${HEAD:-?} labels=${LABELS:-none}"
  echo "note: image sha = merge commit (pr/merge ref), not head; compare build-info.branch '<pr>/merge' + date"
fi
echo

for leg in "${RECIPE_LEGS[@]}"; do
  IFS='|' read -r NAME KC INGS NOTE <<<"$leg"
  echo "## leg: $NAME  ($NOTE)"
  [ -f "$KC" ] || { echo "kubeconfig missing: $KC"; echo; continue; }
  if ! K get deploy "$RECIPE_RELEASE" -o name >/dev/null 2>"/tmp/sds.$$"; then
    echo "deploy/$RECIPE_RELEASE: NOT FOUND ($(head -c 200 "/tmp/sds.$$"))"; echo; continue
  fi
  K get deploy "$RECIPE_RELEASE" -o jsonpath='{"ready="}{.status.readyReplicas}/{.spec.replicas}{" updated="}{.status.updatedReplicas}{" created="}{.metadata.creationTimestamp}{"\nimage="}{.spec.template.spec.containers[0].image}{"\n"}'
  echo "main image=$(K get deploy -l "$RECIPE_MAIN_SELECTOR" -o jsonpath='{.items[0].spec.template.spec.containers[0].image}' 2>/dev/null)"
  K get pods -l "app.kubernetes.io/name=$RECIPE_RELEASE" -o custom-columns='POD:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,START:.status.startTime' 2>/dev/null
  have="$(K get ing -o name 2>/dev/null | sed 's#.*/##')"
  for i in $INGS; do
    if printf '%s\n' "$have" | grep -qx "$i"; then
      p="$(K get ing "$i" -o jsonpath='{.spec.rules[*].http.paths[*].path}')"; echo "ing/$i ✅ $p"
    else echo "ing/$i ❌ missing"; fi
  done
  extra="$(printf '%s\n' "$have" | grep "^$RECIPE_RELEASE" | grep -vxF -f <(printf '%s\n' $INGS))"
  [ -n "$extra" ] && echo "unexpected ingresses: $extra"
  recipe_extra "$NAME" "$KC"
  echo "recent warnings:"; K get events --field-selector type=Warning 2>/dev/null | grep "$RECIPE_RELEASE" | tail -3
  echo
done
