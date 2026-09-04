---
name: qa01-parallel-namespace-deploy
description: >-
  Deploy a webui PR/branch to a QA01 parallel namespace (rtp-XX) and verify the
  rollout actually landed. Use when the user says "deploy this PR to rtp12",
  "deploy my branch to a parallel namespace", "部署 PR 到 rtp12", "把 branch 部署到
  rtp-X", "redeploy rtp09", "which rtp namespace is free", "who is using rtp12",
  "is my rtp deploy up", "rtp 部署好了嗎", "why did my parallel namespace build
  fail", or references the bot-deploy-pns-rtp-XX branches / the
  create-parallel-namespace-branches workflow. Covers preflight (namespace
  ownership + occupancy + branch staleness), triggering the GitHub Action, and
  verifying the real rollout in Kubernetes -- because the deploy Jenkins job
  routinely reports UNSTABLE on a rollout that actually succeeded. Mutating:
  overwrites a shared namespace another team may be using, so it requires an
  explicit AskUserQuestion gate. Does NOT cover binding tenant hostnames to the
  namespace (that is qa01-parallel-namespace-routing), ngweb-v2 PR sidecars
  (that is sidecar), or FedRAMP one_button_webui deploys.
---

# QA01 Parallel Namespace Deploy (rtp-XX)

QA01 runs one regular webui namespace (`qa01-mp-npe--webui`) plus ~20 **parallel
namespaces** (`qa01-mp-npe-rtpXX--webui`) so teams can put a feature branch on a
real tenant. A deploy is three chained systems:

```
GitHub Action  create-parallel-namespace-branches.yml   (netSkope/webui)
  └─ creates bot-deploy-pns-rtp-<NN> in netSkope/webui AND netSkope/service
       └─ Jenkins webui-stork-develop-pipeline  (npe-cisystem)      -> builds images
            └─ Jenkins one_button_webui  (cdjenkins.betaskope.iad0) -> deploys to
                 namespace qa01-mp-npe-rtp<NN>--webui
```

Getting traffic to it is a **separate** job: a tenant hostname must be bound to
the namespace on the QA01 nginx VM. That is the `qa01-parallel-namespace-routing`
skill. Deploying without binding a tenant gives you a running pod nobody reaches.

## Hard rules

- **`AskUserQuestion` is mandatory before triggering a deploy.** Every rtp
  namespace is nominally owned by some team, and deploying replaces whatever they
  have running. Show the target namespace, the current occupant (image tag + age
  from the live check below), the branch, and the Jira ticket, then confirm.
  Re-confirm even if the user already said "deploy it" earlier in the session --
  the namespace number may have changed since.

- **Never treat the GitHub Action's conclusion as the deploy result.** The
  workflow fails the run unless Jenkins returns exactly `SUCCESS`, and the deploy
  job returns `UNSTABLE` on rollouts that fully succeeded. See
  **Verify the rollout** -- Kubernetes is the only authority.

- **Distinguish the two failure stages before diagnosing.** A failure in
  `build-webui` means no image was produced and nothing was deployed (real
  blocker). A failure in `deploy-namespace` is usually `UNSTABLE` and the rollout
  is fine. Reading the wrong one inverts the conclusion.

- **Do not request a new namespace.** The source doc is explicit that parallel
  namespaces were a workaround and new ones should not be requested unless
  absolutely necessary; reuse an idle one instead.

- **Resource and replica overrides stay on feature branches.** Never merge the
  stork config / replica / CPU-memory changes to `develop`. The GitHub Action
  handles this correctly on its own; only manual setups risk it.

- **Do not bypass the gate script for the trigger.** Do not call
  `gh workflow run` directly, and do not hand-build the branches. The script
  carries the input validation, the occupant check, the staleness check, the
  concurrency guards and the audit line; going around it skips all of them.
  Read-only `gh` / `kubectl` calls for your own investigation are fine.

This skill functions on a machine with no other Claude skill installed.
`jenkins-query` and `confluence-reader` make some steps nicer and are referenced
where useful, but nothing here depends on them.

## Caveman mode

Conversational text follows the active caveman level. Any command, branch name,
namespace, image tag, job name, or URL is a technical token -- reproduce
verbatim, never abbreviate.

