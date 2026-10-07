#!/usr/bin/env bash
# Usage: check_report.sh <report-dir> [secret ...]
# Fails (exit 1) on broken relative <img src> links or if any secret string appears in the HTML.
# The password is also read from $LRS_PASSWORD when set.
set -u
dir="${1:?report dir required}"
shift
secrets=("$@")
[ -n "${LRS_PASSWORD:-}" ] && secrets+=("$LRS_PASSWORD")
bad=0
cd "$dir" || exit 2
for f in *.html; do
  [ -e "$f" ] || continue
  total=0; missing=0
  while IFS= read -r src; do
    total=$((total + 1))
    if [ ! -f "$src" ]; then echo "MISSING $f -> $src"; missing=$((missing + 1)); bad=1; fi
  done < <(grep -o '<img src="[^"]*"' "$f" | sed 's/<img src="//; s/"$//')
  echo "$f: img=$total missing=$missing"
  for s in "${secrets[@]}"; do
    [ -n "$s" ] && grep -qF -- "$s" "$f" && { echo "SECRET FOUND in $f"; bad=1; }
  done
done
[ "$bad" -eq 0 ] && echo "OK" || echo "PROBLEMS FOUND"
exit "$bad"
