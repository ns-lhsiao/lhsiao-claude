# Reaching the QA01 nginx VM over teleport

## The command

```bash
tsh ssh --cluster iad0 ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net
```

Non-interactively (what the scripts use):

```bash
tsh ssh --cluster iad0 ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net -- '<command>'
```

Login, if the profile is expired:

```bash
tsh login --proxy=teleport.netskope.io
tsh status     # confirm a qa01-mp-npe role is present and the cert is valid
```

## Why discovery does not work here

Do not try to find this host by listing nodes. On this cluster:

- `tsh ls` returns hundreds of `kaas-node-<uuid>` entries -- Kubernetes nodes --
  and no `ngsslwebui` anywhere in the list
- `tsh ls --search=ngsslwebui`, `--search=sslwebui`, `--search=qa01-mp-npe` all
  return an empty table plus the generic "Not seeing nodes? ... your user's roles
  do not match the labels of at least one node" hint, which reads like a
  permissions problem and is not one
- `tsh ls --cluster=qa01-mp-npe` fails outright with an authentication handshake
  error -- `qa01-mp-npe` is a *role* name, not the teleport cluster to use
- `tsh ssh` **without** `--cluster iad0` fails with "target host
  ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net is offline or does not exist"

The hostname and `--cluster iad0` must both be supplied explicitly. The leaf
cluster is the **POP** (`iad0`), not the stack.

An expired or missing profile also surfaces as "offline or does not exist" rather
than as an auth error, so re-check `tsh status` before concluding the host is
gone.

## Pattern for other POPs

The same VM role exists across POPs, with the teleport leaf cluster being the POP
name. Observed shapes:

```
ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net       --cluster iad0    (QA01 NPE)
ngsslwebui01.<stack>-mp-prod.nc1.<pop>.nsscloud.net  --cluster <pop>   (most prod POPs)
ngsslwebui05.<pop>.nskope.net                        --cluster <pop>   (older naming)
ngsslwebui03.mgt.<pop>.nskope.net                    --cluster <pop>   (some POPs)
```

Numbering varies per POP -- prod POPs commonly have several
(`ngsslwebui01`..`03`, sometimes `05`/`06`). Since `--search` does not work, the
only reliable enumeration is:

```bash
tsh ls --cluster <pop> -f names | grep ngsslwebui
```

which does list them once the correct leaf cluster is named.

**This skill is scoped to qa01/iad0 only.** The prod patterns are recorded so you
recognise them and so nobody adapts a qa01 command to a prod host by editing one
word. Prod nginx changes are not in scope here.

## Privileges on the VM

- The generated PNS configs are `0600 root`, so reads need `sudo`
- `sudo` is available for `nginx -t`, `supervisorctl`, and reading/editing the
  configs
- The directory `/etc/nginx/conf.d` itself is owned by `nsadmin`

## Sanity check

```bash
tsh ssh --cluster iad0 ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net -- \
  'hostname; ls -la /etc/nginx/conf.d/ | grep -i pns'
```

`hostname` returns the short form (`ngsslwebui01`), which confirms you are on the
VM and not on a jump host.
