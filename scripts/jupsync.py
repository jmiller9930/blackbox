#!/usr/bin/env python3
"""
Jupiter / SeanV3 lab sync — push local git to origin, pull on clawbot, rebuild & restart
``vscode-test/seanv3`` (``seanv3`` + ``jupiter-web``).

Process (operator):
  1. Commit your changes in the blackbox repo (or use --skip-push if origin already has them).
  2. Run ``python3 scripts/jupsync.py`` from repo root (Mac or any machine with git + ssh).
  3. Script pushes current branch to origin, SSHs to the lab host, ``git pull``, then
     ``docker compose up -d --build`` in ``vscode-test/seanv3``.

This complements ``scripts/sync.py`` (BlackBox UIUX.Web nginx/api). Use **jupsync** for Jupiter
dashboard + SeanV3 engine; use **sync.py** for operator dashboard HTML/API.

Environment (optional):
  BLACKBOX_SYNC_SSH / JUPSYNC_SSH     SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME               Remote repo dir under ~ (default: blackbox)
  BLACKBOX_REMOTE_BRANCH / JUPSYNC_BRANCH  Branch to pull on remote (default: main)

Usage:
  python3 scripts/jupsync.py
  python3 scripts/jupsync.py --dry-run
  python3 scripts/jupsync.py --skip-push          # remote pull + compose only
  python3 scripts/jupsync.py --skip-health        # do not curl jupiter /health after

Reachability (important):
  The optional post-deploy ``curl http://127.0.0.1:707/health`` runs **on the lab host inside SSH** —
  there ``127.0.0.1`` is correct. From your **laptop** or any machine that is not the server, use the
  **server hostname** (e.g. ``http://clawbot.a51.corp:707/`` on VPN/LAN) or your **public DNS + port**
  (e.g. ``http://jupv3.greyllc.net:737/``); do not use ``localhost`` unless you have an explicit tunnel.
  Jupiter serves **HTTP** on 707 unless you terminate **HTTPS** in front (nginx, Caddy, etc.).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


DEFAULT_SSH = os.environ.get("JUPSYNC_SSH") or os.environ.get("BLACKBOX_SYNC_SSH", "jmiller@clawbot.a51.corp")
DEFAULT_REMOTE_DIR = os.environ.get("BLACKBOX_REMOTE_HOME", "blackbox")
DEFAULT_REMOTE_BRANCH = os.environ.get("JUPSYNC_BRANCH") or os.environ.get("BLACKBOX_REMOTE_BRANCH", "main")


def _find_git_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.stderr.write(f"jupsync.py: no .git found above {__file__}\n")
            sys.exit(1)
        cur = parent


def _run(cmd: list[str], *, cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True)


def _branch(repo: str) -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()


def _sync_push(repo: str, branch: str, *, dry_run: bool, skip_push: bool) -> None:
    _run(["git", "fetch", "origin"], cwd=repo)
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    try:
        origin_ref = _run(["git", "rev-parse", f"origin/{branch}"], cwd=repo).stdout.strip()
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


def _remote_script(remote_dir_name: str, pull_branch: str, *, health_check: bool) -> str:
    health = ""
    if health_check:
        health = """
echo "--- jupiter /health ---"
curl -sS --connect-timeout 5 "http://127.0.0.1:707/health" || echo "(health check failed — is jupiter-web up?)"
"""
    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "REMOTE_HEAD=$(git rev-parse HEAD)"
cd vscode-test/seanv3
docker compose up -d --build
docker compose ps
{health}
"""


def _remote_jupsync(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
    health_check: bool,
) -> None:
    body = _remote_script(remote_dir_name, pull_branch, health_check=health_check)
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    print(f"SSH {ssh_target}: git pull + docker compose (vscode-test/seanv3) …", flush=True)
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
    ap = argparse.ArgumentParser(
        description="Push to origin, then on remote: git pull + rebuild SeanV3/Jupiter docker compose."
    )
    ap.add_argument("--ssh", default=DEFAULT_SSH, help=f"SSH user@host (default: {DEFAULT_SSH})")
    ap.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help="Directory under remote home (default: blackbox → ~/blackbox)",
    )
    ap.add_argument("--remote-branch", default=DEFAULT_REMOTE_BRANCH, help="Branch to pull on remote")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH pull + compose")
    ap.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip post-deploy curl to http://127.0.0.1:707/health on remote",
    )
    args = ap.parse_args()

    repo = _find_git_root()
    branch = _branch(repo)
    if branch == "HEAD":
        sys.stderr.write("jupsync.py: detached HEAD; checkout a branch before syncing.\n")
        sys.exit(1)

    print(f"Repo: {repo}  branch: {branch}", flush=True)
    if branch != args.remote_branch:
        print(
            f"Note: pushing origin/{branch} but remote will pull origin/{args.remote_branch}.",
            file=sys.stderr,
        )

    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)
    _remote_jupsync(
        args.ssh,
        args.remote_dir,
        args.remote_branch,
        dry_run=args.dry_run,
        health_check=not args.skip_health,
    )


if __name__ == "__main__":
    main()
