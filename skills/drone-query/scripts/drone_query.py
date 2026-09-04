#!/usr/bin/env python3
"""
drone_query.py -- read-only Drone CI REST gate.

This is the ONLY way the drone-query skill talks to Drone. All operations are
GET-only (no starting, promoting, cancelling, or deleting builds). Step logs
are tail-bounded so a multi-MB log can't blow up the agent context.

Usage:
  drone_query.py from-url '<any drone/drone-ext/ci-drone build URL>'
  drone_query.py get-build --repo netSkope/service --build 159397
  drone_query.py trace-failure --repo netSkope/service --build 159397 [--drone-yml]
  drone_query.py step-log --repo netSkope/service --build 159397 --stage 1 --step 4
  drone_query.py list-builds --repo netSkope/service [--page 1] [--per-page 25]
  drone_query.py latest --repo netSkope/service --branch develop
  drone_query.py find-ref --repo netSkope/service [--sha X | --branch X | --pr N] [--max-pages 10]
  drone_query.py deploy-history --repo netSkope/service [--max-pages 10]

Netskope Drone repos carry their own `visibility` flag independent of the
underlying GitHub repo's visibility. Public-visibility repos serve builds,
stages/steps, and logs over the REST API with NO authentication -- verified
live against netSkope/service and netSkope/webui2, and matching the
convention used by existing netSkope scripts (ngbase-helm-chart/scripts/*).

For repos with non-public visibility, requests come back 401. This script
retries once with a bearer token read from ~/.drone-token if that file
exists. Get a token at https://drone.netskope.io/account and save it there
(chmod 600 recommended) -- no other setup is needed.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CANONICAL_HOST = "drone.netskope.io"
KNOWN_HOSTS = ("drone.netskope.io", "drone-ext.netskope.io", "ci-drone.netskope.io")
TOKEN_PATH = Path.home() / ".drone-token"

DEFAULT_TAIL_KB = 64
MAX_TAIL_KB = 256
HTTP_TIMEOUT = 30
DEFAULT_PER_PAGE = 25
DEFAULT_MAX_PAGES = 10

# UNVERIFIED: netskope's actual promotion event name(s) were never confirmed
# live against a repo that uses Drone promotions (see design.md open
# questions). A "0 deploys found" result may mean the event name differs,
# not "no deploys" -- confirm against a real promoting repo before trusting it.
DEPLOY_EVENTS = {"promote", "rollback"}

# Light PII / secret scrubbing on step log output, matching the spirit of
# jenkins-query's scrub(). Deliberately does NOT redact bare 40-char hex
# strings -- those are almost always git commit SHAs in build logs.
_PII_PATTERNS = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    (re.compile(r"(?i)\b(?:bearer\s+|token\s*=\s*|api[_-]?key\s*=\s*|secret\s*=\s*)[A-Za-z0-9._\-]{12,}"),
     lambda m: m.group(0).split("=")[0].rstrip() + "=[REDACTED]" if "=" in m.group(0)
               else "Bearer [REDACTED]"),
    (re.compile(r"(?i)\bpassword\s*=\s*\S+"), "password=[REDACTED]"),
]


# ============================================================================
# Helpers
# ============================================================================

def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def scrub(text: str) -> str:
    for pattern, repl in _PII_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _read_token() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        token = TOKEN_PATH.read_text().strip()
    except OSError as e:
        die(f"could not read {TOKEN_PATH}: {e}")
    return token or None


# Repos confirmed (this process invocation) to need a token, so later calls
# in the same run -- e.g. _iter_builds paging up to --max-pages -- skip the
# doomed unauthenticated attempt and go straight to the authenticated one.
_needs_token: set[tuple[str, str]] = set()


def _token_instructions(owner: str, repo: str) -> str:
    return (
        f"repo {owner}/{repo} is not public-visibility on Drone (401 Unauthorized).\n"
        f"  1) Get a personal Drone token: https://{CANONICAL_HOST}/account\n"
        f"  2) Save it to {TOKEN_PATH} (a plain text file, just the token)\n"
        f"  3) Re-run the command -- the token is sent as a bearer header, never as an argv."
    )


def _token_invalid_instructions(owner: str, repo: str) -> str:
    return (
        f"still 401 Unauthorized for {owner}/{repo} even with a token from {TOKEN_PATH}.\n"
        f"  The repo may be non-public-visibility AND the token could be invalid, expired,\n"
        f"  or lack access to this repo -- check/regenerate it at https://{CANONICAL_HOST}/account."
    )


def http_get_json(path: str, *, owner: str = "", repo: str = "") -> dict | list:
    """GET https://<canonical>/api<path>. Unauthenticated first; on 401, retry
    once with ~/.drone-token if present, and remember for the rest of this
    process that (owner, repo) needs a token so later calls skip straight to
    the authenticated request. Returns the parsed JSON body."""
    url = f"https://{CANONICAL_HOST}/api{path}"

    def _request(token: str | None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()

    repo_key = (owner, repo)
    token = _read_token() if repo_key in _needs_token else None

    try:
        data = _request(token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            if token:
                # Already using ~/.drone-token and still 401 -- it's not a
                # matter of switching credentials, so fail loud now.
                die(_token_invalid_instructions(owner, repo))
            _needs_token.add(repo_key)
            token = _read_token()
            if not token:
                die(_token_instructions(owner, repo))
            try:
                data = _request(token)
            except urllib.error.HTTPError as e2:
                if e2.code == 401:
                    die(_token_invalid_instructions(owner, repo))
                die(f"HTTP {e2.code} from {url}")
            except urllib.error.URLError as e2:
                die(f"network error for {url}: {e2.reason}")
        elif e.code == 404:
            die(f"404 Not Found at {url} -- check owner/repo/build number")
        else:
            body = e.read().decode("utf-8", errors="replace")[:500]
            die(f"HTTP {e.code} from {url}\n  body: {body}")
    except urllib.error.URLError as e:
        die(f"network error for {url}: {e.reason}")

    if not data:
        return {}
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        die(f"non-JSON response from {url}: {e}\n  body: {data[:200]!r}")


# ============================================================================
# URL parsing
# ============================================================================

_WEB_PATH_RE = re.compile(r"^/([^/]+)/([^/]+)/(\d+)/?$")
_API_PATH_RE = re.compile(r"^/api/repos/([^/]+)/([^/]+)/builds/(\d+)/?$")


def parse_drone_url(url: str) -> tuple[str, str, str]:
    """Extract (owner, repo, build) from a Drone URL on any known host, in
    either the web form or the API form. Parses via urlparse first (so a
    trailing ?query or #fragment, e.g. from a UI "console tab" link, doesn't
    break the match) and regexes only the path. Always normalize to the
    canonical host when constructing subsequent API calls (callers use
    owner/repo/build directly, so no host string needs to survive past this
    function)."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.hostname not in KNOWN_HOSTS:
        die(
            f"could not parse Drone URL: {url}\n"
            f"  host must be one of: {', '.join(KNOWN_HOSTS)}"
        )
    for pattern in (_WEB_PATH_RE, _API_PATH_RE):
        m = pattern.match(parsed.path)
        if m:
            owner, repo, build = m.groups()
            return owner, repo, build
    die(
        f"could not parse Drone URL: {url}\n"
        f"  expected path: /<owner>/<repo>/<build>\n"
        f"  or:            /api/repos/<owner>/<repo>/builds/<build>"
    )


