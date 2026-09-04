#!/usr/bin/env python3
"""Gate script for QA01 parallel namespace (rtp-XX) deploys.

Read-only subcommands: occupancy, verify, check-branch, status.
Mutating subcommand: deploy (requires --confirm; --dry-run changes nothing).

Design rules:
  - The Kubernetes context is PINNED. The caller's current-context is often a
    production cluster; this script never uses it and refuses to run against
    anything other than the QA01 NPE cluster.
  - deploy without --confirm prints the plan and exits non-zero, so the agent
    must run an AskUserQuestion gate and re-invoke.
  - No third-party dependencies. Requires `kubectl` and `gh` on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- pinned constants -------------------------------------------------------

KUBE_CONTEXT = "stork-qa01-mp-npe-iad0-nc1"
NS_PATTERN = re.compile(r"^qa01-mp-npe-rtp(\d*)--webui$")
NS_TEMPLATE = "qa01-mp-npe-rtp{n}--webui"

WEBUI_REPO = "netSkope/webui"
SERVICE_REPO = "netSkope/service"
WORKFLOW = "create-parallel-namespace-branches.yml"
DEPLOY_BRANCH_TEMPLATE = "bot-deploy-pns-rtp-{n}"
BASE_BRANCH = "develop"

JIRA_RE = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")

# Audit trail, following the webui-ff-toggle convention of
# ~/.claude/state/<skill>/ at mode 0700. Reads never touch it.
STATE_DIR = Path(os.path.expanduser("~/.claude/state/pns_deploy"))
LOG_FILE = STATE_DIR / "deploy.log"
# A deploy takes ~40 min end to end; re-triggering the same namespace inside
# this window is almost always a mistake rather than an intent.
REPEAT_WINDOW_S = 45 * 60

# A change under any of these in the gap between the branch and develop can
# break the image build with an error that looks unrelated to the PR.
BUILD_SYSTEM_PREFIXES = (
    "compile/",
    "images/",
    "src/goldenDB/",
    ".gitmodules",
    "deployment/",
)
BUILD_SYSTEM_NAMES = ("Dockerfile", "Makefile", "Makefile.parallel")


class Fail(Exception):
    pass


def run(cmd: list[str], check: bool = True) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise Fail(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def run_json(cmd: list[str]) -> object:
    out = run(cmd)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise Fail(f"expected JSON from {' '.join(cmd)}: {exc}") from exc


# --- kubernetes -------------------------------------------------------------


def assert_context() -> None:
    """Refuse to touch any cluster other than the pinned QA01 NPE one."""
    names = run(["kubectl", "config", "get-contexts", "-o", "name"]).split()
    if KUBE_CONTEXT not in names:
        raise Fail(
            f"kube context {KUBE_CONTEXT!r} not found.\n"
            "This skill only ever reads the QA01 NPE cluster. Add the context "
            "(Rancher/nsk kubeconfig download) and retry.\n"
            "If you have the k8s MCP tools available instead, use those with "
            f"cluster={KUBE_CONTEXT} and skip this script's k8s subcommands."
        )


def kubectl(args: list[str]) -> list[str]:
    return ["kubectl", "--context", KUBE_CONTEXT] + args


def ns_sort_key(ns: str) -> tuple:
    m = NS_PATTERN.match(ns)
    num = m.group(1) if m else ""
    return (0, int(num)) if num else (1, 0)


def list_rtp_namespaces() -> list[str]:
    data = run_json(kubectl(["get", "ns", "-o", "json"]))
    found = [
        item["metadata"]["name"]
        for item in data.get("items", [])
        if NS_PATTERN.match(item["metadata"]["name"])
    ]
    return sorted(found, key=ns_sort_key)


def age_of(ts: str | None) -> str:
    if not ts:
        return "?"
    started = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - started
    mins = int(delta.total_seconds() // 60)
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def pods_in(ns: str) -> list[dict]:
    data = run_json(kubectl(["get", "pods", "-n", ns, "-o", "json"]))
    out = []
    for item in data.get("items", []):
        meta, spec, status = item["metadata"], item["spec"], item.get("status", {})
        containers = spec.get("containers", [])
        image = containers[0].get("image", "") if containers else ""
        tag = image.rsplit(":", 1)[-1] if ":" in image else image
        statuses = status.get("containerStatuses") or []
        ready = sum(1 for c in statuses if c.get("ready"))
        restarts = sum(c.get("restartCount", 0) for c in statuses)
        out.append(
            {
                "name": meta["name"],
                "phase": status.get("phase", "?"),
                "ready": f"{ready}/{len(containers)}",
                "restarts": restarts,
                "image_tag": tag,
                "age": age_of(status.get("startTime") or meta.get("creationTimestamp")),
            }
        )
    return sorted(out, key=lambda p: p["name"])


def classify(pods: list[dict]) -> str:
    if not pods:
        return "EMPTY      no pods - never set up, or torn down"
    webui = [p for p in pods if p["name"].startswith("webui-webui-")]
    ref = webui or pods
    running = [p for p in ref if p["phase"] == "Running"]
    pending = [p for p in ref if p["phase"] == "Pending"]
    if pending and not running:
        return (
            f"STALE      {len(pending)} pod(s) Pending (oldest {max(p['age'] for p in pending)}) "
            "- abandoned deploy holding reservations"
        )
    if running:
        note = f"IN USE     Running, image {running[0]['image_tag']}, age {running[0]['age']}"
        if pending:
            note += f" (+{len(pending)} Pending leftover)"
        return note
    return "UNCLEAR    " + ", ".join(f"{p['name']}={p['phase']}" for p in ref)


# --- subcommands: read-only -------------------------------------------------


def cmd_occupancy(_args: argparse.Namespace) -> int:
    assert_context()
    namespaces = list_rtp_namespaces()
    if not namespaces:
        print("no qa01-mp-npe-rtp*--webui namespaces found")
        return 1
    print(f"cluster: {KUBE_CONTEXT}\n")
    for ns in namespaces:
        print(f"{ns:34s} {classify(pods_in(ns))}")

    present = {NS_PATTERN.match(ns).group(1) for ns in namespaces}  # type: ignore[union-attr]
    absent = [f"{i:02d}" for i in range(1, 21) if f"{i:02d}" not in present]
    if absent:
        print(f"\nNo namespace at all for: rtp{', rtp'.join(absent)}")
        print("  (never set up, or torn down - not automatically yours to use)")

    print(
        "\nIN USE  -> do not take it.\n"
        "STALE   -> idle in practice; still confirm with the owner.\n"
        "EMPTY   -> confirm with the owner before claiming.\n"
        "\nOwnership table is NOT here on purpose - it drifts. See "
        "references/sources.md for the Confluence page that holds it."
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    assert_context()
    ns = NS_TEMPLATE.format(n=args.namespace)
    if ns not in list_rtp_namespaces():
        print(f"namespace {ns} does not exist on {KUBE_CONTEXT}")
        return 1
    pods = pods_in(ns)
    print(f"namespace: {ns}\ncluster:   {KUBE_CONTEXT}\n")
    if not pods:
        print("no pods -> nothing deployed")
        return 1
    for p in pods:
        print(
            f"  {p['name']:42s} {p['phase']:9s} {p['ready']:5s} "
            f"restarts={p['restarts']:<4d} age={p['age']:<6s} {p['image_tag']}"
        )
    healthy = [
        p
        for p in pods
        if p["name"].startswith("webui-webui-")
        and p["phase"] == "Running"
        and p["ready"].split("/")[0] == p["ready"].split("/")[1]
    ]
    print()
    if healthy:
        print(
            f"ROLLOUT OK - {len(healthy)} webui pod(s) Running and ready.\n"
            "This is the authority, not the Jenkins result and not the GitHub\n"
            "Action conclusion. A deploy job that reported UNSTABLE with a pod\n"
            "in this state has succeeded."
        )
        return 0
    print("ROLLOUT NOT CONFIRMED - no ready webui pod. See references/troubleshooting.md")
    return 1


def compare(base: str, head: str) -> dict:
    return run_json(
        ["gh", "api", f"repos/{WEBUI_REPO}/compare/{base}...{head}"]
    )  # type: ignore[return-value]


def cmd_check_branch(args: argparse.Namespace) -> int:
    branch = args.branch
    meta = compare(BASE_BRANCH, branch)
    behind = meta.get("behind_by", 0)
    ahead = meta.get("ahead_by", 0)
    print(f"branch: {branch}\nvs {BASE_BRANCH}: ahead {ahead}, behind {behind}\n")
    if behind == 0:
        print("Up to date with develop - staleness is not your build problem.")
        return 0

    gap = compare(branch, BASE_BRANCH)
    files = [f.get("filename", "") for f in gap.get("files", [])]
    risky = sorted(
        {
            f
            for f in files
            if f.startswith(BUILD_SYSTEM_PREFIXES)
            or f.rsplit("/", 1)[-1] in BUILD_SYSTEM_NAMES
        }
    )
    commits = gap.get("commits", [])
    print(f"{len(commits)} commit(s) on develop missing from this branch:")
    for c in commits:
        subject = c["commit"]["message"].split("\n", 1)[0]
        print(f"  {c['sha'][:8]}  {subject}")

    if risky:
        print(f"\nBUILD RISK - {len(risky)} build-system file(s) changed in the gap:")
        for f in risky[:25]:
            print(f"  {f}")
        if len(risky) > 25:
            print(f"  ... and {len(risky) - 25} more")
        print(
            "\nMerge develop into the branch and push BEFORE deploying. The\n"
            "pipeline builds your branch, not develop, so these fixes are\n"
            "absent from your build and it can fail on code you never touched.\n"
            "See references/troubleshooting.md section 1."
        )
        return 2
    print(
        "\nNo build-system files in the gap. Staleness is unlikely to break the\n"
        "build, though merging develop is still good hygiene.\n"
        "NOTE: the compare API caps files at 300 and commits at 250; on a very\n"
        "large gap, verify by hand."
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    data = run_json(
        [
            "gh", "run", "view", str(args.run_id),
            "--repo", WEBUI_REPO,
            "--json", "status,conclusion,jobs,url",
        ]
    )
    print(f"run:        {data.get('url')}")
    print(f"status:     {data.get('status')}  conclusion: {data.get('conclusion')}\n")
    build_failed = deploy_failed = False
    for job in data.get("jobs", []):
        name, concl = job.get("name", ""), job.get("conclusion") or job.get("status")
        print(f"  {concl or '?':10s} {name}")
        if "build-webui" in name and concl == "failure":
            build_failed = True
        if "deploy-namespace" in name and concl == "failure":
            deploy_failed = True
    print()
    if build_failed:
        print(
            "BUILD STAGE FAILED - real blocker, no image was produced and nothing\n"
            "was deployed. First suspect: branch behind develop. Run\n"
            "  python3 scripts/pns_deploy.py check-branch --branch <branch>\n"
            "See references/troubleshooting.md section 1."
        )
        return 2
    if deploy_failed:
        print(
            "DEPLOY STAGE FAILED - this is frequently UNSTABLE on a rollout that\n"
            "actually succeeded. Do NOT conclude failure yet:\n"
            "  python3 scripts/pns_deploy.py verify --namespace <NN>\n"
            "See references/troubleshooting.md section 2."
        )
        return 2
    if data.get("status") != "completed":
        print("Still running. Re-check later; a poll timeout does not cancel Jenkins.")
        return 0
    print("No failing build/deploy job. Still verify the rollout in Kubernetes.")
    return 0


# --- audit trail and concurrency guards -------------------------------------


def audit_append(ns_num: str, branch: str, jira: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = f"{int(time.time())} rtp{ns_num} {branch} {jira}\n"
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line)


def audit_recent(ns_num: str) -> int | None:
    """Seconds since this machine last triggered a deploy for this namespace."""
    if not LOG_FILE.exists():
        return None
    newest = None
    for raw in LOG_FILE.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) < 2 or parts[1] != f"rtp{ns_num}":
            continue
        try:
            newest = max(newest or 0, int(parts[0]))
        except ValueError:
            continue
    return None if newest is None else int(time.time()) - newest


def running_workflow_runs() -> list[dict]:
    """In-flight runs of this workflow, from GitHub - real shared state.

    A local rate-limit file cannot see a colleague's deploy; this can.
    """
    data = run_json(
        [
            "gh", "run", "list",
            "--repo", WEBUI_REPO,
            "--workflow", WORKFLOW,
            "--limit", "20",
            "--json", "databaseId,status,createdAt",
        ]
    )
    return [r for r in data if r.get("status") in ("in_progress", "queued", "requested", "waiting")]  # type: ignore[union-attr]


# --- subcommand: mutating ---------------------------------------------------


def cmd_deploy(args: argparse.Namespace) -> int:
    if not JIRA_RE.match(args.jira):
        raise Fail(
            f"invalid --jira {args.jira!r}; the deploy job requires a real key "
            "matching ^[A-Z][A-Z0-9]+-[0-9]+$ (e.g. ENG-1234567) and rejects "
            "placeholders."
        )
    try:
        n = int(args.namespace, 10)
    except ValueError:
        raise Fail(f"--namespace must be numeric, got {args.namespace!r}") from None
    nn = f"{n:02d}"
    ns = NS_TEMPLATE.format(n=nn)

    # Confirm the branch exists before doing anything else.
    run(["gh", "api", f"repos/{WEBUI_REPO}/branches/{args.branch}"])

    print("PLAN")
    print(f"  workflow          {WORKFLOW} ({WEBUI_REPO})")
    print(f"  namespace input   {nn}")
    print(f"  target namespace  {ns}")
    print(f"  deploy branches   {DEPLOY_BRANCH_TEMPLATE.format(n=nn)}")
    print(f"                    in {WEBUI_REPO} and {SERVICE_REPO} (force-updated)")
    print(f"  source branch     {args.branch}")
    print(f"  jira              {args.jira}")
    print(f"  disable pods      {args.disable_pods_method}")
    print(f"  trigger build     {'no (branches only)' if args.branches_only else 'yes'}")

    print("\nOCCUPANT")
    try:
        assert_context()
        print(f"  {ns}: {classify(pods_in(ns)) if ns in list_rtp_namespaces() else 'namespace absent'}")
    except Fail as exc:
        print(f"  could not check ({exc.args[0].splitlines()[0]})")
        print("  Check occupancy another way before confirming - deploying blind")
        print("  can wipe out another team's environment.")

    print("\nSTALENESS")
    try:
        meta = compare(BASE_BRANCH, args.branch)
        behind = meta.get("behind_by", 0)
        print(f"  {behind} commit(s) behind {BASE_BRANCH}")
        if behind:
            print("  Run check-branch before deploying; a stale branch can fail the build")
            print("  on code your PR never touched.")
    except Fail as exc:
        print(f"  could not check ({exc.args[0].splitlines()[0]})")

    print("\nCONCURRENCY")
    blockers: list[str] = []
    try:
        inflight = running_workflow_runs()
        if inflight:
            ids = ", ".join(str(r["databaseId"]) for r in inflight)
            print(f"  {len(inflight)} run(s) of this workflow already in flight: {ids}")
            print("  Someone may be mid-deploy, possibly on another namespace.")
            blockers.append("a workflow run is already in flight")
        else:
            print("  no in-flight runs of this workflow")
    except Fail as exc:
        print(f"  could not check ({exc.args[0].splitlines()[0]})")

    since = audit_recent(nn)
    if since is not None and since < REPEAT_WINDOW_S:
        print(f"  this machine triggered rtp{nn} {since // 60}m ago")
        print("  A deploy takes ~40 min; the earlier one may still be running.")
        blockers.append(f"rtp{nn} was triggered from here {since // 60}m ago")
    elif since is not None:
        print(f"  last local trigger for rtp{nn}: {since // 3600}h ago")

    if args.dry_run:
        print("\n--dry-run: nothing triggered.")
        return 0
    if not args.confirm:
        print(
            "\nREFUSING TO TRIGGER: --confirm not given.\n"
            "This overwrites the bot-deploy branches and replaces whatever is\n"
            "running in the target namespace. Present the plan above to the user\n"
            "via AskUserQuestion, including the occupant, then re-invoke with\n"
            "--confirm."
        )
        return 3
    if blockers and not args.force:
        print("\nREFUSING TO TRIGGER: " + "; ".join(blockers) + ".")
        print(
            "Check the in-flight run and the target namespace first. If you have\n"
            "confirmed it is safe to proceed anyway, re-invoke with --force.\n"
            "Concurrent deploys to the same namespace race each other."
        )
        return 4

    cmd = [
        "gh", "workflow", "run", WORKFLOW,
        "--repo", WEBUI_REPO,
        "-f", f"namespace={nn}",
        "-f", f"webui_branch={args.branch}",
        "-f", f"jira_ticket={args.jira}",
        "-f", f"disable_pods_method={args.disable_pods_method}",
        "-f", f"trigger_build={'false' if args.branches_only else 'true'}",
    ]
    run(cmd)
    audit_append(nn, args.branch, args.jira)
    print(f"\ntriggered, and recorded in {LOG_FILE}.")
    print("Expect ~20 min build + ~20-35 min deploy.")
    print("Find the run:")
    print(f"  gh run list --repo {WEBUI_REPO} --workflow {WORKFLOW} --limit 3")
    print("Then:")
    print("  python3 scripts/pns_deploy.py status --run-id <id>")
    print(f"  python3 scripts/pns_deploy.py verify --namespace {nn}")
    print("\nThe run going red does NOT mean the deploy failed. Verify in k8s.")
    return 0


# --- cli --------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("occupancy", help="list every rtp namespace and whether it is in use")

    v = sub.add_parser("verify", help="confirm a rollout actually landed (the authority)")
    v.add_argument("--namespace", required=True, help="namespace number, e.g. 12")

    c = sub.add_parser("check-branch", help="is the branch too stale to build?")
    c.add_argument("--branch", required=True)

    s = sub.add_parser("status", help="classify a workflow run's failure stage")
    s.add_argument("--run-id", required=True)

    d = sub.add_parser("deploy", help="trigger the deploy (mutating)")
    d.add_argument("--namespace", required=True, help="namespace number, e.g. 12")
    d.add_argument("--branch", required=True, help="source webui branch")
    d.add_argument("--jira", required=True, help="real Jira key, e.g. ENG-1234567")
    d.add_argument("--disable-pods-method", default="scale-to-zero",
                   choices=["scale-to-zero", "remove"],
                   help="'remove' only on a brand-new namespace; it can orphan pods")
    d.add_argument("--branches-only", action="store_true",
                   help="create branches without building or deploying")
    d.add_argument("--dry-run", action="store_true", help="print the plan, trigger nothing")
    d.add_argument("--confirm", action="store_true",
                   help="required to actually trigger; use only after an AskUserQuestion gate")
    d.add_argument("--force", action="store_true",
                   help="override the in-flight / recent-repeat guards; needs its own confirmation")

    args = p.parse_args()
    handlers = {
        "occupancy": cmd_occupancy,
        "verify": cmd_verify,
        "check-branch": cmd_check_branch,
        "status": cmd_status,
        "deploy": cmd_deploy,
    }
    try:
        return handlers[args.cmd](args)
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