## Naming: four different shapes of the same number

The single most common source of copy-paste errors. For namespace number `12`:

| Thing | Value | Note |
|---|---|---|
| Workflow input | `12` | `namespace`; zero-padded internally, `8` and `08` both work |
| Git branch (both repos) | `bot-deploy-pns-rtp-12` | **hyphen** before the number |
| Kubernetes namespace | `qa01-mp-npe-rtp12--webui` | **no** hyphen; note the `--` |
| Jenkins `STACK_OVERRIDE` | `qa01-mp-npe-rtp12` | no `--webui` suffix |
| nginx `--ns-id` (routing skill) | `rtp12` | no hyphen |
| k8s Service / webui address | `webui-rtp12.qa01-mp-npe-rtp12--webui` | both forms in one string |

## Preflight

Run all three. Each has caught a real problem.

### 1. Is the namespace actually free?

The ownership table in the source doc marks essentially every namespace "Do not
use this", so it cannot tell you what is idle. The live cluster can:

```bash
python3 scripts/pns_deploy.py occupancy
```

This lists every `qa01-mp-npe-rtp*--webui` namespace with its pod status, image
tag and age. Read it as:

- `Running`, recent age -> **someone is actively using this.** Do not take it.
- `Running`, image tag many weeks old -> probably parked; still ask the owner.
- `Pending` for weeks -> a broken/abandoned deploy holding cluster reservations.
  Idle in practice, but confirm before reusing, and consider flagging it for
  cleanup.
- namespace absent entirely -> never set up, or torn down.

Then cross-check the owner in the source doc's namespace table (see **Sources**)
and confirm with that team. The doc's table and the live cluster disagree
routinely; the doc gives you a **name to ask**, the cluster gives you **reality**.

### 2. Is the branch fresh enough to build?

**This is the failure mode that looks like your code broke and is not.** The
pipeline builds *your branch*, not `develop`. Any build-system fix merged to
`develop` after your branch point is missing from your build, so the build dies
on an error in code you never touched.

```bash
python3 scripts/pns_deploy.py check-branch --branch pr/ENG-1234567/my-feature
```

Reports how far behind `develop` the branch is and flags any commit in the gap
that touches build-system paths (`compile/`, `images/`, `Dockerfile`, `Makefile`,
`.gitmodules`, `src/goldenDB/`). If it flags anything, merge `develop` into the
branch and push before deploying.

### 3. Do you have the Jenkins permissions?

Build permission is needed on both jobs, and they live on **different** Jenkins
instances (see **Sources**). Missing permission surfaces as an HTTP error from
the workflow's trigger step, not as a build failure.

## Deploy

Preferred path is always the GitHub Action -- it writes the stork config, points
the service submodule, and applies the minimal-resource/replica settings that
keep QA01 from being over-reserved. Do not hand-roll the branches.

```bash
# 1. Dry run first: validates inputs, resolves the occupant, prints the plan,
#    triggers nothing.
python3 scripts/pns_deploy.py deploy \
  --namespace 12 \
  --branch pr/ENG-1234567/my-feature \
  --jira ENG-1234567 \
  --dry-run

# 2. AskUserQuestion gate here. Then re-run without --dry-run.
```

The script wraps `gh workflow run create-parallel-namespace-branches.yml`. Input
notes:

- `jira_ticket` is **required** when `trigger_build` is on and must match
  `^[A-Z][A-Z0-9]+-[0-9]+$`. Placeholders are rejected by the deploy job.
- `trigger_build` defaults to **false** upstream, i.e. the plain workflow only
  creates branches. The script sets it true unless you pass `--branches-only`.
- `dry_run` on the *workflow* means "create branches locally, never push, skip
  Jenkins entirely" -- different from this script's `--dry-run`, which does not
  even start the workflow.
- `disable_pods_method` defaults to `scale-to-zero`. Only use `remove` on a
  brand-new namespace; on an existing one it can leave orphan pods.

Expect roughly **20 min build + 20-35 min deploy**. The workflow's Jenkins poll
gives up after ~60 min per job.

### Concurrency guards

Before triggering, the script refuses (exit 4) when either is true, and says
which:

