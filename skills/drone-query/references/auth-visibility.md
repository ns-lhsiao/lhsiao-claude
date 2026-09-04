# Auth model: Drone's per-repo visibility, not a login flow

Unlike `spinnaker-query` (browser session cookie) or `jenkins-query` (API
token required up front for every call), Drone at netSkope needs **no
credential at all** for the common case. This is not a guess -- it was
verified live and matches the convention already baked into other netSkope
scripts.

## The `visibility` flag

Every Drone repo object carries two related-looking but independent fields:

```json
{"slug": "netSkope/service", "visibility": "public", "private": true}
```

- `private` mirrors the underlying **GitHub** repo's visibility (almost
  every netSkope repo is `private: true` on GitHub).
- `visibility` is **Drone's own** setting, configured per-repo in Drone's
  UI/settings, independent of GitHub. It's the one that actually gates API
  reads.

Verified live, unauthenticated:

| Repo | `visibility` | Unauth `GET /builds` |
|---|---|---|
| `netSkope/service` | public | 200 |
| `netSkope/webui2` | public | 200 |
| `netSkope/ns_ui` | (non-public) | 401 |
| `netSkope/goskope` | (non-public) | 401 |

Account-level endpoints (`/api/user`, `/api/user/repos`, `/api/repos` with
no owner/repo) always require auth regardless of any repo's visibility --
they're not repo-scoped.

## Why zero-auth is the right default, not a shortcut

Every existing netSkope script that queries the Drone API anonymously
(`ngbase-helm-chart/scripts/get_services_build_version.sh`,
`npe_updater/00_get_latest_build_number.py`,
`npe_updater/04_show_recent_builds.py`) does exactly this: plain GET, no
`Authorization` header, works because the repos they target are
public-visibility. This skill follows the same convention rather than
requiring a token for a case that doesn't need one.

## What happens on 401

`http_get_json()` in `drone_query.py` always tries unauthenticated first.
On a 401:

1. It looks for `~/.drone-token` (plain text, whitespace-trimmed).
2. If found, retries once with `Authorization: Bearer <token>` -- sent as an
   HTTP header, never appended to argv, so it never shows up in `ps`/shell
   history.
3. If that also 401s, or no token file exists, the script **fails loud**
   with the exact remediation:
   ```
   repo <owner>/<repo> is not public-visibility on Drone (401 Unauthorized).
     1) Get a personal Drone token: https://drone.netskope.io/account
     2) Save it to ~/.drone-token (a plain text file, just the token)
     3) Re-run the command -- the token is sent as a bearer header, never as an argv.
   ```

It never silently returns empty data on a 401 -- that would look
indistinguishable from "this build/repo doesn't exist."

## Open question (see design.md)

Whether a `~/.drone-token` bearer actually unlocks a non-public repo (vs.
needing the same SSO/OAuth cookie the web UI uses) was **not verified**
during design -- no token was minted. Treat the token path as
documented-but-unverified until confirmed against a real private repo.

## Token file hygiene

`~/.drone-token` is a long-lived personal credential, not a session cookie
like Spinnaker's. Still, treat it like any bearer token:
- `chmod 600 ~/.drone-token`.
- Don't commit it, don't paste it into chat, don't put it in `DRONE_TOKEN`
  in a shell profile that gets sourced into logs.
