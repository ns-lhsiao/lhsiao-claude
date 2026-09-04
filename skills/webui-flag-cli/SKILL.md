---
name: webui-flag-cli
description: Read or write WebUI feature/control flags for any team's tenants using the `@netskope/flag` CLI (`npm install -g @netskope/flag` / `npx @netskope/flag`). Team-scoped -- covers all WebUI teams via a shared team registry (airt, cci, npa, rbac, spm, ueba, etc.), with tenant shortcuts (npe/nonprod, prod, dc name, full tenant name, or raw tenant ID), write-by-alias, control-flag writes, JSON output, dry-run, and built-in production-write warnings. Use whenever the user asks to "read flags for team X", "check flag Y on tenant Z", "enable/disable <alias> for <tenant>", "list webui teams/flags", or references the `flag` / `@netskope/flag` CLI. Do NOT use for qa01/devint/stg01 provisioner-pycore or direct-MariaDB tenant flag toggling (that is `webui-ff-toggle`), and do NOT use for creating/retiring flags across the webui/service/ursa codebases (that is `feature-flag-manager` / `control-flag-manager`).
---

# webui-flag-cli

Team-scoped WebUI flag reader/writer. Wraps the `@netskope/flag` CLI
(`netSkope/script-utils` -> `flag-cli`), which resolves a team key to its
configured tenants and flags, then reads/writes via `kubectl exec` under the
hood. No Python setup beyond a valid kubeconfig.

## Why this skill exists (read this first)

This is a **thin front door** to an existing, externally maintained CLI --
`@netskope/flag`. The skill's job is to know which command to run for a
given request, surface the CLI's own safety warnings, and enforce the write
confirmation flow. It does not reimplement flag storage/lookup logic; that
lives in the `flag-cli` package (see
`references/flag-cli-source.md` for where to look if the CLI itself needs a
fix).

This is a different tool from `webui-ff-toggle`:

| | `webui-flag-cli` (this skill) | `webui-ff-toggle` |
|---|---|---|
| Mechanism | `@netskope/flag` CLI -> `kubectl exec` + curl inside the pod | provisioner-pycore POST, or direct MariaDB `--via=db` |
| Scope | Any WebUI team's configured tenants (npe + prod) | qa01 / devint / stg01 only |
| Selection | team key (`airt`, `cci`, ...) + tenant shortcut | explicit `--env` + tenant id |
| Safety model | CLI-native prod warnings + read-back verify prompt | rate limits, lock file, audit log, triple identity guard |

If the user's request names a team (`airt`, `cci`, `spm`, ...) or says
"flag CLI" / "`@netskope/flag`" / "`npx flag`", use this skill. If it names
`qa01`/`devint`/`stg01` explicitly with a raw tenant id and no team, or
mentions provisioner-pycore / `--via=db`, prefer `webui-ff-toggle` instead.

## Triggering

- "read all airt flags on npe"
- "check nplan7230_airt_dlp_addon for qa01"
- "enable dlp for airt-qa01" / "disable nplan6196_airt_enabled on tenant 9459"
- "list webui teams" / "show cci flags"
- "write control flag NPLAN6196_AIRT_ENABLED 1 for airt-qa01"
- The user pastes or names a team key from the Supported Teams table below

Do NOT use for: qa01/devint/stg01 provisioner-pycore or direct-DB tenant
flag toggling (`webui-ff-toggle`); creating, renaming, or retiring flags in
the webui/service/ursa codebases (`feature-flag-manager`,
`control-flag-manager`); LaunchDarkly flags (`launchDarkly-flag-manager`).

## Setup

Install globally (Node 18+):

```bash
npm install -g @netskope/flag
```

Or run without installing:

```bash
npx @netskope/flag airt npe
```

If the `@netskope` registry isn't configured yet, add it first:

```bash
echo "@netskope:registry=https://artifactory-rd.netskope.io/artifactory/api/npm/npm-dev/" >> ~/.npmrc
```

Check availability before choosing global vs `npx`:

```bash
command -v flag || echo "not installed globally -- use npx @netskope/flag"
```

## Command shape

```
flag <team> <tenant> [flag_or_alias] [value]
```

- `<team>` -- team key, e.g. `airt`, `cci`. Run `flag list` for the current
  authoritative set (the table below can drift; treat `flag list` as
  ground truth).
- `<tenant>` -- tenant shortcut. `npe` / `nonprod` = all non-prod, `prod` =
  all prod, a DC name (`qa01`), a full tenant name (`airt-qa01`), or a raw
  tenant ID (`9459`).
- `[flag_or_alias]` -- omit to read all flags for the team; give a specific
  flag name or team-defined alias to target one.
- `[value]` -- `1` to enable, `0` to disable. Omit to read.

## Workflow

### Reads

Run directly, no confirmation needed:

```bash
flag airt npe                              # all AIRT flags, all non-prod
flag airt qa01                             # all AIRT flags, one dc
flag airt qa01 nplan7230_airt_dlp_addon    # one flag
flag airt 9459                             # by raw tenant id
flag airt qa01 --json                      # machine-readable
flag airt npe --dry-run                    # preview commands, no kubectl needed
flag list                                  # all teams
flag list cci                              # one team's flags + aliases
```

