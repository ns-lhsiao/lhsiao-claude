#!/usr/bin/env bash
# Live probe: does tenant /ns land on webui2 sidecar <env>?
# Usage: probe.sh <tenant-host> <npe-env> [cookie-header]
# Read-only: GETs only. No auth unless cookie passed.
set -uo pipefail

HOST="${1:?usage: probe.sh <tenant-host> <npe-env> [cookie]}"
ENV="${2:?usage: probe.sh <tenant-host> <npe-env> [cookie]}"
COOKIE="${3:-}"
H="https://${HOST#https://}"; H="${H%/}"
CRANE_MAP="${CRANE_MAP:-$HOME/ns/git/webui-crane-project/qa01_crane_tenants.md}"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

base=(-s --max-time 20)
[ -n "$COOKIE" ] && base+=(-H "Cookie: $COOKIE")
hdr=("${base[@]}" -H "x-npe-env: $ENV")

say() { printf '%s\n' "$*"; }
code() { curl "$@" -o /dev/null -w '%{http_code}'; }

say "# webui2 sidecar probe"
say "host=$H env=$ENV auth=$([ -n "$COOKIE" ] && echo cookie || echo anonymous)"
say ""

# ---- 1. what was poked: /ns main vs header
say "## 1. Requests"
curl "${base[@]}" -D "$T/m.h" -o "$T/m.html" "$H/ns"
curl "${hdr[@]}"  -D "$T/s.h" -o "$T/s.html" "$H/ns"
say "GET $H/ns                         -> $(head -1 "$T/m.h" | tr -d '\r')"
say "GET $H/ns  [x-npe-env: $ENV]      -> $(head -1 "$T/s.h" | tr -d '\r')"
say ""

# ---- 2. /ns producer
say "## 2. /ns producer"
crane="unknown (map snapshot missing)"
if [ -f "$CRANE_MAP" ]; then
  snap="$(grep -oE '抓取日 [0-9-]+|fetched [0-9-]+' "$CRANE_MAP" | head -1)"
  if grep -qF "${HOST#https://} 1;" "$CRANE_MAP"; then crane="YES ($snap snapshot)"; else crane="NO ($snap snapshot)"; fi
fi
ci="$(grep -i '^set-cookie: ci_session=' "$T/s.h" | head -1)"
say "crane_tenants.map member : $crane  (snapshot may be stale; live map on ngsslwebui01 /etc/nginx/crane_tenants.map)"
say "ci_session Set-Cookie    : $([ -n "$ci" ] && echo present || echo absent)  (CodeIgniter = PHP; ms-bootstrap never sets it)"
# ms-bootstrap mimics PHP Expires/Cache-Control + helmet X-XSS-Protection:0 -> those are NOT discriminators.
if [ -n "$ci" ]; then say "=> producer: webui PHP Ns::index() (MP qa01 webui pods)"
  case "$crane" in YES*) say "   ⚠️ snapshot says crane but PHP answered: tenant likely removed from live map";; esac
else case "$crane" in
  YES*) say "=> producer: ms-bootstrap (crane: ngssl -> AWS NLB -> EKS eks-skopeit-dev)";;
  *)    say "=> producer: likely ms-bootstrap (no ci_session) — verify live map";;
esac; fi
say ""

