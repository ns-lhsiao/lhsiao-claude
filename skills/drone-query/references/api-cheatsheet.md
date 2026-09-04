# Drone REST API cheatsheet

All endpoints below are `GET` and were verified live against
`https://drone.netskope.io` (Corp VPN reachable). Base path is `/api`.

## Endpoints

| Purpose | Path |
|---|---|
| Repo metadata | `/repos/{owner}/{repo}` |
| List builds (paginated, newest first) | `/repos/{owner}/{repo}/builds?page=N&per_page=N` |
| Latest build for a branch | `/repos/{owner}/{repo}/builds/latest?branch={branch}` |
| Single build (+ stages/steps) | `/repos/{owner}/{repo}/builds/{number}` |
| Step log | `/repos/{owner}/{repo}/builds/{number}/logs/{stage}/{step}` |

`page`/`per_page` on `/builds`: default page size is 25. Pass `per_page` to
change it (verified up to at least 8; standard Drone behavior for larger
values is unconfirmed -- if you need more than ~50/page, paginate instead of
pushing `per_page` up).

## Repo object fields (subset)

```json
{
  "slug": "netSkope/service",
  "visibility": "public",
  "private": true,
  "default_branch": "develop",
  "active": true
}
```

Note `visibility` and `private` are **independent** -- see
`references/auth-visibility.md`. `visibility` is the one that determines
whether unauthenticated reads succeed.

## Build object fields (subset, from a real response)

```
id, repo_id, trigger, number, status, event, action, link, timestamp,
title, message, before, after, ref, source_repo, source, target,
author_login, author_name, author_email, author_avatar, sender,
started, finished, created, updated, version, stages
```

Key fields for lookups:
- `status`: `success` | `failure` | `running` | `skipped`
- `event`: `push` | `pull_request` (also `promote` / `rollback` for
  deploy-history, event value TBC against a promotion-using repo -- see
  design.md open questions)
- `after`: commit SHA the build ran (use for `find-ref --sha`)
- `source` / `target`: branch names (push: same branch both; PR: PR branch -> base branch)
- `ref`: `refs/heads/{branch}` for push, `refs/pull/{n}/head` for PRs (use for `find-ref --pr`)

## stages[].steps[] shape (verified, build `netSkope/service#159397`)

```json
{
  "stages": [
    {
      "name": "tenant-provisioner",
      "status": "failure",
      "steps": [
        {"name": "clone", "exit_code": 0, "status": "success"},
        {"name": "drone-consider-check", "exit_code": 0, "status": "success"},
        {"name": "build", "exit_code": 0, "status": "success"},
        {"name": "lint", "exit_code": 2, "status": "failure"},
        {"name": "unit-test", "exit_code": 0, "status": "skipped"},
        {"name": "jira update", "exit_code": 0, "status": "skipped"},
        {"name": "email-notify", "exit_code": 0, "status": "success"},
        {"name": "slack-notify", "exit_code": 0, "status": "success"}
      ]
    }
  ]
}
```

Drone's model is **flat**: one build has stages, each stage has steps, no
nested-pipeline recursion (unlike Spinnaker's `source.executionId` chains).
The failing-step trace is a single pass: first step with `status=="failure"`
or `exit_code != 0`.

Stage/step numbers used in the log-fetch path (`/logs/{stage}/{step}`) are
**1-based positions** in these arrays, not IDs.

## Step log response shape

```json
[
  {"pos": 0, "out": "latest: Pulling from qe/jslark-base\n", "time": 0},
  {"pos": 1, "out": "...\n", "time": 1}
]
```
Join every `out` field in order to reconstruct the full log text.
