#!/bin/zsh
# fedramp-preprod-kubeconfig diagnostic (READ-ONLY).
# Figures out which step of the FedRAMP PreProd k8s setup you are stuck on
# and prints the exact next command. Never runs sudo, never mutates state.
#
# Steps checked, in order:
#   1. tsh logged in to teleport.betagovskope.io (fedhigh-preprod)
#   2. tshuttle tunnel up (rancher.betagovskope.io reachable)
#   3. stale reject route left behind (10.246/16 marked '!')
#   4. [fedramp-preprod] token set in ~/.nsk/configuration (not placeholder)
#   5. cluster kubeconfig downloaded to ~/.nsk/
#
# Usage: diagnose.sh

set -u

NSK_CFG="$HOME/.nsk/configuration"
PROXY="teleport.betagovskope.io"
CLUSTER_FED="fedhigh-preprod"
RANCHER="https://rancher.betagovskope.io/v3"
# fed02 (DFW2, DR site) is used as the tshuttle jump host first -- empirically
# more reliable than fed01 (IAD3) per WebUI on-call experience.
JUMP_FED02="knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net"
JUMP_FED01="knode01.c1.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net"
ROUTE="10.246.0.0/16"

ok()   { print -r -- "  [OK]   $1"; }
bad()  { print -r -- "  [FAIL] $1"; }
info() { print -r -- "  [..]   $1"; }
hdr()  { print -r -- ""; print -r -- "== $1 =="; }

NEXT=""      # first blocking step's remediation; printed at the end
set_next() { [ -z "$NEXT" ] && NEXT="$1"; }

# ---- 1. tsh session ----------------------------------------------------
hdr "1. Teleport session"
if ! command -v tsh >/dev/null 2>&1; then
  bad "tsh not installed"
  set_next "Install Teleport client (tsh). See references/known-issues.md."
else
  # tsh status prints all profiles; grab the betagovskope block and check it's
  # not expired. tsh prints "Valid until: ... [EXPIRED]" for a dead session but
  # still shows the profile block, so a bare proxy-name grep would false-OK an
  # expired login. Isolate the block (proxy line + following lines) first.
  STATUS="$(tsh status 2>&1)"
  BLOCK="$(print -r -- "$STATUS" | grep -F -A8 "$PROXY")"
  if [ -z "$BLOCK" ]; then
    bad "not logged in to $PROXY"
    set_next "tsh login --proxy $PROXY   # opens browser, complete Okta-gov login"
  elif print -r -- "$BLOCK" | grep -qi "EXPIRED"; then
    bad "$PROXY session EXPIRED"
    set_next "tsh login --proxy $PROXY   # session expired, re-login (browser Okta-gov)"
  elif print -r -- "$BLOCK" | grep -q "$CLUSTER_FED"; then
    ok "logged in to $PROXY (cluster $CLUSTER_FED)"
  else
    ok "profile for $PROXY present"
  fi
fi

# Detect a stale reject route up front so step 2's remediation can tell the
# user to clear it BEFORE rebuilding the tunnel (order matters: a leftover
# reject route blocks a fresh tunnel).
STALE="$(netstat -rn 2>/dev/null | awk '$1 ~ /^10\.246/ && $NF == "!" {print $1}')"