# ============================================================================
# Log fetch + bounding
# ============================================================================

def fetch_step_log(owner: str, repo: str, build: str, stage: int, step: int, tail_kb: int) -> tuple[str, bool, int, int]:
    """Returns (text, truncated, original_bytes, effective_tail_kb) --
    effective_tail_kb is tail_kb clamped to [1, MAX_TAIL_KB], for callers to
    report accurately instead of echoing back an unclamped CLI value."""
    tail_kb = min(max(tail_kb, 1), MAX_TAIL_KB)
    tail_bytes = tail_kb * 1024

    lines = http_get_json(
        f"/repos/{owner}/{repo}/builds/{build}/logs/{stage}/{step}",
        owner=owner, repo=repo,
    )
    if not isinstance(lines, list):
        lines = []
    lines.sort(key=lambda line: line.get("pos", 0))
    full_bytes = "".join(line.get("out") or "" for line in lines).encode("utf-8")
    original_bytes = len(full_bytes)

    truncated = original_bytes > tail_bytes
    if truncated:
        text = full_bytes[-tail_bytes:].decode("utf-8", errors="replace")
        nl = text.find("\n")
        if nl > 0:
            text = text[nl + 1:]
    else:
        text = full_bytes.decode("utf-8")

    return scrub(text), truncated, original_bytes, tail_kb


