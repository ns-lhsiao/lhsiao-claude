#!/bin/zsh
# fedramp-preprod-one-button-webui diagnostic (READ-ONLY).
# Verifies you can REACH the FedRAMP PreProd deploy Jenkins. Does NOT trigger
# any build, never runs sudo, never mutates state.
#
# The deploy path is separate from the kubeconfig/rancher path:
#   - tunnel routes the Jenkins floating IP (10.149.192.172/32 for fed02
#     primary), NOT the rancher subnet 10.246.0.0/16.
#   - access = okta group fedh-cdjenkins-preprod-webui-ncd + YubiKey (browser).
#
# Steps checked:
#   1. tsh logged in to teleport.betagovskope.io
#   2. /etc/hosts has the cdjenkinsfedh FQDN -> floating-IP mapping
#   3. deploy Jenkins reachable (tunnel routes the Jenkins IP)
#
# Okta-group membership + YubiKey MFA can only be confirmed by the user
# logging into the Jenkins UI in a browser -- the script can't check that.
#
# Usage: diagnose.sh

set -u

PROXY="teleport.betagovskope.io"
CLUSTER_FED="fedhigh-preprod"
JUMP_FED02="knode01.c1.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net"
JUMP_FED01="knode01.c1.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net"
# fed02 = Primary, fed01 = DR. Each has its own Jenkins floating IP.
JENKINS_FED02="cdjenkinsfedh.fed02-mp-preprod.nc1.dfw2.usnssgovcloud.net"
JENKINS_FED01="cdjenkinsfedh.fed01-mp-preprod.nc1.iad3.usnssgovcloud.net"
IP_FED02="10.149.192.172"
IP_FED01="10.159.195.6"
ROUTE_FED02="${IP_FED02}/32"

ok()   { print -r -- "  [OK]   $1"; }
bad()  { print -r -- "  [FAIL] $1"; }
info() { print -r -- "  [..]   $1"; }
hdr()  { print -r -- ""; print -r -- "== $1 =="; }

NEXT=""
set_next() { [ -z "$NEXT" ] && NEXT="$1"; }

# ---- 1. tsh session ----------------------------------------------------
hdr "1. Teleport session"
if ! command -v tsh >/dev/null 2>&1; then
  bad "tsh not installed"
  set_next "Install Teleport client (tsh)."
else
  # tsh prints "Valid until: ... [EXPIRED]" for a dead session but still shows
  # the profile block, so a bare proxy-name match would false-OK an expired
  # login. Isolate the block with fixed-string matching (dots in $PROXY are
  # not regex metacharacters here) and check for EXPIRED explicitly.
  STATUS="$(tsh status 2>&1)"
  BLOCK="$(print -r -- "$STATUS" | grep -F -A8 "$PROXY")"
  if [ -z "$BLOCK" ]; then
    bad "not logged in to $PROXY"
    set_next "tsh login --proxy $PROXY   # browser Okta-gov login"
  elif print -r -- "$BLOCK" | grep -qi "EXPIRED"; then
    bad "$PROXY session EXPIRED"
    set_next "tsh login --proxy $PROXY   # session expired, re-login (browser Okta-gov)"
  else
    ok "logged in to $PROXY"
    # TELEPORT_LOGIN sometimes needs setting if ssh perms fail (DO wiki FAQ)
    if [ -z "${TELEPORT_LOGIN:-}" ]; then
      info "TELEPORT_LOGIN unset -- if tsh ssh gives a permissions error, set it to your govskope username (before the @govskope.us)"
    fi
  fi
fi

# ---- 2. /etc/hosts mapping ---------------------------------------------
hdr "2. /etc/hosts Jenkins mapping"
# Ignore commented lines; parse by fields (not a dot-as-wildcard regex match
# on the FQDN) so the lookup doesn't false-match a similar hostname and
# handles multiple aliases on the same /etc/hosts line. Take the first
# active mapping and compare its IP to the expected floating IP so a
# stale/wrong mapping is flagged, not passed.
MAPPED_IP="$(awk -v host="$JENKINS_FED02" '
  $1 !~ /^#/ {
    for (i = 2; i <= NF; i++) if ($i == host) { print $1; exit }
  }' /etc/hosts 2>/dev/null)"
if [ -z "$MAPPED_IP" ]; then
  bad "no /etc/hosts entry for $JENKINS_FED02"
  set_next "Add to /etc/hosts (needs sudo):
    $IP_FED02 $JENKINS_FED02
    $IP_FED01 $JENKINS_FED01"
elif [ "$MAPPED_IP" != "$IP_FED02" ]; then
  bad "$JENKINS_FED02 mapped to WRONG IP ($MAPPED_IP, expected $IP_FED02)"
  set_next "Fix the /etc/hosts mapping (needs sudo) -- should be:
    $IP_FED02 $JENKINS_FED02"
else
  ok "$JENKINS_FED02 mapped ($MAPPED_IP)"
fi

# ---- 3. deploy Jenkins reachability ------------------------------------
hdr "3. Deploy Jenkins reachability (fed02 primary)"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "https://$JENKINS_FED02/login" 2>/dev/null)"
# 200/403/302 = server reachable (login/redirect). 000/timeout = tunnel not
# routing the Jenkins IP.
if [ "$CODE" = "200" ] || [ "$CODE" = "403" ] || [ "$CODE" = "302" ]; then
  ok "$JENKINS_FED02 reachable (HTTP $CODE)"
  info "Confirm okta group + YubiKey by logging into the UI in a browser:"
  info "  https://$JENKINS_FED02/"
  info "  You should be able to log in and see the one_button_webui job."
else
  bad "$JENKINS_FED02 NOT reachable (HTTP ${CODE:-timeout})"
  set_next "Bring up the deploy tunnel (fed02 primary). Run in a terminal that stays open:
    tshuttle -e 'tsh ssh --proxy $PROXY' -r $JUMP_FED02 $ROUTE_FED02
  To ALSO reach rancher (for post-deploy FIPS check), add its subnet:
    tshuttle -e 'tsh ssh --proxy $PROXY' -r $JUMP_FED02 $ROUTE_FED02 10.246.0.0/16
  If the UI still freezes/times out (DO wiki FAQ): disable Juniper/VPN,
  'sudo pfctl -F all', 'sudo route -n delete $IP_FED02', 'tsh logout' then retry."
fi

# ---- summary -----------------------------------------------------------
hdr "Next step"
if [ -z "$NEXT" ]; then
  print -r -- "  Reachability green. Log into the Jenkins UI (browser + YubiKey) to
  confirm okta-group access and see one_button_webui. Do NOT trigger a build
  unless you have a real in-flight patch and explicit go-ahead. See SKILL.md
  for the parameter reference."
else
  print -r -- "$NEXT"
fi
print -r -- ""
