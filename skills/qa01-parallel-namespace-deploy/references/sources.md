# Sources of truth, and when to trust which

This skill deliberately does **not** copy the volatile parts of the upstream
docs. Ownership tables, Jenkins form screenshots and workflow input lists drift;
a stale copy inside a skill is worse than a link, because nothing errors when it
goes wrong.

## Precedence

When two sources disagree, prefer in this order:

1. **The live system.** The cluster, the running script's `--help`, the
   workflow's own YAML. This is the only thing that cannot be out of date.
2. **The upstream doc** (Confluence / the ruslans-tools runbook).
3. **This skill.**

If you find (1) or (2) contradicting this skill, fix this skill in the same
change. Do not leave the discrepancy for someone else.

## Links

### Primary runbook

- **Confluence: "Deploy WebUI Feature Branch to qa01 - aka parallel namespace deployment"**
  <https://netskope.atlassian.net/wiki/spaces/WUB/pages/5864096161/Deploy+WebUI+Feature+Branch+to+qa01+-+aka+parallel+namespace+deployment>
  - space `WUB`, page id `5864096161`
  - short link: <https://netskope.atlassian.net/wiki/x/oQGHXQE>
  - read it with the `confluence-reader` skill, or fetch page id `5864096161`
  - **this is where the namespace ownership table lives** -- the authoritative
    answer to "who do I ask before taking rtp-XX"
- Original Google Doc the page was migrated from (has some sections the
  Confluence copy summarises, notably the older nginx narrative):
  <https://docs.google.com/document/d/1hGHmXDWX29X_hol-TTj8XWy8GriUokQUh1QPhlh3WV8/edit>

### Automation

- GitHub Action (the supported path):
  <https://github.com/netSkope/webui/actions/workflows/create-parallel-namespace-branches.yml>
  - source of truth for the input list -- read
    `.github/workflows/create-parallel-namespace-branches.yml` and
    `.github/scripts/create_parallel_namespace_branches.py` on `develop`
- Image build job (`webui-stork-develop-pipeline`), **npe-cisystem**:
  <https://npe-cisystem.netskope.io/job/webui-stork-develop-pipeline/>
- Deploy job (`one_button_webui`), **cdjenkins.betaskope.iad0**:
  <https://cdjenkins.betaskope.iad0.netskope.com/job/one_button_webui/>
- Helper bookmarklets and a Chrome extension for filling the Jenkins form by
  hand are in the Confluence page and
  <https://github.com/netSkope/script-utils/tree/main/jenkins-webui-helper>
  (only needed for manual deploys; the GitHub Action supersedes them)

### nginx / tenant routing side

Covered by the `qa01-parallel-namespace-routing` skill, but listed here because
a deploy is not testable without it:

- PNS routing runbook:
  <https://github.com/netSkope/ruslans-tools/blob/master/sslwebui_tools/parallel_namespace_setup.md>
- The script itself:
  <https://github.com/netSkope/ruslans-tools/blob/master/sslwebui_tools/pns_setup.sh>
- Jira for that mechanism: `ENG-1005017`

### Related tickets / threads

- `CD-52095` -- sample ticket for adding a namespace to the CD deployment
  pipeline (only if a genuinely new namespace is unavoidable)
- The Confluence page links Slack threads on namespace hygiene and on the
  requirement to use the GitHub Action rather than hand-made branches

## Known contradictions (do not average these)

### 1. Can crane / AWS-cutover tenants use a parallel namespace?

The Confluence **Prerequisites** section says no: tenants rerouted to AWS by the
Crane project "are not able to utilize following parallel namespaces proxies
because they are not served by ngssl nginx", and gives an `x-amzn-trace-id`
`curl` check to identify them.

The Confluence **NGINX Changes (New Process)** section, and the ruslans-tools
runbook, say yes: the setup "works for both crane cutover tenant as well as
regular tenants", provided the tenant is listed in `/etc/nginx/crane_tenants.map`.
The runbook documents the mechanism -- for `crane_tenant=1` the request goes
through API Gateway and an `X-Netskope-Apigw-Upstream-Webui-Target` header
selects the namespace.

**The NGINX-section answer is the newer one and is the mechanism actually
implemented in the current script.** The Prerequisites warning predates it.
Treat cutover tenants as supported, but verify the tenant is in
`crane_tenants.map`.

### 2. The runbook lags the deployed script

The runbook lists four generated files. The copy of `pns_setup.sh` deployed on
the QA01 nginx VM generates more than that (auth/pinger and webui2 header files,
a `webui_auth_proxy_<ns>.conf`) and supports capabilities the runbook does not
mention, such as nginx regex patterns in `--tenants`.

**Always read `--help` from the copy on the VM** rather than trusting the
runbook's flag list. The routing skill documents this.

### 3. Which Jenkins builds the images

The Confluence page names both `gke-cisystem.netskope.io` and
`npe-cisystem.netskope.io` for `webui-stork-develop-pipeline`. The GitHub Action
uses **npe-cisystem**; that is what to inspect.

## Inspecting the Jenkins jobs

The `jenkins-query` skill is the read-only way in, but note its credential file
(`~/.claude/connections/jenkins.json`) commonly only has an `npe` server
configured. The **deploy** job lives on `cdjenkins.betaskope.iad0`, so add it as
a second server before trying to inspect a deploy build:

```json
{
  "default": "npe",
  "servers": {
    "npe":      {"url": "https://npe-cisystem.netskope.io",             "user": "you@netskope.com", "api_token": "..."},
    "cdjenkins":{"url": "https://cdjenkins.betaskope.iad0.netskope.com","user": "you@netskope.com", "api_token": "..."}
  }
}
```

Without it, `jenkins-query` returns `404` for deploy builds because it silently
queries the wrong host. Verifying the rollout in Kubernetes does not need any
Jenkins credential at all, which is another reason to make k8s the authority.
