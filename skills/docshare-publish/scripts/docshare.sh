#!/usr/bin/env bash
# docshare.sh - publish/list/delete files on https://docshare.netskope.com (TeamSkope Docs)
#
# Auth: Google IAP cookie stored in ~/.claude/connections/docshare.json (same
# convention + directory as the jenkins/sumo/spinnaker skills), shape:
#   { "host": "docshare.netskope.com", "cookie_header": "name1=val1; name2=val2" }
# The cookie is a session-type IAP token; when it expires every call redirects to
# accounts.google.com. Refresh it with:  docshare.sh login  (then `capture` if SSO
# was needed), or `relogin` from an interactive terminal.
#
# Usage:
#   docshare.sh publish <file> [shortcode]   # upload; prints the live URL
#   docshare.sh list                         # table of your files (name / shortcode / id)
#   docshare.sh delete <shortcode|id>        # delete by shortcode or file id
#   docshare.sh get <shortcode|url> [outfile] # fetch published content (stdout, or save to outfile - use for PDFs)
#   docshare.sh login | capture | relogin    # (re)authenticate, see Auth above
#   docshare.sh check                        # verify cookie still valid

set -euo pipefail

BASE="https://docshare.netskope.com"
CONN_FILE="${DOCSHARE_CONN_FILE:-$HOME/.claude/connections/docshare.json}"
PROFILE="${DOCSHARE_PROFILE:-$HOME/.playwright-cli-profile-netskope-sso}"

die() { echo "ERROR: $*" >&2; exit 1; }

urldecode() {
  python3 -c 'import sys, urllib.parse; sys.stdout.write(urllib.parse.unquote_plus(sys.argv[1]))' "$1"
}

require_cookie() {
  [ -f "$CONN_FILE" ] || die "no connection file at $CONN_FILE - run: $0 login"
  [ -s "$CONN_FILE" ] || die "connection file $CONN_FILE is empty - run: $0 login"
  python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$CONN_FILE" 2>/dev/null \
    || die "connection file $CONN_FILE is not valid JSON - delete it and run: $0 login"
  [ -n "$(cookie)" ] || die "no cookie_header in $CONN_FILE - run: $0 login"
}

# Emit the cookie header value as a single clean line. Reads the cookie_header field
# from the JSON connection file; strips an optional leading "Cookie:" prefix and any
# CR/LF so a stray newline can't inject extra header lines into the curl request.
# Assumes $CONN_FILE is valid JSON -- require_cookie validates that up front.
cookie() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
h = (d.get("cookie_header") or "").replace("\r", " ").replace("\n", " ").strip()
if h[:7].lower() == "cookie:":
    h = h[7:].strip()
sys.stdout.write(h)
' "$CONN_FILE"
}

