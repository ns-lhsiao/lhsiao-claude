# Drone hosts at netSkope

Three hostnames exist. All were probed live; only one is the real API target.

| Host | Role | Verified behavior |
|---|---|---|
| `drone.netskope.io` | **Canonical.** All API calls target this host. | `GET /api/user` -> `401` (host answers, needs auth for that endpoint) |
| `drone-ext.netskope.io` | Deprecated alias, being retired. | `GET /api/user` -> `301` redirect to `https://drone.netskope.io/api/user` |
| `ci-drone.netskope.io` | Separate GCP/GCS-backed host, referenced in human-facing badge/status URLs. | Not an alias of the other two -- distinct backend. |

## What `from-url` does

`parse_drone_url()` in `drone_query.py` accepts a build URL on **any** of
the three hosts, in either form:

- Web form: `https://<host>/<owner>/<repo>/<build>`
- API form: `https://<host>/api/repos/<owner>/<repo>/builds/<build>`

It extracts `(owner, repo, build)` and discards the host entirely -- every
subsequent API call in this skill is hardcoded to the canonical
`drone.netskope.io`. This means a `drone-ext.netskope.io` URL pasted by a
user resolves correctly even though that host is being deprecated, and a
`ci-drone.netskope.io` URL resolves correctly even though it's a distinct
backend from the other two (its build numbers happen to be queryable via
the same canonical API in the cases checked -- if a repo turns out to be
GCS-only and not visible via `drone.netskope.io`, that's a gap to revisit).

## Why not just hardcode one host (like EP's drone-ci-debugger does)

EP's `ep-skills/drone-ci-debugger` hardcodes `drone.netskope.io` in every
curl call and has no URL normalization step -- if a user pastes a
`drone-ext` URL there, it's up to the LLM to notice and rewrite it, with no
guarantee it will. This skill closes that gap with an explicit regex-based
parse step (`from-url`, and internally reused by every other subcommand's
URL-accepting paths) so host choice never depends on the model happening to
get it right.

## Adding a host

If netSkope adds or retires a Drone host:
1. Update `KNOWN_HOSTS` in `drone_query.py`.
2. Update the table above.
3. If the new host is NOT just an alias of the canonical API (i.e. it serves
   genuinely different data, like `ci-drone` might), flag that explicitly --
   the current design assumes all three ultimately answer through the same
   `drone.netskope.io` API for any build a user would paste a URL for.
