#!/usr/bin/env python3
"""QA01 parallel namespace tenant routing: inspect, and emit gated mutations.

  show    read the current tenant binding for every / one rtp namespace (safe)
  add     emit the commands to bind a tenant     (emits only, never executes)
  remove  emit the commands to unbind a tenant   (emits only, never executes)

This script NEVER mutates the VM. Every write path prints a command sequence for
a human to review and run, because the target nginx serves ALL of QA01 and a bad
config there is everyone's outage. Reads go over `tsh ssh` and need sudo on the
VM because the generated configs are 0600 root.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys

# --- pinned target ----------------------------------------------------------

TSH_CLUSTER = "iad0"
VM_HOST = "ngsslwebui01.qa01-mp-npe.nc1.iad0.nsscloud.net"
CONF_DIR = "/etc/nginx/conf.d"
NGINX_CONF = "/etc/nginx/nginx-sslwebui.conf"
PNS_SCRIPT = f"{CONF_DIR}/pns_setup.sh"

NS_ID_RE = re.compile(r"^rtp\d{1,2}$")
CONF_TEMPLATE = f"{CONF_DIR}/webui_proxy_{{ns}}.nginx.conf"
# Anchored on purpose: an unanchored match also hits `proxy_ssl_server_name`.
SERVER_NAME_GREP = r"^[[:space:]]*server_name[[:space:]]"

VALIDATE = f"sudo nginx -t -c {NGINX_CONF}"
RELOAD = "sudo supervisorctl signal HUP nginx"


class Fail(Exception):
    pass


def assert_target() -> None:
    """Structural guard: this skill is scoped to the QA01 NPE nginx VM only."""
    if "prod" in VM_HOST or TSH_CLUSTER != "iad0" or "qa01-mp-npe" not in VM_HOST:
        raise Fail(
            "refusing to run: target host is not the QA01 NPE nginx VM. "
            "This skill must never be pointed at a production POP."
        )


def ssh(remote_cmd: str) -> str:
    assert_target()
    proc = subprocess.run(
        ["tsh", "ssh", "--cluster", TSH_CLUSTER, VM_HOST, "--", remote_cmd],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        hint = ""
        if "offline or does not exist" in err:
            hint = (
                "\nhint: this message also appears when the teleport profile is "
                "expired, and when --cluster is wrong. Run `tsh status`, then "
                "`tsh login --proxy=teleport.netskope.io` if needed. "
                "See references/teleport-access.md"
            )
        raise Fail(f"tsh ssh failed ({proc.returncode}): {err}{hint}")
    return proc.stdout


def validate_ns_id(ns_id: str) -> str:
    if not NS_ID_RE.match(ns_id):
        raise Fail(f"--ns-id must look like 'rtp12', got {ns_id!r}")
    return ns_id


def read_bindings(ns_id: str | None = None) -> dict[str, list[str]]:
    """Return {ns_id: [tenant, ...]} straight from the VM."""
    glob = f"webui_proxy_{ns_id}.nginx.conf" if ns_id else "webui_proxy_rtp*.nginx.conf"
    remote = (
        f'for f in {CONF_DIR}/{glob}; do '
        '[ -e "$f" ] || continue; '
        'b=$(basename "$f" .nginx.conf); '
        f'sn=$(sudo grep -m1 -E {shlex.quote(SERVER_NAME_GREP)} "$f" '
        r"""| sed -e 's/^[[:space:]]*server_name[[:space:]]*//' -e 's/;[[:space:]]*$//'); """
        'echo "${b#webui_proxy_}|$sn"; '
        "done"
    )
    out: dict[str, list[str]] = {}
    for line in ssh(remote).splitlines():
        if "|" not in line:
            continue
        ns, sn = line.split("|", 1)
        out[ns.strip()] = sn.split()
    return out


# --- subcommands ------------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    ns_id = validate_ns_id(args.ns_id) if args.ns_id else None
    bindings = read_bindings(ns_id)
    if not bindings:
        target = ns_id or "any rtp namespace"
        print(f"no nginx routing config found for {target} on {VM_HOST}")
        print("Nothing is bound, so those tenants fall through to qa01-mp-npe--webui.")
        return 1
    print(f"host: {VM_HOST} (cluster {TSH_CLUSTER})\n")
    for ns in sorted(bindings):
        tenants = bindings[ns] or ["(none - suspicious, see nginx-internals.md)"]
        print(f"{ns}:")
        for t in tenants:
            print(f"    {t}")
    print(
        "\nSource of truth is the server_name line in "
        f"{CONF_TEMPLATE.format(ns='<ns>')}.\n"
        "A tenant listed here still needs a running pod in the matching namespace "
        "-> qa01-parallel-namespace-deploy verify."
    )
    return 0


def emit_header(action: str, ns_id: str) -> None:
    print(f"# {action} for {ns_id} on {VM_HOST}")
    print("# Review these before running. This script executed nothing.\n")


def emit_login() -> None:
    """Emit an interactive login rather than one-shot wrapped commands.

    Nested quoting through `tsh ssh -- '<cmd>'` turns a sed expression into
    unreadable '"'"' soup, and an unreviewable command defeats the whole point
    of emitting instead of executing. Log in, then run plain commands.
    """
    print("# 0. log in to the VM (run the rest ON the VM)")
    print(f"tsh ssh --cluster {TSH_CLUSTER} {VM_HOST}")
    print()


def cmd_add(args: argparse.Namespace) -> int:
    ns_id = validate_ns_id(args.ns_id)
    if not args.emit:
        print(
            "This script never mutates the VM. Re-run with --emit to print the\n"
            "command sequence, then run it yourself after an AskUserQuestion gate."
        )
        return 3

    existing = read_bindings(ns_id).get(ns_id)
    webui_address = args.webui_address or f"webui-{ns_id}.qa01-mp-npe-{ns_id}--webui"

    emit_header("Add tenant(s)", ns_id)
    if existing is None:
        print("# NOTE: no config exists yet for this ns-id -> FIRST-TIME generation.")
        print("#       The script refuses to overwrite pre-existing generated files.")
        if not args.apiv1_address:
            print("#       Pass --apiv1-address too if you need /api/v1/* routed;")
            print("#       it only takes effect at first-time generation.\n")
    else:
        print(f"# current server_name: {' '.join(existing)}")
        print("# append mode: existing tenants are preserved\n")
        already = [t for t in args.tenants if t in existing]
        if already:
            print(f"# ALREADY BOUND, nothing to do for: {' '.join(already)}\n")
            if len(already) == len(args.tenants):
                return 0

    setup = [
        f"sudo bash {PNS_SCRIPT}",
        f"--ns-id {ns_id}",
        f"--webui-address {webui_address}",
    ]
    if args.apiv1_address:
        setup.append(f"--apiv1-address {args.apiv1_address}")
    setup.append("--tenants " + " ".join(shlex.quote(t) for t in args.tenants))

    emit_login()
    print("# 1. generate / append")
    print("  " + " \\\n    ".join(setup))
    print("\n# 2. dry run - MUST pass before reloading")
    print(f"  {VALIDATE}")
    print("\n# 3. AskUserQuestion gate here, showing the nginx -t output")
    print("\n# 4. reload (prints: nginx: signalled)")
    print(f"  {RELOAD}")
    print("\n# 5. confirm, back on your machine")
    print(f"python3 scripts/pns_routing.py show --ns-id {ns_id}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    ns_id = validate_ns_id(args.ns_id)
    if not args.emit:
        print(
            "This script never mutates the VM. Re-run with --emit to print the\n"
            "command sequence, then run it yourself after an AskUserQuestion gate.\n"
            "Removal is a hand edit of a live root-owned config - the highest-risk\n"
            "operation in this skill. Read the emitted commands carefully."
        )
        return 3

    existing = read_bindings(ns_id).get(ns_id)
    if existing is None:
        print(f"no config for {ns_id}; nothing to remove")
        return 1

    unknown = [t for t in args.tenants if t not in existing]
    survivors = [t for t in existing if t not in args.tenants]
    conf = CONF_TEMPLATE.format(ns=ns_id)

    emit_header("Remove tenant(s)", ns_id)
    print(f"# current server_name : {' '.join(existing)}")
    print(f"# removing            : {' '.join(args.tenants)}")
    print(f"# resulting           : {' '.join(survivors) if survivors else '(empty)'}\n")

    if unknown:
        print(f"# WARNING: not currently bound, check for a typo: {' '.join(unknown)}")
        print("#          A regex-form entry will not match a literal hostname here.\n")
    if not survivors:
        print(
            "# STOP: every tenant would be removed. An empty server_name is not a\n"
            "#       valid disabled state. Tear the namespace routing down instead:\n"
            f"#         sudo rm {conf}\n"
            f"#         sudo rm -rf {CONF_DIR}/pns_{ns_id}\n"
            f"#         {VALIDATE}\n"
            f"#         {RELOAD}\n"
            "#       See the 'Tear down' section in SKILL.md. Re-read the rm paths\n"
            "#       before running them."
        )
        return 2

    new_line = "    server_name         " + " ".join(survivors) + ";"

    emit_login()
    print("# 1. back up (this backup is your rollback)")
    print(f"  sudo cp -p {conf} {conf}.bak.$(date +%Y%m%d%H%M%S)")
    print(f"  sudo ls -la {conf}.bak.*")
    print("\n# 2. rewrite the FIRST server_name line only. Check the diff after.")
    print(f"  sudo sed -i '0,/^[[:space:]]*server_name[[:space:]]/{{")
    print(f"    s|^[[:space:]]*server_name[[:space:]].*|{new_line}|")
    print(f"  }}' {conf}")
    print("\n#    Prefer a real editor if you are at all unsure:")
    print(f"  sudo vi {conf}      # and set the server_name line to:")
    print(f"  #   {new_line.strip()}")
    print("\n# 3. eyeball the result before validating")
    print(f'  sudo grep -nE "{SERVER_NAME_GREP}" {conf}')
    print(f"  sudo diff {conf}.bak.* {conf}")
    print("\n# 4. dry run - MUST pass. If it fails, restore the backup and")
    print("#    re-validate before doing anything else.")
    print(f"  {VALIDATE}")
    print("\n# 5. AskUserQuestion gate here, showing the nginx -t output")
    print("\n# 6. reload (prints: nginx: signalled)")
    print(f"  {RELOAD}")
    print("\n# 7. confirm, back on your machine")
    print(f"python3 scripts/pns_routing.py show --ns-id {ns_id}")
    print(
        "\n# Rollback, on the VM:\n"
        f"#   sudo cp -p {conf}.bak.<ts> {conf}\n"
        f"#   {VALIDATE}\n"
        f"#   {RELOAD}"
    )
    print(
        "\n# Status: this removal path has not been exercised against the VM from\n"
        "# this repo. Treat it as a reviewed proposal, not a proven runbook."
    )
    return 0


# --- cli --------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="read current tenant bindings (safe)")
    s.add_argument("--ns-id", help="e.g. rtp12; omit for all")

    a = sub.add_parser("add", help="emit commands to bind tenant(s)")
    a.add_argument("--ns-id", required=True)
    a.add_argument("--tenants", required=True, nargs="+")
    a.add_argument("--webui-address", help="default webui-<ns>.qa01-mp-npe-<ns>--webui")
    a.add_argument("--apiv1-address", help="only meaningful at first-time generation")
    a.add_argument("--emit", action="store_true", help="print the command sequence")

    r = sub.add_parser("remove", help="emit commands to unbind tenant(s)")
    r.add_argument("--ns-id", required=True)
    r.add_argument("--tenants", required=True, nargs="+")
    r.add_argument("--emit", action="store_true", help="print the command sequence")

    args = p.parse_args()
    handlers = {"show": cmd_show, "add": cmd_add, "remove": cmd_remove}
    try:
        return handlers[args.cmd](args)
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