# Three-state: 0 = cookie valid, 1 = cookie expired (redirected to Google login),
# 2 = the check itself couldn't run (network/DNS/TLS/timeout). Distinguishing 1 from
# 2 keeps "run relogin" advice from firing on an unrelated connectivity problem.
is_valid() {
  local redirect
  redirect=$(curl -sS -o /dev/null -w '%{redirect_url}' --max-time 20 \
               -H "Cookie: $(cookie)" "$BASE/") || return 2
  # no redirect (200 on the homepage) or a same-origin (absolute or relative) redirect
  # means the cookie authenticated fine; only Google's own login redirect is invalid.
  case "$redirect" in
    ""|"$BASE"/*|"$BASE"|/*) return 0 ;;
    *)                       return 1 ;;
  esac
}

guard_valid() {
  is_valid; local rc=$?
  case "$rc" in
    0) return 0 ;;
    1) die "cookie expired (redirects to Google login) - run: $0 login" ;;
    *) die "could not reach $BASE (network/DNS/TLS?) - not a cookie problem" ;;
  esac
}

cmd_check() {
  require_cookie
  is_valid; local rc=$?
  case "$rc" in
    0) echo "OK - cookie valid" ;;
    1) die "cookie expired - run: $0 login" ;;
    *) die "could not reach $BASE (network/DNS/TLS?) - not a cookie problem" ;;
  esac
}

cmd_publish() {
  local file="${1:-}" shortcode="${2:-}"
  [ -n "$file" ] || die "usage: $0 publish <file> [shortcode]"
  [ -f "$file" ] || die "no such file: $file"
  shortcode="${shortcode#/}"
  if [ -n "$shortcode" ] && ! printf '%s' "$shortcode" | grep -qE '^[A-Za-z0-9-]+$'; then
    die "invalid shortcode '$shortcode' - letters, numbers, and hyphens only"
  fi
  require_cookie; guard_valid

  local ctype="text/html"
  case "$file" in
    *.html|*.htm) ctype="text/html" ;;
    *.md)         ctype="text/markdown" ;;
    *.pdf)        ctype="application/pdf" ;;
    *.txt)        ctype="text/plain" ;;
    *)            ctype="application/octet-stream" ;;
  esac

  local args=(-F "file=@${file};type=${ctype}")
  # --form-string (not -F) for shortcode: a value starting with @ or < would
  # otherwise be interpreted by curl as "read this local file", not literal text.
  [ -n "$shortcode" ] && args+=(--form-string "shortcode=${shortcode}")

  local redirect
  redirect=$(curl -sS -o /dev/null -w '%{redirect_url}' --max-time 120 \
               -H "Cookie: $(cookie)" "${args[@]}" "$BASE/upload")

  case "$redirect" in
    *success*)
      if [ -n "$shortcode" ]; then
        echo "$BASE/$shortcode"
      else
        # auto-shortcode: resolve the live URL via exact filename match
        local code
        code=$(_rows | awk -F'\t' -v f="$(basename "$file")" '$1==f {print $2; exit}')
        [ -n "$code" ] && [ "$code" != "/?" ] \
          || die "uploaded but could not resolve auto-generated shortcode"
        echo "$BASE$code"
      fi
      ;;
    *error*)   die "upload failed: $(urldecode "${redirect#*error=}")" ;;
    *google.com*) die "cookie expired mid-request - run: $0 relogin" ;;
    *)         die "unexpected response: $redirect" ;;
  esac
}

# Parse homepage into rows: "<filename>\t<shortcode>\t<file_id>"
_rows() {
  require_cookie; guard_valid
  curl -sS --max-time 30 -H "Cookie: $(cookie)" "$BASE/" \
    | python3 -c '
import sys, re, html
h = sys.stdin.read()
# each file row has: <p ...>FILENAME</p> ... href="/SHORTCODE" ... /files/ID/edit
# split on the edit-link anchor which terminates each row block
for m in re.finditer(r"/files/([A-Za-z0-9]{20})/edit", h):
    fid = m.group(1)
    block = h[max(0, m.start()-3200):m.start()]
    fn = re.findall(r"<p[^>]*>\s*([^<]+?\.[A-Za-z0-9]{1,5})\s*</p>", block, re.I)
    # shortcode link renders as <a href="/CODE" target="_blank">/CODE</a>
    sc = re.findall(r"href=\"/([A-Za-z0-9\-]+)\"[^>]*target", block)
    name = html.unescape(fn[-1]).strip() if fn else "?"
    code = sc[-1] if sc else "?"
    print(f"{name}\t/{code}\t{fid}")
'
}

cmd_list() {
  printf '%-52s %-28s %s\n' "FILE" "SHORTCODE" "ID"
  _rows | while IFS=$'\t' read -r name code id; do
    printf '%-52s %-28s %s\n' "$name" "$code" "$id"
  done
}

cmd_delete() {
  local target="${1:-}"
  [ -n "$target" ] || die "usage: $0 delete <shortcode|id>"
  require_cookie; guard_valid

  # a leading "/" always forces shortcode resolution, even if what follows
  # happens to look like a 20-char file id (avoids ambiguity between the two).
  local forced_shortcode=0
  case "$target" in /*) forced_shortcode=1 ;; esac
  target="${target#/}"

  local id="$target"
  if [ "$forced_shortcode" = 1 ] || ! printf '%s' "$target" | grep -qE '^[A-Za-z0-9]{20}$'; then
    id=$(_rows | awk -F'\t' -v c="/$target" '$2==c {print $3; exit}')
    [ -n "$id" ] || die "no file with shortcode /$target"
  fi

  local redirect
  redirect=$(curl -sS -o /dev/null -w '%{redirect_url}' --max-time 30 \
               -H "Cookie: $(cookie)" -X POST "$BASE/files/$id/delete")
  case "$redirect" in
    *success*)    echo "deleted $id" ;;
    *google.com*) die "cookie expired mid-request - run: $0 relogin" ;;
    *)            die "delete failed: $redirect" ;;
  esac
}

cmd_get() {
  local sc="${1:-}" outfile="${2:-}"
  [ -n "$sc" ] || die "usage: $0 get <shortcode|url> [outfile]"
  # accept a full docshare URL, not just a bare shortcode
  sc="${sc#"$BASE"/}"
  sc="${sc#https://docshare.netskope.com/}"
  sc="${sc#http://docshare.netskope.com/}"
  require_cookie; guard_valid
  if [ -n "$outfile" ]; then
    curl -sS --max-time 30 -H "Cookie: $(cookie)" -o "$outfile" "$BASE/${sc#/}"
    echo "saved to $outfile"
  else
    curl -sS --max-time 30 -H "Cookie: $(cookie)" "$BASE/${sc#/}"
  fi
}

# Save playwright storage state to a writable path and extract the docshare cookies
# into the JSON connection file. Returns 0 on success, 1 if not authenticated yet.
# "Authenticated" REQUIRES the __Host-GCP_IAP_AUTH_TOKEN_ cookie -- an unauthenticated
# visit still receives GCP_IAP_XSRF_NONCE_* cookies, so counting "any docshare cookie"
# falsely reports success (and then check/publish 302s to Google). playwright-cli
# sandboxes state-save to a few allowed roots, so try the cwd-relative path (its usual
# default) FIRST, then fall back to alongside the connection file.
_capture_cookies() {
  mkdir -p "$(dirname "$CONN_FILE")"; chmod 700 "$(dirname "$CONN_FILE")" 2>/dev/null || true
  local state saved=0
  for state in "./.playwright-cli/state.json" "$(dirname "$CONN_FILE")/docshare-state.json"; do
    mkdir -p "$(dirname "$state")" 2>/dev/null || continue
    playwright-cli state-save "$state" >/dev/null 2>&1 || { rm -f "$state"; continue; }
    saved=1
    # python reads the saved state, writes the connection JSON, and reports the count.
    # single-quoted -c body -> no backslash escapes (bash passes them through literally
    # and python's f-string parser then rejects \"); concatenate strings instead.
    python3 -c '
import json, sys
state_path, conn_path, host = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(state_path))
cks = [c for c in d.get("cookies", []) if "docshare" in c.get("domain", "")]
# real auth needs the IAP auth token, not just the XSRF nonce cookies
if not any(c["name"].startswith("__Host-GCP_IAP_AUTH_TOKEN") for c in cks):
    sys.exit(3)
header = "; ".join(c["name"] + "=" + c["value"] for c in cks)
json.dump({"host": host, "cookie_header": header}, open(conn_path, "w"), indent=2)
print(len(cks), file=sys.stderr)
' "$state" "$CONN_FILE" "${BASE#https://}" 2>/dev/null
    local rc=$?
    rm -f "$state"
    if [ "$rc" = 3 ]; then return 1; fi      # state saved but no auth token = not logged in
    [ "$rc" = 0 ] || continue
    chmod 600 "$CONN_FILE"
    return 0
  done
  [ "$saved" = 1 ] && return 1               # state saved but extraction never succeeded = not logged in
  die "state-save failed under every allowed root (cwd/.playwright-cli, $(dirname "$CONN_FILE")) - is playwright-cli's file-access sandbox blocking all of them?"
}

# True if a playwright browser is already open (avoids the close+reopen flash).
_browser_open() { playwright-cli snapshot >/dev/null 2>&1; }

# Open (or reuse) a headed browser on docshare. If one is already open, just navigate.
# Otherwise, first clear Chromium's session-restore state in the persistent profile:
# a profile that wasn't closed cleanly last time makes Chromium auto-reopen the previous
# window on launch, so you'd get TWO windows (the restored one + the one playwright
# drives). playwright only controls its own, so the restored window is an untracked
# duplicate -- deleting the Sessions/Current-* files prevents it.
_open_browser() {
  if _browser_open; then
    playwright-cli goto "$BASE/" >/dev/null 2>&1 || true
    return 0
  fi
  if [ -d "$PROFILE/Default" ]; then
    rm -rf "$PROFILE/Default/Sessions" 2>/dev/null || true
    rm -f "$PROFILE/Default/Current Session" "$PROFILE/Default/Current Tabs" \
          "$PROFILE/Default/Last Session"    "$PROFILE/Default/Last Tabs" 2>/dev/null || true
  fi
  playwright-cli open "$BASE/" --headed --profile="$PROFILE" >/dev/null 2>&1 \
    || die "failed to open browser via playwright-cli"
}

# Agent-friendly, NON-interactive: ensure a browser is on docshare and, if the profile
# is already authenticated, capture the cookie immediately. If not logged in, leave the
# browser open and tell the caller to finish Google SSO then run `capture`. No
# `read`/stdin. Reuses an already-open browser instead of closing + reopening it, so a
# window you already logged into isn't yanked away and replaced.
cmd_login() {
  command -v playwright-cli >/dev/null || die "playwright-cli not installed"
  _open_browser
  if _capture_cookies 2>/dev/null; then
    playwright-cli close >/dev/null 2>&1 || true
    echo "already authenticated - cookie captured, no SSO needed"
    cmd_check
  else
    echo "browser open but not logged in - complete Google SSO in the window, then run: $0 capture" >&2
    return 2
  fi
}

# Agent-friendly, NON-interactive: after Google SSO is done in the open browser,
# extract the cookie. Pairs with `login`.
cmd_capture() {
  command -v playwright-cli >/dev/null || die "playwright-cli not installed"
  _capture_cookies || die "no IAP auth token in the browser session (only got XSRF nonce cookies) - is Google SSO actually finished?"
  playwright-cli close >/dev/null 2>&1 || true
  cmd_check
}

# Interactive, for a real terminal: open browser, pause for SSO via Enter, then
# capture. Falls back to the login/capture split when there's no tty to read from
# (e.g. driven by an agent) so it never hangs on a `read` that can't be answered.
cmd_relogin() {
  command -v playwright-cli >/dev/null || die "playwright-cli not installed"
  if [ ! -t 0 ]; then
    echo "no interactive terminal - use the two-step flow instead:" >&2
    echo "  1) $0 login      (opens browser; captures now if already authed)" >&2
    echo "  2) $0 capture    (after you finish Google SSO in that browser)" >&2
    cmd_login
    return $?
  fi
  _open_browser
  # already logged in? skip the SSO wait entirely.
  if _capture_cookies 2>/dev/null; then
    playwright-cli close >/dev/null 2>&1 || true
    echo "already authenticated - no SSO needed"
    cmd_check
    return
  fi
  echo "complete Google SSO in the browser window, then press Enter here..." >&2
  read -r _
  cmd_capture
}

# hard dependencies (playwright-cli is only needed for login/capture/relogin, so it's
# checked in those subcommands instead of here).
for _dep in curl python3; do
  command -v "$_dep" >/dev/null || die "required command '$_dep' not found in PATH"
done

sub="${1:-}"; shift || true
case "$sub" in
  publish|upload) cmd_publish "$@" ;;
  list|ls)        cmd_list "$@" ;;
  delete|rm)      cmd_delete "$@" ;;
  get|cat)        cmd_get "$@" ;;
  login)          cmd_login "$@" ;;
  capture)        cmd_capture "$@" ;;
  relogin)        cmd_relogin "$@" ;;
  check)          cmd_check "$@" ;;
  *) echo "usage: $0 {publish <file> [shortcode]|list|delete <target>|get <sc|url> [outfile]|login|capture|relogin|check}" >&2; exit 2 ;;
esac