def find_failing_step(build_data: dict) -> tuple[int, int, dict, dict] | None:
    """Walk stages[].steps[] and return (stage_number, step_number, stage,
    step) for the first step whose status is 'failure' or exit_code is
    non-zero, numbers 1-based. Drone's model is flat (no nested-pipeline
    recursion like Spinnaker)."""
    for stage_number, stage in enumerate(build_data.get("stages", []), start=1):
        for step_number, step in enumerate(stage.get("steps", []), start=1):
            if step.get("status") == "failure" or step.get("exit_code", 0) != 0:
                return stage_number, step_number, stage, step
    return None


# ============================================================================
# Subcommands
# ============================================================================

def cmd_from_url(args) -> None:
    owner, repo, build = parse_drone_url(args.url)
    if args.format == "json":
        print(json.dumps({"owner": owner, "repo": repo, "build": build}, indent=2))
        return
    print(f"owner: {owner}")
    print(f"repo:  {repo}")
    print(f"build: {build}")
    print(f"\nNext step: python3 \"$SCRIPT\" get-build --repo {owner}/{repo} --build {build}")


def _split_repo(repo: str) -> tuple[str, str]:
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        die(f"--repo must be '<owner>/<repo>', got {repo!r}")
    return parts[0], parts[1]


def _print_build_summary(b: dict) -> None:
    print(f"Build #{b.get('number')}  status={b.get('status')}  event={b.get('event')}")
    print(f"  branch: {b.get('source')} -> {b.get('target')}  ref: {b.get('ref')}")
    print(f"  after:  {b.get('after')}")
    print(f"  author: {b.get('author_login') or b.get('author_name')}")
    print(f"  link:   {b.get('link')}")


def cmd_get_build(args) -> None:
    owner, repo = _split_repo(args.repo)
    data = http_get_json(f"/repos/{owner}/{repo}/builds/{args.build}", owner=owner, repo=repo)

    if args.format == "json":
        print(json.dumps(data, indent=2))
        return

    _print_build_summary(data)
    print("  stages:")
    for stage_idx, stage in enumerate(data.get("stages", []), start=1):
        print(f"    [{stage_idx}] {stage.get('name') or '-'}  status={stage.get('status') or '-'}")
        for step_idx, step in enumerate(stage.get("steps", []), start=1):
            print(f"      ({step_idx}) {(step.get('name') or '-'):<24s} "
                  f"status={(step.get('status') or '-'):<10s} exit_code={step.get('exit_code')}")


def cmd_trace_failure(args) -> None:
    owner, repo = _split_repo(args.repo)
    data = http_get_json(f"/repos/{owner}/{repo}/builds/{args.build}", owner=owner, repo=repo)

    _print_build_summary(data)

    hit = find_failing_step(data)
    if hit is None:
        print("\nNo failing step found (build did not fail at the step level).")
        return

    stage_number, step_number, stage, step = hit

    print(f"\nFailing step: stage[{stage_number}]={stage.get('name')} "
          f"step[{step_number}]={step.get('name')}  exit_code={step.get('exit_code')}")

    text, truncated, original_bytes, effective_tail_kb = fetch_step_log(
        owner, repo, args.build, stage_number, step_number, args.tail_kb,
    )
    if truncated:
        print(f"  (log truncated to last {effective_tail_kb}KB; original was {original_bytes} bytes)")
    print("-" * 72)
    print(text)

    if args.drone_yml:
        after = data.get("after")
        print("-" * 72)
        if not after:
            print("(no .drone.yml fetch: build has no 'after' commit SHA)")
            return
        yml = _fetch_drone_yml(owner, repo, after)
        if yml is None:
            print(f"(.drone.yml at {after[:12]} could not be fetched -- continuing without it)")
        else:
            print(f".drone.yml @ {after[:12]}:")
            print(yml)


