---
name: drone-query
description: Read-only Drone CI inspection -- parse a Drone build URL, trace a failed build to the exact failing step and its error log, list build history, find which build ran a given commit/branch/PR, and list deploy/promote history. Use whenever the user pastes a drone.netskope.io / drone-ext.netskope.io / ci-drone.netskope.io build URL, asks "why did drone build X fail", "what's the error in this build", "list drone builds for X", "is my commit/PR in a drone build", "did X's last build pass", or "drone deploy history for X". Public-visibility repos need zero credentials -- do NOT call the Drone REST API directly with curl or WebFetch, always go through `scripts/drone_query.py`.
---

# drone-query

Personal read-only Drone CI skill. Wraps the Drone REST API behind a single
Python gate script that handles host normalization, the public/private
visibility model, log truncation (64 KB tail / 256 KB cap), and PII scrubbing.

## Why a gate script (read this first)

1. **Read-only.** No subcommand starts, restarts, promotes, cancels, rolls
   back, or deletes a build. Write tools are deliberately not implemented.
   If a write becomes necessary, add it as a separate skill with an approval
   gate -- do not extend this one.
2. **Netskope Drone repos are public-by-default for the ones you'll query
   most.** Drone has its own per-repo `visibility` flag independent of the
   underlying GitHub repo's visibility. Verified live: `netSkope/service` and
   `netSkope/webui2` serve builds/stages/logs with **zero authentication**.
   This matches the convention already used by other netSkope scripts
   (`ngbase-helm-chart/scripts/*`). Only non-public repos need a token --
   see `references/auth-visibility.md`.
3. **Three hosts, one canonical API.** `drone-ext.netskope.io` is a
   deprecated alias that 301-redirects to `drone.netskope.io`; `ci-drone.netskope.io`
   is a separate GCP-backed host. `from-url` accepts a build URL on any of
   the three and normalizes to the canonical `drone.netskope.io` API --
   see `references/hosts.md`.

Never bypass the gate. Do not `curl https://drone*.netskope.io/api/...`
directly, do not `WebFetch` a Drone URL, do not write a one-off `requests`
script. If the gate script refuses something (401 with no token, 404), surface
the refusal and fix it via the instructions it prints -- do not work around it.

## Triggering

Use this skill when the user wants Drone CI data. Typical phrasings:

- "why did drone build 159397 fail?" / "what's the error in this build?"
- The user pastes a URL like `https://drone-ext.netskope.io/netSkope/service/159397`
  (or the `drone.netskope.io` / `ci-drone.netskope.io` equivalent)
- "list drone builds for netSkope/service"
- "did develop's last build pass?"
- "is my PR #107323 / commit &lt;sha&gt; / branch X in a drone build"
- "drone deploy history for &lt;repo&gt;" / "when did X last promote?"

Do NOT use for: GitHub Actions, Jenkins (use `jenkins-query`), Spinnaker
deploys (use `spinnaker-query`) -- this is Drone CI only.

## Where the script lives

Resolve the script path **once at the start** of the session, then reuse `$SCRIPT`:

```bash
SCRIPT=$(ls \
  ~/.claude/skills/drone-query/scripts/drone_query.py \
  .claude/skills/drone-query/scripts/drone_query.py \
  2>/dev/null | head -1)
[ -z "$SCRIPT" ] && { echo "drone-query skill not installed"; exit 1; }
```

Do not use bare `scripts/drone_query.py` (relative paths break unless cwd is
the skill dir).

## No setup needed for public repos

Unlike `spinnaker-query` (browser-cookie auth) or `jenkins-query` (API token
required up front), this skill needs **no credential** for the common case.
Just run a command:

```bash
python3 "$SCRIPT" get-build --repo netSkope/service --build 159397
```

If a repo turns out to be non-public-visibility, the script fails loud with
exactly what to do -- get a token at `https://drone.netskope.io/account`,
save it to `~/.drone-token`, re-run. See `references/auth-visibility.md`.

## Workflow

### Fast path: user pasted a Drone build URL

```bash
python3 "$SCRIPT" from-url 'https://drone-ext.netskope.io/netSkope/service/159397'
```
Prints `owner`, `repo`, `build` (works for any of the three hosts, web or API
URL form). Then:

```bash
python3 "$SCRIPT" trace-failure --repo netSkope/service --build 159397
```
This is the fast path for "what's the error" -- it fetches the build, walks
`stages[].steps[]` for the first step with `status=failure` / non-zero
`exit_code`, and auto-tails that step's log (bounded + scrubbed). Add
`--drone-yml` to also fetch `.drone.yml` pinned at the build's commit SHA
(via `gh api`, best-effort -- degrades gracefully if `gh` isn't authed).

Need the full stage/step breakdown without the log?

```bash
python3 "$SCRIPT" get-build --repo netSkope/service --build 159397
```

Need one specific step's log (not the auto-detected failing one)?

```bash
python3 "$SCRIPT" step-log --repo netSkope/service --build 159397 --stage 1 --step 4
```
Stage/step numbers are 1-based, matching the order in `get-build`'s output.

### Build history

```bash
python3 "$SCRIPT" list-builds --repo netSkope/service --page 1
python3 "$SCRIPT" latest --repo netSkope/service --branch develop
```
`list-builds` returns 25 per page (`--per-page` to change), newest first.
`latest` gives the most recent build for a branch -- fast path for "did
develop's last build pass".

### Is my commit / branch / PR in a build

```bash
python3 "$SCRIPT" find-ref --repo netSkope/service --sha <commit-sha>
python3 "$SCRIPT" find-ref --repo netSkope/service --pr 107323
python3 "$SCRIPT" find-ref --repo netSkope/service --branch my-feature-branch
```
Scans build history newest-first, matching `--sha` against `after`, `--branch`
against `source`/`target`, `--pr` against `ref` (`refs/pull/<n>/head`). Default
scan depth is 10 pages (`--max-pages` to widen); if the cap is hit with no
match, the output says so explicitly rather than implying the ref was never built.

### Deploy / promote history

```bash
python3 "$SCRIPT" deploy-history --repo netSkope/service
```
Scans build history for `event` in `promote`/`rollback`. Same `--max-pages`
cap and "cap reached" reporting as `find-ref`. **Note:** those exact event
names are the best guess from Drone's general model, not yet confirmed
against a netSkope repo that actually uses Drone promotions -- a "0 deploy
events found" result could mean the event name is different, not that there
were no deploys. Confirm against a real promoting repo before trusting a
zero result.

## Reference files

- **`references/api-cheatsheet.md`** -- endpoint-by-endpoint reference
  (repo, builds list, latest-by-branch, single build, step logs), the full
  build-object field map, and the verified `stages[].steps[]` shape from a
  real failing build.
- **`references/auth-visibility.md`** -- the Drone `visibility` model, why
  public repos need no token, the `~/.drone-token` fallback, and what a 401
  actually means.
- **`references/hosts.md`** -- the three known Drone hosts, which is
  canonical, and how `from-url` normalizes between them.

## Things to not do

- Do not call `https://drone*.netskope.io/api/...` directly with
  curl/WebFetch/requests -- always go through the script.
- Do not implement `promote`, `restart`, `cancel`, `delete`, or any write
  operation in this skill.
- Do not assume every repo needs a token -- try without one first; the
  script already does this automatically.
- Do not leave a `~/.drone-token` file world-readable; `chmod 600` it.
- Do not treat a `find-ref`/`deploy-history` "no match" as definitive without
  checking whether the scan hit its page cap -- the output tells you if it did.