# ---- 3. shell render
say "## 3. Balkan render"
entry() { grep -oE '/mf/frame/assets/index-[A-Za-z0-9_-]+\.js' "$1" | head -1; }
m_entry="$(entry "$T/m.html")"; s_entry="$(entry "$T/s.html")"
cdn="$(grep -oE '"balkan_s3_cloudfront_url":"[^"]*"' "$T/s.html" | head -1)"
if [ -n "$s_entry" ]; then
  shell=frame
  sc_entry="$(curl "${hdr[@]}" "$H/mf/frame/index.html" | grep -oE '/mf/frame/assets/index-[A-Za-z0-9_-]+\.js' | head -1)"
  say "shell: React frame (/ns HTML embeds /mf/frame entry; hash chosen server-side) -> case ②/④"
  say "main /ns entry          : ${m_entry:-none}"
  say "/ns + header entry      : $s_entry"
  say "sidecar frame index.html: ${sc_entry:-none}"
  if [ "$s_entry" = "$sc_entry" ] && [ "$s_entry" != "$m_entry" ]; then say "=> /ns SERVED SIDECAR ✅"
  elif [ "$s_entry" = "$m_entry" ]; then say "=> /ns SERVED MAIN ❌ (producer ignored header)"
  else say "=> MISMATCH ⚠️ (neither main nor sidecar index.html)"; fi
elif grep -qE 'UI_Layer/dist|ng/dist' "$T/s.html"; then
  shell=angular
  say "shell: Angular (/ns has no webui2 hash; browser loads /mf/shell/remoteEntry.js) -> case ①/③"
  say "balkan_s3_cloudfront_url: ${cdn:-not found}"
  [ -n "$cdn" ] && [ "$cdn" != '"balkan_s3_cloudfront_url":""' ] && say "⚠️ CDN set: browser bypasses ngssl, sidecar header ineffective"
  [ -z "$COOKIE" ] && say "note: anonymous -> PHP path always Angular login page; pass cookie to see post-login shell"
else
  shell=unknown; say "shell: unknown (no frame entry, no Angular dist). first 300 bytes:"; head -c 300 "$T/s.html"; say ""
fi
say ""

# ---- 4. assets
say "## 4. Assets (hdr/nohdr status; sidecar-only = 200/404 proves sidecar pod served it)"
classify() { # $1 path
  local a b; a="$(code "${hdr[@]}" "$H$1")"; b="$(code "${base[@]}" "$H$1")"
  local v
  if [ "$a" = 200 ] && [ "$b" != 200 ]; then v="sidecar-only ✅"
  elif [ "$a" = 200 ] && [ "$b" = 200 ]; then v="both (shared hash / fallback to main) ⚠️"
  else v="BROKEN ❌"; fi
  printf '%-75s %s/%s %s\n' "$1" "$a" "$b" "$v"
}
if [ "$shell" = frame ]; then
  for p in $(grep -oE '/mf/frame/assets/[A-Za-z0-9_.-]+\.(js|css)' "$T/s.html" | sort -u); do classify "$p"; done
  curl "${hdr[@]}" "$H$s_entry" > "$T/entry.js"
  for c in $(grep -oE '\./[A-Za-z0-9_.-]+-[A-Za-z0-9_]{8}\.(js|css)' "$T/entry.js" | sort -u | head -12); do
    classify "/mf/frame/assets/${c#./}"; done
elif [ "$shell" = angular ]; then
  rc="$(curl "${hdr[@]}" -o "$T/re.s" -w '%{http_code}' "$H/mf/shell/remoteEntry.js")"; curl "${base[@]}" -o "$T/re.m" "$H/mf/shell/remoteEntry.js"
  if [ "$rc" != 200 ]; then
    say "/mf/shell/remoteEntry.js -> $rc ($(wc -c < "$T/re.s" | tr -d ' ') bytes)"
    say "=> auth_request masquerade (401->404 HTML) when anonymous. Pass cookie (ci_session=...) to verify shell chunks."
  else
  rs="$(grep -oE '[A-Za-z_]+-[A-Za-z0-9_]{8}\.js' "$T/re.s" | sort -u | head -3 | tr '\n' ' ')"
  rm_="$(grep -oE '[A-Za-z_]+-[A-Za-z0-9_]{8}\.js' "$T/re.m" | sort -u | head -3 | tr '\n' ' ')"
  say "remoteEntry.js +hdr chunks: $rs"; say "remoteEntry.js main chunks: $rm_"
  cmp -s "$T/re.s" "$T/re.m" && say "=> remoteEntry identical to main ❌/⚠️" || say "=> remoteEntry differs from main ✅"
  for c in $(grep -oE '[A-Za-z_]+-[A-Za-z0-9_]{8}\.js' "$T/re.s" | sort -u | head -6); do classify "/mf/shell/assets/$c"; done
  fi
fi
say ""

# ---- 5. build-info
say "## 5. build-info"
bi() { grep -oE '"(version|commit|branch|deploymentSuffix)":"[^"]*"' | tr '\n' ' '; }
fb="$(curl "${hdr[@]}" "$H/mf/frame/build-info.json")"; sb="$(curl "${hdr[@]}" "$H/mf/shell/build-info.json")"
say "frame +hdr : $(printf '%s' "$fb" | bi)"
say "frame main : $(curl "${base[@]}" "$H/mf/frame/build-info.json" | bi)"
say "shell +hdr : $(printf '%s' "$sb" | bi)"
fc="$(printf '%s' "$fb" | grep -oE '"commit":"[0-9a-f]{7}' | cut -d'"' -f4)"
scm="$(printf '%s' "$sb" | grep -oE '"commit":"[0-9a-f]{7}' | cut -d'"' -f4)"
if [ -n "$fc" ] && [ -n "$scm" ] && [ "$fc" != "$scm" ]; then
  say "⚠️ LEG SKEW: /mf/frame sidecar=$fc vs /mf/shell sidecar=$scm — crane frame goes AWS leg (EKS), shell goes MP leg (qa01). Run sidecar-deploy-status."
fi