Interactive/multi-tenant browsing:

```bash
flag airt
```

### Writes

```bash
flag airt qa01 dlp 1                              # enable by alias
flag airt qa01 nplan7230_airt_dlp_addon 0          # disable by full name
flag airt 9459 dlp 1                               # by raw tenant id
```

Before running a write:

1. **Resolve the team key.** If unclear or not recognized, run `flag list`
   and ask the user to confirm which team.
2. **Check whether the target is production.** If the tenant/cluster
   resolves to a prod cluster, stop and confirm with the user that there is
   an approved, active CM ticket before proceeding. The CLI itself prints a
   `WARNING -- CM ticket required` banner on any prod write; treat that as
   a hard stop, not a formality, until the user confirms.
3. **Read current value first**, show it to the user.
4. **Run the write.** The CLI prompts `Read back flags to verify? (Y/n)`
   after every write (default yes) -- accept the default so the change is
   verified automatically. Do not suppress or auto-skip this prompt.

### Control flag writes

Uppercase flag names are automatically treated as control flags (the CLI
shells out to `php /opt/ns/bin/ws_scripts/controlFlags.php` for these):

```bash
flag airt airt-qa01 NPLAN6196_AIRT_ENABLED 1
flag airt airt-qa01 NPLAN6196_AIRT_ENABLED 0
flag airt airt-qa01 airt_cf 1   # by team-defined alias
```

### Production safety (CLI-native)

| Operation | Trigger | CLI behavior |
|---|---|---|
| Write (any prod) | Any write to a prod cluster | Prints `WARNING` -- treat as: confirm CM ticket is approved and active before proceeding |
| Mass read (>2 prod clusters) | e.g. `flag airt prod` | Prints `NOTE` -- confirm with user whether their team requires a CM ticket for this read |

Single or dual prod cluster reads (e.g. `flag airt sjc1`) print no warning
-- treat those as routine.

### Fallback -- feature_flag.py / control_flag.py

If the CLI/npm path isn't available and the user wants to proceed anyway,
the same `script-utils` repo ships direct-provisioner Python scripts under
`flags/`:

```bash
python feature_flag.py <flag> [flag2 ...] --tenant <id> -c <cluster>
python feature_flag.py --set flag_a=1 --tenant <id> -c <cluster>
./control_flag.py NPLAN6196_AIRT_ENABLED read
./control_flag.py NPLAN6196_AIRT_ENABLED enable -c qa01
```

Ask the user for the cluster/tenant details these scripts need (they take
raw cluster names, not team keys). See
`references/flag-cli-source.md` for the repo location.

## Supported teams (snapshot -- confirm with `flag list`)

| Key | Label |
|---|---|
| `advanced_analytics_reports` | WebUI-Advanced Analytics / Reports |
| `airt` | WebUI-AIRT (AI Red Teaming) |
| `cci` | WebUI-CCI |
| `client` | WebUI-Client |
| `cloud_firewall` | WebUI-Cloud Firewall |
| `dem` | WebUI-DEM |
| `endpoint_dlp` | WebUI-Endpoint DLP |
| `enterprise_browser` | WebUI-Enterprise Browser |
| `gre_ipsec` | WebUI-GRE IPSec |
| `homepage` | WebUI-Homepage |
| `incidents_dlp` | WebUI-Incidents DLP |
| `inline_swg` | WebUI-Inline SWG |
| `inlineswg` | WebUI-Inlineswg |
| `introspection` | WebUI-Introspection |
| `ips` | WebUI-IPS |
| `npa` | WebUI-NPA |
| `platform` | WebUI-Platform |
| `rbac` | WebUI-RBAC |
| `rbi` | WebUI-RBI |
| `rbi_inline_rtp_edit` | WebUI-RBI (Inline RTP Edit) |
| `smtp_dlp` | WebUI-SMTP DLP |
| `spm` | WebUI-SPM |
| `steering` | WebUI-Steering |
| `ueba` | WebUI-UEBA |
| `virtual_private_edge` | WebUI-Virtual Private Edge |

Teams without tenant IDs configured prompt for a tenant ID on first use. A
team not in this table may still exist -- this list can drift from the
package; `flag list` is the source of truth.

## Reference files

- `references/flag-cli-source.md` -- upstream repo locations for the CLI
  and the Python fallback scripts, and where to look if either needs a fix
  or a new team onboarded.

## Things to not do

- Do not read or write flags via raw `kubectl exec` / hand-rolled curl when
  this CLI covers the team -- always go through `flag` / `npx @netskope/flag`.
- Do not skip the prod-write CM-ticket confirmation, even if the user says
  "just do it" -- re-confirm per write, since team/tenant/flag context can
  drift across a session.
- Do not suppress the CLI's "read back flags to verify?" prompt.
- Do not overwrite a team's alias/config assumptions from memory -- if
  `flag list <team>` disagrees with this file's snapshot table, trust the
  live output.
