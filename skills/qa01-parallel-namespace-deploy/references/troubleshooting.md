# Troubleshooting a parallel namespace deploy

Ordered by how often each one actually happens.

## 1. Build fails on a file your PR never touched

**Symptom.** `build-webui` fails. The error names a path unrelated to your
change. Real example:

```
cp: cannot stat '/src_tree/3p/edk/bin/grammar_reference.json': No such file or directory
#65 ERROR: executor failed running [/bin/sh -c bash -c '/usr/local/bin/nswebui_install.sh']: exit code: 123
[FAIL] docker build failed.
make: *** [.../stork-build.mk:77: component-images] Error 1
```

Pipeline stages showed `Build goldendb` and `webui` FAILURE, `Push Images to
Artifactory` skipped.

**Cause.** The pipeline builds **your branch**, not `develop`. A build-system fix
that landed on `develop` after your branch point is absent from your build. In the
example the branch was 6 commits behind and the gap contained
`EP-99143: Update grammar_reference.json path from 3p/edk/ to edk/` plus a
goldenDB Dockerfile fix -- merged to `develop` hours earlier the same day.

**Diagnosis.**

```bash
python3 scripts/pns_deploy.py check-branch --branch pr/ENG-1234567/my-feature
```

or by hand:

```bash
gh api repos/netSkope/webui/compare/develop...<branch> \
  --jq '{ahead_by, behind_by, status}'
gh api repos/netSkope/webui/compare/<branch>...develop \
  --jq '.commits[] | {sha: .sha[0:8], msg: (.commit.message | split("\n")[0])}'
```

Scan the gap for anything touching `compile/`, `images/`, `Dockerfile`,
`Makefile`, `.gitmodules`, `src/goldenDB/`. A hit there explains an
"unrelated" build error.

**Fix.** Merge `develop` into the branch and push, then re-trigger. A merge
commit on a PR branch is visible to reviewers, so confirm with the user first.
Doing this in a throwaway worktree avoids disturbing a dirty main checkout:

```bash
cd <webui clone>
git fetch origin <branch> develop
WT=$(mktemp -d)
git worktree add -b tmp-merge-develop "$WT" origin/<branch>
cd "$WT" && git merge origin/develop --no-edit
git push origin HEAD:refs/heads/<branch>
cd - && git worktree remove "$WT" && git branch -D tmp-merge-develop
```

**Generalise.** Whenever a parallel-namespace build fails on code the PR did not
touch, check branch staleness *before* reading the stack trace.

## 2. Deploy reports UNSTABLE (or the workflow says failure) but it worked

**Symptom.** `deploy-namespace / trigger-jenkins` fails with:

```
Jenkins build failed with result: UNSTABLE
JENKINS_RESULT: UNSTABLE
```

and the whole GitHub Action run is marked failure, because the workflow only
accepts `SUCCESS`.

**Reality.** Observed twice on the same namespace from two different people's
deploys: `UNSTABLE`, workflow failure, and the pod had rolled out cleanly --
one of them then served traffic for 10 days. `UNSTABLE` reflects a post-deploy
check, not the rollout.

**What to do.** Check Kubernetes and let it decide:

```bash
python3 scripts/pns_deploy.py verify --namespace 12
```

A `Running` `1/1` pod with an age matching your deploy and the expected
`-pr-headless` image tag means the deploy landed. Report that, and mention the
`UNSTABLE` as a known quirk rather than as a failure.

**Do not** re-trigger the whole deploy just because the workflow is red. You will
redo 40 minutes of work on something that already succeeded.

## 3. Cannot inspect the deploy build

**Symptom.** `jenkins-query` returns `404 Not Found` for the `one_button_webui`
build, with a URL pointing at `npe-cisystem.netskope.io`.

**Cause.** The deploy job is on `cdjenkins.betaskope.iad0.netskope.com`, but only
an `npe` server is configured in `~/.claude/connections/jenkins.json`, so the
query silently went to the wrong host.

**Fix.** Add a `cdjenkins` server -- see `references/sources.md`. Or skip Jenkins:
the Kubernetes check answers the only question that matters.

## 4. Namespace is occupied, or pods are Pending forever

**Symptom.** `occupancy` shows pods `Pending` for weeks, sometimes several
ReplicaSets' worth, occasionally with an image that is not webui at all.

**Meaning.** An abandoned deploy still holding cluster reservations. This is
exactly the over-reservation the source doc warns about. In practice the
namespace is idle, but:

- confirm with the owner from the source doc's table before reusing it
- prefer a namespace whose pods are absent or cleanly stopped
- if you reuse it, `disable_pods_method=scale-to-zero` (the default) is correct;
  `remove` on a namespace with existing pods can orphan them

Multiple `Pending` ReplicaSets for one namespace usually means repeated failed
deploys, not one bad rollout.

## 5. Deployed successfully but the tenant shows the old UI

Almost always **missing or wrong tenant routing**, not a deploy problem. The pod
is up; nothing points a hostname at it.

Check with the `qa01-parallel-namespace-routing` skill: the tenant hostname must
appear in the `server_name` of `/etc/nginx/conf.d/webui_proxy_rtp<NN>.nginx.conf`
on the QA01 nginx VM, and nginx must have been reloaded since.

Also check you are looking at the right namespace -- `bot-deploy-pns-rtp-12`
(branch) versus `qa01-mp-npe-rtp12--webui` (namespace) is an easy mix-up.

## 6. Workflow rejects the Jira ticket

```
::error::jira_ticket is required when trigger_build is enabled.
::error::Invalid jira_ticket: '<x>'. Expected a Jira key like ENG-1234567, NPLAN-1234, OPS-12345.
```

Must match `^[A-Z][A-Z0-9]+-[0-9]+$`. The deploy job rejects placeholder strings,
so bot-style values like `bot-deploy-pns-12` fail validation by design.

## 7. Poll timeout

The workflow polls Jenkins ~360 times at 10s intervals, so it gives up after
roughly an hour per job. A timeout does **not** cancel the Jenkins build. Check
the job directly, then Kubernetes.
