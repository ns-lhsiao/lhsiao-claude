# What pns_setup.sh actually generates, and how routing works

## Mechanism

Two paths, selected per request by `$crane_tenant`:

| Tenant state | `proxy_pass` | `host` header | Result |
|---|---|---|---|
| `crane_tenant=0` (not cut over) | `http://webui` (KLBI) | `webui-rtpXX` | KLBI host routing lands in the rtpXX namespace |
| `crane_tenant=1` (cut over to AWS) | `$apigw_proxy_pass` | `$api_gw_host_header` | API Gateway honours `X-Netskope-Apigw-Upstream-Webui-Target` |

For non-cutover tenants the whole trick is the `host` header: setting
`host: webui-rtpXX` instead of `host: webui` is enough for KLBI to pick the
parallel namespace, so no new upstream definitions are needed. The lbaas map
(`$webui_pass`) is deliberately bypassed and the upstream hardcoded to
`http://webui`, so the host header is always what decides.

For cutover tenants the request goes through API Gateway, and
`X-Netskope-Apigw-Upstream-Webui-Target` overrides the default upstream. **The
tenant must already be in `/etc/nginx/crane_tenants.map`** -- that file is what
sets `$crane_tenant=1`. Without it the cutover tenant takes the non-cutover path
and does not reach the namespace.

Nothing pre-existing is modified. All generated files are new, per-`ns-id` files,
which is what makes this survive deployment cycles.

## Generated files

Per `--ns-id rtpXX`, under `/etc/nginx/conf.d`:

```
webui_proxy_rtpXX.nginx.conf        <- the server{} block; server_name lives HERE
pns_rtpXX/
  crane_mp_webui_headers_rtpXX
  crane_authn_headers_rtpXX
  webui_auth_proxy_rtpXX.conf
  webui_route_mappings_rtpXX.conf
  crane_mp_webui_apiv1_headers_rtpXX     [only with --apiv1-address]
```

`webui_proxy_rtpXX.nginx.conf` is a copy of the rendered
`webui_proxy.nginx.conf` server block with:

- `default_server` stripped from `listen`
- `server_name` replaced by your tenant list
- header/routing includes swapped to the `_rtpXX` variants
- per-namespace `map` blocks prepended, defining `$pns_rtpXX_*` variables

The `map` blocks define, for `$crane_tenant`:

```nginx
map $crane_tenant $pns_rtpXX_mp_webui_pass {
    1       $apigw_proxy_pass;
    0       "http://webui";
    default "http://webui";
}
map $crane_tenant $pns_rtpXX_webui_host_header {
    1       $api_gw_host_header;
    0       "webui-rtpXX";
    default "webui-rtpXX";
}
```

plus the `_apiv1_` equivalents when `--apiv1-address` was given. The `$pns_<ns>_*`
names cannot collide with anything in the main config.

## The deployed script is newer than the published runbook

Confirmed on the QA01 VM: `--help` documents `crane_authn_headers_<ns>` and
`webui_auth_proxy_<ns>.conf` outputs, and support for **nginx regex patterns** in
`--tenants` (e.g. `--tenants '~(a|b)\.example\.com$'`, quoted so the shell does
not expand it). Neither appears in the published runbook, and a live `pns_rtp12/`
directory additionally contained `crane_ms_bootstrap_headers_rtp12` and
`crane_webui2_headers_rtp12`.

Consequences:

1. Read `sudo bash /etc/nginx/conf.d/pns_setup.sh --help` on the VM for the
   authoritative flag list and output list.
2. When tearing down, remove the whole `pns_rtpXX/` directory rather than the
   individually named files from the runbook, or you will leave orphans.

## Flags (from the VM copy)

```
--ns-id           required   short id, suffixes every generated filename
--webui-address   required   k8s service FQDN; host header derived from the part
                             before the first '.'
--tenants         required   one or more hostnames, space separated; nginx regex
                             patterns allowed
--apiv1-address   optional   enables /api/v1/* routing override
--source          optional   default /etc/nginx/conf.d/webui_proxy.nginx.conf
--out-dir         optional   default /etc/nginx/conf.d
-h | --help
```

**There is no removal flag.** Behaviour when a config for the `ns-id` already
exists is to merge the new tenants into the existing `server_name` and stop --
it does not regenerate the other files, and it cannot subtract. First-time
generation refuses to overwrite any existing output file.

## Why removal is a hand edit

Given no remove flag, taking one tenant off a namespace means rewriting the
`server_name` line in `webui_proxy_rtpXX.nginx.conf`. Constraints:

- the file is `0600 root`
- it is live; the next reload by anyone picks up whatever is in it
- an empty `server_name` is not a valid "disabled" state -- if no tenants remain,
  tear the namespace config down instead
- the line's leading whitespace should be preserved (the generator writes
  `server_name` followed by alignment spaces)

So: back up, edit, `nginx -t -c /etc/nginx/nginx-sslwebui.conf`, confirm, reload.
The backup is the rollback. Never leave the VM with a config that fails
validation -- the failure is inherited by the next person's reload.

## Validation and reload

```bash
sudo nginx -t -c /etc/nginx/nginx-sslwebui.conf
sudo supervisorctl signal HUP nginx
```

`-c` is required: the sslwebui instance does not use nginx's default config path,
so a bare `nginx -t` validates a different file and passing it proves nothing.

Two warnings are pre-existing on this VM and appear on a clean config:

```
nginx: [warn] could not build optimal map_hash, you should increase either map_hash_max_size: 2048 or map_hash_bucket_size: 128; ignoring map_hash_bucket_size
nginx: [warn] could not build optimal variables_hash, you should increase either variables_hash_max_size: 1024 or variables_hash_bucket_size: 64; ignoring variables_hash_bucket_size
```

Success looks like `syntax is ok` + `test is successful`. A reload prints
`nginx: signalled`.

## Reading the current binding

```bash
sudo grep -nE "^[[:space:]]*server_name[[:space:]]" \
  /etc/nginx/conf.d/webui_proxy_rtpXX.nginx.conf
```

Anchor the pattern. An unanchored `grep server_name` also matches
`proxy_ssl_server_name on;`, which occurs several times further down the same
file; on a real rtp12 config that produced three hits where only the first was
the tenant list.
