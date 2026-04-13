#!/usr/bin/env python3
"""
Sync local git to origin, then pull on the remote lab host and restart UI stack services.

Default remote: jmiller@clawbot.a51.corp with repo at ~/blackbox and compose in UIUX.Web.

Environment overrides:
  BLACKBOX_SYNC_SSH     SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME   Home-relative path to repo on remote (default: blackbox -> ~/blackbox)
  BLACKBOX_REMOTE_BRANCH Branch to pull on remote (default: main)

Usage (from repo root):
  python3 scripts/sync.py
  python3 scripts/sync.py --dry-run
  python3 scripts/sync.py --skip-push
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


DEFAULT_SSH = os.environ.get("BLACKBOX_SYNC_SSH", "jmiller@clawbot.a51.corp")
DEFAULT_REMOTE_DIR = os.environ.get("BLACKBOX_REMOTE_HOME", "blackbox")
DEFAULT_REMOTE_BRANCH = os.environ.get("BLACKBOX_REMOTE_BRANCH", "main")


def _find_git_root() -> str:
    """Repo root: walk upward from this file until .git exists."""
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.stderr.write(f"sync.py: no .git found above {__file__}\n")
            sys.exit(1)
        cur = parent


def _run(
    cmd: list[str],
    *,
    cwd: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def _branch(repo: str) -> str:
    p = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return p.stdout.strip()


def _sync_push(repo: str, branch: str, *, dry_run: bool, skip_push: bool) -> None:
    _run(["git", "fetch", "origin"], cwd=repo)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    try:
        origin_ref = _run(
            ["git", "rev-parse", f"origin/{branch}"],
            cwd=repo,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        origin_ref = ""
    if head == origin_ref:
        print(f"Local {branch} matches origin/{branch} ({head[:12]}…); nothing to push.")
        return
    if skip_push:
        print(
            f"Would push {branch} (local {head[:12]}… != origin {origin_ref[:12] if origin_ref else 'missing'}…); "
            "--skip-push set, skipping."
        )
        return
    if dry_run:
        print(f"[dry-run] git push origin {branch}")
        return
    print(f"Pushing {branch} to origin …")
    subprocess.run(["git", "push", "origin", branch], cwd=repo, check=True)
    print("Push OK.")


def _remote_script(remote_dir_name: str, pull_branch: str) -> str:
    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "REMOTE_HEAD=$(git rev-parse HEAD)"
cd UIUX.Web
docker compose build web
docker compose up -d
docker compose restart api
docker compose ps
"""


def _remote_pull_and_restart(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
) -> None:
    body = _remote_script(remote_dir_name, pull_branch)
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    print(f"SSH {ssh_target}: git pull + docker compose (UIUX.Web) …", flush=True)
    r = subprocess.run(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=30",
            ssh_target,
            "bash",
            "--noprofile",
            "--norc",
            "-s",
        ],
        input=body,
        text=True,
    )
    if r.returncode != 0:
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description="Push local main, pull on remote, restart compose services.")
    ap.add_argument(
        "--ssh",
        default=DEFAULT_SSH,
        help=f"SSH user@host (default env BLACKBOX_SYNC_SSH or {DEFAULT_SSH})",
    )
    ap.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help="Directory name under remote home (default: blackbox → ~/blackbox)",
    )
    ap.add_argument(
        "--remote-branch",
        default=DEFAULT_REMOTE_BRANCH,
        help="Branch to git pull on remote (default: main or BLACKBOX_REMOTE_BRANCH)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH pull + restart")
    args = ap.parse_args()

    repo = _find_git_root()
    branch = _branch(repo)
    if branch == "HEAD":
        sys.stderr.write("sync.py: detached HEAD; checkout a branch before syncing.\n")
        sys.exit(1)

    print(f"Repo: {repo}  branch: {branch}", flush=True)
    if branch != args.remote_branch:
        print(
            f"Note: pushing origin/{branch} but remote will pull origin/{args.remote_branch}.",
            file=sys.stderr,
        )

    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)
    _remote_pull_and_restart(
        args.ssh,
        args.remote_dir,
        args.remote_branch,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