# ---- 2. tunnel / rancher reachability ----------------------------------
hdr "2. tshuttle tunnel (rancher reachability)"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "$RANCHER" 2>/dev/null)"
# 401 = server reachable but no auth header (expected for /v3 without token).
# 200/302 also fine. 000 / timeout = tunnel down.
if [ "$CODE" = "401" ] || [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then
  ok "rancher.betagovskope.io reachable (HTTP $CODE)"
  TUNNEL_UP=1
else
  bad "rancher.betagovskope.io NOT reachable (HTTP ${CODE:-timeout})"
  TUNNEL_UP=0
  # Prefix a route-delete only if a stale reject route is actually present.
  if [ -n "$STALE" ]; then
    PREFIX="Clear the stale reject route first (needs sudo), then bring up the
  tunnel (fed02-first) in a terminal that stays open:
    sudo route delete $ROUTE
    "
  else
    PREFIX="Bring up the tunnel (fed02-first) in a terminal that stays open:
    "
  fi
  set_next "${PREFIX}tshuttle -e 'tsh ssh --proxy $PROXY' -r $JUMP_FED02 $ROUTE
  If fed02 fails, fall back to fed01:
    tshuttle -e 'tsh ssh --proxy $PROXY' -r $JUMP_FED01 $ROUTE"
fi

# ---- 3. stale reject route ---------------------------------------------
# A '!' (reject) route for 10.246/16 only matters when the tunnel is DOWN --
# tshuttle leaves it behind on exit and it blocks the next tunnel from coming
# up. When the tunnel is UP, rancher is reachable, so the route is benign
# (tshuttle's own route coexists); don't flag it as a failure in that case.
hdr "3. Stale route check"
if [ -n "$STALE" ] && [ "${TUNNEL_UP:-0}" = "0" ]; then
  bad "stale reject route present while tunnel down: $STALE  (blocks a fresh tunnel)"
  info "clear it (needs sudo, run yourself):  sudo route delete $ROUTE"
  # remediation already folded into step 2's next-step
elif [ -n "$STALE" ]; then
  info "reject route for 10.246/16 present but tunnel is up -- benign"
else
  ok "no stale reject route"
fi

# ---- 4. nsk token ------------------------------------------------------
hdr "4. nsk [fedramp-preprod] token"
if [ ! -f "$NSK_CFG" ]; then
  bad "$NSK_CFG not found"
  set_next "Create ~/.nsk/configuration with a [fedramp-preprod] section."
else
  # Pull the VALUE of the `token` key inside the [fedramp-preprod] block.
  # Match only a real key line (optional ws, "token", optional ws, = or :) so
  # comments (#...) and other keys containing the substring "token" are ignored.
  # Take the first such line and strip to the value after the = / : delimiter.
  TOKVAL="$(awk '
    /^[[:space:]]*\[fedramp-preprod\]/{f=1;next}
    /^[[:space:]]*\[/{f=0}
    f && /^[[:space:]]*token[[:space:]]*[:=]/{
      sub(/^[[:space:]]*token[[:space:]]*[:=][[:space:]]*/,"");
      gsub(/"/,""); print; exit
    }' "$NSK_CFG")"
  if [ -z "$TOKVAL" ]; then
    bad "no token key under [fedramp-preprod]"
    set_next "Add token to [fedramp-preprod] in ~/.nsk/configuration (see step 4 in SKILL.md)."
  elif print -r -- "$TOKVAL" | grep -qiE "step 1|placeholder|<.*>|xxxx"; then
    bad "token is still a placeholder"
    set_next "Create a Rancher API key at https://rancher.betagovskope.io/dashboard
    (avatar -> Account & API Keys -> Create API Key), then paste the Bearer
    token into [fedramp-preprod] in ~/.nsk/configuration."
  else
    ok "token set (non-placeholder)"
    # only probe if tunnel up, else it'll just hang
    if [ "${TUNNEL_UP:-0}" = "1" ]; then
      LIST="$(nsk cluster list --profile fedramp-preprod 2>&1)"
      if print -r -- "$LIST" | grep -q "401"; then
        bad "token rejected by rancher (401) -- expired or wrong key"
        set_next "Regenerate the Rancher API key and update ~/.nsk/configuration."
      elif print -r -- "$LIST" | grep -q "stork-fed0"; then
        ok "nsk cluster list works ($(print -r -- "$LIST" | grep -c stork-fed0) stork MP clusters)"
      else
        info "nsk cluster list returned unexpected output; inspect manually"
      fi
    else
      info "skipping nsk probe (tunnel down)"
    fi
  fi
fi

# ---- 5. downloaded kubeconfigs -----------------------------------------
hdr "5. Downloaded kubeconfig(s)"
FOUND=0
for c in stork-fed01-mp-preprod-iad3-nc1 stork-fed02-mp-preprod-dfw2-nc1; do
  if [ -f "$HOME/.nsk/$c.yaml" ] || [ -f "$HOME/.nsk/fedramp-preprod/$c.yaml" ] || [ -f "$HOME/.kube/$c.yaml" ]; then
    ok "$c.yaml present"
    FOUND=1
  fi
done
if [ "$FOUND" = "0" ]; then
  info "no fedramp-preprod kubeconfig downloaded yet"
  info "once tunnel + token are green:  nsk cluster kubeconfig --profile fedramp-preprod --name stork-fed02-mp-preprod-dfw2-nc1"
fi

# ---- summary -----------------------------------------------------------
hdr "Next step"
if [ -z "$NEXT" ]; then
  print -r -- "  All checks green. If kubectl is slow/timing out, that is the tunnel
  (SSH-tunneled, high latency). Scope queries with -n <namespace>, add
  --request-timeout=60s, and avoid full cluster-wide list. See known-issues.md."
else
  print -r -- "$NEXT"
fi
print -r -- ""