def _fetch_drone_yml(owner: str, repo: str, sha: str) -> str | None:
    """Fetch .drone.yml pinned at the build's commit via `gh api`, matching
    EP drone-ci-debugger's SHA-pinned approach. Best-effort: any failure
    (gh not installed, gh not authed, file missing at that SHA) degrades to
    None rather than aborting the trace."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/contents/.drone.yml?ref={sha}", "--jq", ".content"],
            capture_output=True, text=True, timeout=HTTP_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return base64.b64decode(result.stdout.strip()).decode("utf-8", errors="replace")
    except Exception:
        return None


def cmd_step_log(args) -> None:
    owner, repo = _split_repo(args.repo)
    text, truncated, original_bytes, effective_tail_kb = fetch_step_log(
        owner, repo, args.build, args.stage, args.step, args.tail_kb,
    )
    if args.format == "json":
        print(json.dumps({
            "text": text, "truncated": truncated, "originalBytes": original_bytes,
            "tailKb": effective_tail_kb,
        }, indent=2))
        return
    print(f"# log for {args.repo} build {args.build} stage[{args.stage}] step[{args.step}]")
    print(f"# original size: {original_bytes} bytes  truncated: {truncated}  tail: {effective_tail_kb} KB")
    print("-" * 72)
    print(text)


def cmd_list_builds(args) -> None:
    owner, repo = _split_repo(args.repo)
    qs = urllib.parse.urlencode({"page": args.page, "per_page": args.per_page})
    data = http_get_json(f"/repos/{owner}/{repo}/builds?{qs}", owner=owner, repo=repo)
    builds = data if isinstance(data, list) else []

    if args.format == "json":
        print(json.dumps(builds, indent=2))
        return

    print(f"{len(builds)} build(s) for {args.repo} (page {args.page}):")
    for b in builds:
        print(f"  #{b.get('number') or '-':<8} {b.get('status') or '-':<10} {b.get('event') or '-':<14} "
              f"{b.get('source') or '-'}->{b.get('target') or '-':<16} {b.get('author_login') or '-'}")


def cmd_latest(args) -> None:
    owner, repo = _split_repo(args.repo)
    qs = urllib.parse.urlencode({"branch": args.branch})
    data = http_get_json(f"/repos/{owner}/{repo}/builds/latest?{qs}", owner=owner, repo=repo)

    if args.format == "json":
        print(json.dumps(data, indent=2))
        return
    _print_build_summary(data)


def _iter_builds(owner: str, repo: str, max_pages: int, per_page: int = DEFAULT_PER_PAGE):
    """Yield (page, builds) newest-first, up to max_pages. Stops early if a
    page comes back empty (end of history)."""
    for page in range(1, max_pages + 1):
        qs = urllib.parse.urlencode({"page": page, "per_page": per_page})
        data = http_get_json(f"/repos/{owner}/{repo}/builds?{qs}", owner=owner, repo=repo)
        builds = data if isinstance(data, list) else []
        if not builds:
            return
        yield page, builds


def _scan_builds(owner: str, repo: str, max_pages: int, predicate) -> tuple[list, int]:
    """Page through build history newest-first via _iter_builds, collecting
    every build matching predicate. Returns (matches, scanned_pages)."""
    matches = []
    scanned_pages = 0
    for page, builds in _iter_builds(owner, repo, max_pages):
        scanned_pages = page
        matches.extend(b for b in builds if predicate(b))
    return matches, scanned_pages


def _print_cap_notice(scanned_pages: int, max_pages: int, subject: str) -> None:
    if scanned_pages >= max_pages:
        print(f"  Scan cap ({max_pages} pages) reached -- {subject} may exist further back; "
              f"retry with a higher --max-pages.")


def cmd_find_ref(args) -> None:
    owner, repo = _split_repo(args.repo)
    if not any([args.sha, args.branch, args.pr]):
        die("find-ref requires one of --sha, --branch, --pr")

    pr_ref = f"refs/pull/{args.pr}/head" if args.pr else None

    def matches_ref(b: dict) -> bool:
        if args.sha and (b.get("after") or "").startswith(args.sha):
            return True
        if args.branch and (b.get("source") == args.branch or b.get("target") == args.branch):
            return True
        return bool(pr_ref and b.get("ref") == pr_ref)

    matches, scanned_pages = _scan_builds(owner, repo, args.max_pages, matches_ref)

    if args.format == "json":
        print(json.dumps({"matches": matches, "scannedPages": scanned_pages}, indent=2))
        return

    if not matches:
        print(f"No matching build found in {scanned_pages} page(s) scanned.")
        _print_cap_notice(scanned_pages, args.max_pages, "the ref")
        return

    print(f"{len(matches)} matching build(s):")
    for b in matches:
        print(f"  #{b.get('number') or '-':<8} {b.get('status') or '-':<10} {b.get('event') or '-':<14} "
              f"after={((b.get('after') or '')[:12]):<14} ref={b.get('ref')}")


def cmd_deploy_history(args) -> None:
    owner, repo = _split_repo(args.repo)
    matches, scanned_pages = _scan_builds(
        owner, repo, args.max_pages, lambda b: b.get("event") in DEPLOY_EVENTS,
    )

    if args.format == "json":
        print(json.dumps({"deploys": matches, "scannedPages": scanned_pages}, indent=2))
        return

    print(f"{len(matches)} deploy event(s) for {args.repo} ({scanned_pages} page(s) scanned):")
    for b in matches:
        print(f"  #{b.get('number') or '-':<8} {b.get('status') or '-':<10} {b.get('event') or '-':<10} "
              f"target={b.get('deploy_to') or b.get('target')}")
    if not matches:
        _print_cap_notice(scanned_pages, args.max_pages, "older deploys")


# ============================================================================
# CLI
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="drone_query",
        description="Read-only Drone CI skill gate. All operations are GET.",
    )
    p.add_argument("--format", choices=["pretty", "json"], default="pretty")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=["pretty", "json"], default=argparse.SUPPRESS)

    with_repo = argparse.ArgumentParser(add_help=False, parents=[common])
    with_repo.add_argument("--repo", required=True, help="<owner>/<repo>")

    with_build = argparse.ArgumentParser(add_help=False, parents=[with_repo])
    with_build.add_argument("--build", required=True, help="Build number.")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("from-url", parents=[common],
                        help="Parse a Drone build URL (any known host) into owner/repo/build.")
    sp.add_argument("url")
    sp.set_defaults(func=cmd_from_url)

    sp = sub.add_parser("get-build", parents=[with_build],
                        help="Get a build's status + per-stage per-step breakdown.")
    sp.set_defaults(func=cmd_get_build)

    sp = sub.add_parser("trace-failure", parents=[with_build],
                        help="Find the first failing step and show its log tail.")
    sp.add_argument("--tail-kb", type=int, default=DEFAULT_TAIL_KB,
                    help=f"KB of log tail to return (default {DEFAULT_TAIL_KB}, max {MAX_TAIL_KB}).")
    sp.add_argument("--drone-yml", action="store_true",
                    help="Also fetch .drone.yml pinned at the build's commit SHA (via `gh api`).")
    sp.set_defaults(func=cmd_trace_failure)

    sp = sub.add_parser("step-log", parents=[with_build],
                        help="Get a specific stage/step's log tail.")
    sp.add_argument("--stage", type=int, required=True, help="1-based stage number.")
    sp.add_argument("--step", type=int, required=True, help="1-based step number.")
    sp.add_argument("--tail-kb", type=int, default=DEFAULT_TAIL_KB)
    sp.set_defaults(func=cmd_step_log)

    sp = sub.add_parser("list-builds", parents=[with_repo],
                        help="List builds for a repo, newest first.")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    sp.set_defaults(func=cmd_list_builds)

    sp = sub.add_parser("latest", parents=[with_repo],
                        help="Get the latest build for a branch.")
    sp.add_argument("--branch", required=True)
    sp.set_defaults(func=cmd_latest)

    sp = sub.add_parser("find-ref", parents=[with_repo],
                        help="Find builds matching a commit SHA, branch, or PR number.")
    sp.add_argument("--sha")
    sp.add_argument("--branch")
    sp.add_argument("--pr", type=int)
    sp.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    sp.set_defaults(func=cmd_find_ref)

    sp = sub.add_parser("deploy-history", parents=[with_repo],
                        help="List promote/rollback events for a repo.")
    sp.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    sp.set_defaults(func=cmd_deploy_history)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