- **A run of this workflow is already in flight**, read from GitHub rather than
  from a local file -- a local rate-limit cannot see a colleague's deploy, and
  two deploys racing the same namespace is the failure this prevents.
- **This machine already triggered the same namespace within 45 min**, i.e.
  inside one deploy's own duration, so the earlier one is probably still running.

`--force` overrides both. It needs its own confirmation from the user; do not
pass it reflexively because the first attempt was refused.

### State directory

`~/.claude/state/pns_deploy/` (created mode 0700 on first trigger):

- `deploy.log` -- audit trail, one line per triggered deploy:
  `<epoch> rtp<NN> <branch> <jira>`

Read-only subcommands and `--dry-run` never write it. GitHub already records the
authoritative actor/timestamp/inputs for each run; this local line exists for the
repeat guard and for answering "what did I trigger?" offline.

## Verify the rollout

**Do this every time, regardless of what the workflow says.**

```bash
python3 scripts/pns_deploy.py verify --namespace 12
```

Healthy means: a `webui-webui-*` pod `Running` and `1/1`, low restarts, an age
consistent with your deploy, and an image tag matching the version the build
produced (`<RELEASE>.<build>-pr-headless`).

### Why the workflow lies

Observed twice on the same namespace, from two different people's deploys: the
`one_button_webui` job finished `UNSTABLE`, the GitHub Action therefore marked
the whole run **failure**, and in both cases the pod had rolled out cleanly and
served traffic for days afterwards. `UNSTABLE` here reflects a post-deploy check,
not the rollout.

So:

| Stage | Result | What it means |
|---|---|---|
| `build-webui` | `FAILURE` | Real. No image. Nothing deployed. Go diagnose. |
| `deploy-namespace` | `UNSTABLE` | Usually benign. **Verify in k8s** before concluding anything. |
| `deploy-namespace` | `FAILURE` | Verify in k8s; may still have rolled out, but treat as suspect. |
| any | timeout | Job may still be running in Jenkins. Check Jenkins, then k8s. |

Never report "deploy failed" on a `deploy-namespace` `UNSTABLE` without having
looked at the pod. Never report success on a `build-webui` failure.

## Troubleshooting

`references/troubleshooting.md` covers, with the real error text:

- build dies on a file the PR never touched (stale branch) -- most common
- `UNSTABLE` deploy handling and how to confirm the rollout
- Jenkins credential gaps that stop you inspecting the deploy job
- namespace occupied / pods `Pending` forever
- deployed but the tenant shows the old UI (almost always missing tenant routing)

## Sources

This skill holds the stable mechanics and the failure modes worth remembering.
Volatile facts live upstream. `references/sources.md` has every link plus the
known contradictions between them.

**Go read the source docs when:**

- you need the **namespace ownership table** (who to ask) -- it changes and is
  not reproduced here on purpose
- the workflow inputs or Jenkins form fields do not match this skill
- something here contradicts what you observe -- prefer the live system, then
  the upstream doc, then this skill, and fix this skill
- you are doing a **manual** setup instead of the GitHub Action

Read the Confluence page with the `confluence-reader` skill, or fetch page id
`5864096161` (space `WUB`) directly. Note the page has been observed to lag the
actual tooling, and to contradict itself internally -- see
`references/sources.md`.

## What this skill will NOT do

- **Bind or unbind tenant hostnames.** That is nginx work on a shared VM ->
  `qa01-parallel-namespace-routing`.
- **Request or create a new rtp namespace.** Reuse an idle one; the source doc
  asks you not to add more.
- **Deploy to production, or to any stack other than `qa01-mp-npe`.**
- **Merge, rebase, or force-push your PR branch for you.** It will tell you a
  `develop` merge is required; you decide and run it.
- **ngweb-v2 PR sidecars.** Different mechanism entirely -- sidecars isolate by
  Kubernetes label and Ingress path inside one namespace and route with the
  `x-npe-env` header, with no separate namespace and no nginx hostname binding.
  Use the `sidecar` skill.
- **FedRAMP `one_button_webui`.** Same job name, different Jenkins, different
  parameters, different access path -> `fedramp-preprod-one-button-webui`.
