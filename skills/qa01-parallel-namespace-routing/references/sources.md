# Sources of truth, and when to trust which

## Precedence

1. **The VM.** `sudo bash /etc/nginx/conf.d/pns_setup.sh --help`, the actual
   contents of `/etc/nginx/conf.d`, `nginx -t` output. The deployed script has
   been confirmed to be newer than the published runbook, so the VM wins.
2. **The upstream runbook / Confluence page.**
3. **This skill.**

If the VM or the docs contradict this skill, fix this skill in the same change.

## Links

### PNS routing runbook (the mechanism)

- <https://github.com/netSkope/ruslans-tools/blob/master/sslwebui_tools/parallel_namespace_setup.md>
- The script: <https://github.com/netSkope/ruslans-tools/blob/master/sslwebui_tools/pns_setup.sh>
- Deployed copy on the VM: `/etc/nginx/conf.d/pns_setup.sh`
- Jira for the mechanism: `ENG-1005017`

The runbook explains the crane / non-crane split, the generated `map` blocks, and
the append-on-existing behaviour. It does **not** document everything the
deployed script produces -- see `nginx-internals.md`.

### Confluence: the surrounding workflow

- **"Deploy WebUI Feature Branch to qa01 - aka parallel namespace deployment"**
  <https://netskope.atlassian.net/wiki/spaces/WUB/pages/5864096161/Deploy+WebUI+Feature+Branch+to+qa01+-+aka+parallel+namespace+deployment>
  - space `WUB`, page id `5864096161`
  - short link: <https://netskope.atlassian.net/wiki/x/oQGHXQE>
  - read it with the `confluence-reader` skill, or fetch page id `5864096161`
  - holds the **namespace ownership table** (who to ask before touching rtp-XX),
    the "Choosing tenants" section, and the NGINX Changes procedure
- Original Google Doc, which has the older/longer nginx narrative the Confluence
  page links out to:
  <https://docs.google.com/document/d/1hGHmXDWX29X_hol-TTj8XWy8GriUokQUh1QPhlh3WV8/edit>
- Creating a tenant to bind, if you do not have one, is covered by the
  "Creating new tenant on QA01" page linked from that Confluence page

**Consult Confluence when:** you need the ownership table, you need to create a
tenant, or you are checking whether the documented procedure has changed. Do not
consult it for the script's flags -- use the VM.

## Known contradictions (do not average these)

### Can crane / AWS-cutover tenants use a parallel namespace?

The Confluence **Prerequisites** section says **no**: tenants rerouted to AWS by
the Crane project "are not able to utilize following parallel namespaces proxies
because they are not served by ngssl nginx", with an `x-amzn-trace-id` `curl`
check to spot them:

```bash
curl -sI "https://<tenant>/" | grep -qi "x-amzn-trace-id" && echo "AWS" || echo "Not AWS"
```

The Confluence **NGINX Changes (New Process)** section says **yes**: the setup
"works for both crane cutover tenant as well as regular tenants", provided the
tenant is in `/etc/nginx/crane_tenants.map`. The ruslans-tools runbook documents
the actual mechanism for `crane_tenant=1` -- API Gateway plus
`X-Netskope-Apigw-Upstream-Webui-Target` -- and the deployed script implements it.

**The NGINX-section answer is newer and is what the current script does.** Treat
cutover tenants as supported; the real prerequisite is presence in
`crane_tenants.map`, not the absence of cutover. The `x-amzn-trace-id` check is
still useful for *knowing which path a tenant will take*, just not as a
disqualifier.

### The runbook's file list is incomplete

See `nginx-internals.md`. Consequence: tear down the whole `pns_rtpXX/`
directory, not the runbook's four named files.

## Related skills

- `qa01-parallel-namespace-deploy` -- builds and deploys the namespace this
  routing points at. A deploy without routing is unreachable; routing without a
  deploy points at nothing.
- `sidecar` -- ngweb-v2 PR sidecars. Frequently confused with this, and
  genuinely different: sidecars isolate by Kubernetes label plus a per-suffix
  Ingress path **inside one namespace** and are routed with the `x-npe-env`
  header. No separate namespace, no nginx `server_name` binding, no VM access.
- `confluence-reader` -- how to read the Confluence page above.
- `sumo-query` -- this VM appears in Sumo as `_sourceHost=*ngsslwebui*`, which is
  how to see whether a tenant's requests actually took the expected path without
  logging into the VM.
