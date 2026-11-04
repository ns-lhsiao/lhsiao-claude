#!/usr/bin/env bash
# chrome-clean.sh — clean up leftover Playwright Chrome + stale Chrome profile lock.
#
# Kills orphaned @playwright/cli daemons (cliDaemon.js) and their headless
# Chrome children, deletes their temp profiles, and removes Chrome's
# SingletonLock only when the owning PID is dead (stale lock makes Dock
# launch silently do nothing).
#
# Usage: chrome-clean.sh [-n|--dry-run] [-h|--help]
# Note: run outside Claude sandbox (ps/kill blocked inside it).

set -uo pipefail

DRY=0
case "${1:-}" in
  -n|--dry-run) DRY=1 ;;
  -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown arg: $1" >&2; exit 2 ;;
esac

DAEMON_PAT='playwright-core/lib/entry/cliDaemon.js'
PROFILE_PAT='playwright_chromiumdev_profile-'
TMP_ROOT="${TMPDIR:-/tmp}"
# Sandbox may rewrite TMPDIR; Playwright profiles live in real user temp.
REAL_TMP="$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null || echo "$TMP_ROOT")"
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome"

run() { if (( DRY )); then echo "  [dry-run] $*"; else "$@"; fi; }

# pgrep avoids grep self-match on own command line.
list_pids() { pgrep -f "$1" 2>/dev/null | grep -vx "$$" || true; }

echo "== Playwright daemons"
daemons=$(list_pids "$DAEMON_PAT")
if [[ -z "$daemons" ]]; then
  echo "  none"
else
  for p in $daemons; do
    sess=$(ps -o command= -p "$p" 2>/dev/null | awk '{print $NF}')
    echo "  pid $p  session=$sess  age=$(ps -o etime= -p "$p" | tr -d ' ')"
  done
fi

echo "== Playwright headless Chrome"
browsers=$(list_pids "$PROFILE_PAT")
echo "  ${browsers:+$(echo "$browsers" | wc -l | tr -d ' ') process(es)}${browsers:-none}" | head -1

if [[ -n "$daemons$browsers" ]]; then
  echo "== Killing"
  # SIGTERM first; daemons often ignore it, so escalate to SIGKILL.
  run kill $daemons $browsers 2>/dev/null
  if (( ! DRY )); then
    perl -e 'select(undef,undef,undef,2)'
    left=$(list_pids "$DAEMON_PAT"; list_pids "$PROFILE_PAT")
    if [[ -n "$left" ]]; then
      echo "  SIGTERM ignored by: $(echo $left) -> SIGKILL"
      kill -9 $left 2>/dev/null
      perl -e 'select(undef,undef,undef,1)'
    fi
  fi
fi

echo "== Temp profiles"
shopt -s nullglob
profiles=("$REAL_TMP"/${PROFILE_PAT}*)
if (( ${#profiles[@]} == 0 )); then
  echo "  none"
elif [[ -n "$(list_pids "$PROFILE_PAT")" ]] && (( ! DRY )); then
  echo "  skipped: Playwright Chrome still running"
else
  echo "  ${#profiles[@]} dir(s), $(du -shc "${profiles[@]}" 2>/dev/null | tail -1 | cut -f1)"
  run rm -rf "${profiles[@]}"
fi

echo "== Chrome SingletonLock"
lock="$CHROME_DIR/SingletonLock"
if [[ -L "$lock" ]]; then
  target=$(readlink "$lock")           # format: <hostname>-<pid>
  owner=${target##*-}
  if ps -p "$owner" >/dev/null 2>&1; then
    echo "  held by live pid $owner — ok"
  else
    echo "  STALE (pid $owner dead) -> removing Singleton*"
    run rm -f "$CHROME_DIR"/Singleton{Lock,Socket,Cookie}
  fi
else
  echo "  none"
fi

echo "== Result"
echo "  daemons left: $(list_pids "$DAEMON_PAT" | grep -c . || true)"
echo "  pw chrome left: $(list_pids "$PROFILE_PAT" | grep -c . || true)"
main=$(pgrep -x "Google Chrome" | while read -r p; do
  ps -o command= -p "$p" | grep -q -- "$PROFILE_PAT" || echo "$p"; done)
echo "  your Chrome: ${main:-not running}"
