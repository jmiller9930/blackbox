#!/usr/bin/env python3
"""
Renaissance / research sync — align local git with origin, pull on the lab host, reload API only.

**Default (minimal):** same git flow as ``scripts/sync.py``, but on the remote we **do not** rebuild the
``web`` (nginx) image or ``docker compose up`` the full UI stack. We only ensure the **api** container
is up and **restart** it so Python reloads imports from the bind-mounted repo (``renaissance_v4/``,
``UIUX.Web/api_server.py``, ``dashboard.html`` served via the API route, etc.).

**Why not restart ``web`` every time?** The operator dashboard at ``/dashboard.html`` is proxied to
``api`` and reads ``UIUX.Web/dashboard.html`` from the repo mount — no nginx image rebuild needed for
those edits. Rebuilding ``web`` is for static assets baked into the nginx image (e.g. ``index.html``,
``styles.css``) or nginx config changes.

**When to use something else:**
  - Full operator UI stack (build ``web`` + ``up -d`` + restart ``api``): ``python3 scripts/sync.py``
    or ``python3 scripts/jupsync.py --full-stack`` (SeanV3 + optional UI).
  - This script with ``--rebuild-web``: Renaissance code + nginx-served static changes in one shot.

Environment (optional, same family as ``sync.py`` / ``jupsync.py``):
  BLACKBOX_SYNC_SSH / RENSYNC_SSH   SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME              Remote repo dir under ~ (default: blackbox)
  BLACKBOX_REMOTE_BRANCH / RENSYNC_BRANCH  Branch to pull on remote (default: main)

Usage (from repo root):
  python3 scripts/rensync.py
  python3 scripts/rensync.py --dry-run
  python3 scripts/rensync.py --skip-push
  python3 scripts/rensync.py --rebuild-web      # also rebuild nginx image + full compose up (rare)
  python3 scripts/rensync.py --git-only         # remote git pull only; no docker
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


DEFAULT_SSH = os.environ.get("RENSYNC_SSH") or os.environ.get("BLACKBOX_SYNC_SSH", "jmiller@clawbot.a51.corp")
DEFAULT_REMOTE_DIR = os.environ.get("BLACKBOX_REMOTE_HOME", "blackbox")
DEFAULT_REMOTE_BRANCH = os.environ.get("RENSYNC_BRANCH") or os.environ.get("BLACKBOX_REMOTE_BRANCH", "main")


def _find_git_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.stderr.write(f"rensync.py: no .git found above {__file__}\n")
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


def _remote_script(
    remote_dir_name: str,
    pull_branch: str,
    *,
    git_only: bool,
    rebuild_web: bool,
) -> str:
    git_block = f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "REMOTE_HEAD=$(git rev-parse HEAD)"
"""
    if git_only:
        return git_block

    if rebuild_web:
        return git_block + f"""
echo "--- UIUX.Web: rebuild web + full stack + restart api (same as scripts/sync.py) ---"
cd ~/{remote_dir_name}/UIUX.Web
docker compose build web
docker compose up -d
docker compose restart api
docker compose ps
"""

    return git_block + f"""
echo "--- UIUX.Web: restart api only (Renaissance / repo-mounted Python + dashboard route) ---"
cd ~/{remote_dir_name}/UIUX.Web
docker compose up -d api
docker compose restart api
docker compose ps api
"""


def _remote_rensync(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
    git_only: bool,
    rebuild_web: bool,
) -> None:
    body = _remote_script(
        remote_dir_name,
        pull_branch,
        git_only=git_only,
        rebuild_web=rebuild_web,
    )
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    label = "git pull only" if git_only else ("rebuild web + compose" if rebuild_web else "git pull + restart api")
    print(f"SSH {ssh_target}: {label} …", flush=True)
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
        description="Push to origin, pull on remote, restart UIUX.Web api only (default). "
        "Use --rebuild-web when nginx image / static assets need rebuilding."
    )
    ap.add_argument("--ssh", default=DEFAULT_SSH, help=f"SSH user@host (default: {DEFAULT_SSH})")
    ap.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help="Directory under remote home (default: blackbox → ~/blackbox)",
    )
    ap.add_argument("--remote-branch", default=DEFAULT_REMOTE_BRANCH, help="Branch to pull on remote")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH pull + restart")
    ap.add_argument(
        "--git-only",
        action="store_true",
        help="Only git fetch/pull on remote; do not run docker compose",
    )
    ap.add_argument(
        "--rebuild-web",
        action="store_true",
        help="Rebuild nginx web image and docker compose up -d (use when static-in-image files changed)",
    )
    args = ap.parse_args()

    if args.git_only and args.rebuild_web:
        sys.stderr.write("rensync.py: use only one of --git-only or --rebuild-web.\n")
        sys.exit(2)

    repo = _find_git_root()
    branch = _branch(repo)
    if branch == "HEAD":
        sys.stderr.write("rensync.py: detached HEAD; checkout a branch before syncing.\n")
        sys.exit(1)

    print(f"Repo: {repo}  branch: {branch}", flush=True)
    if branch != args.remote_branch:
        print(
            f"Note: pushing origin/{branch} but remote will pull origin/{args.remote_branch}.",
            file=sys.stderr,
        )

    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)
    _remote_rensync(
        args.ssh,
        args.remote_dir,
        args.remote_branch,
        dry_run=args.dry_run,
        git_only=args.git_only,
        rebuild_web=args.rebuild_web,
    )


if __name__ == "__main__":
    main()
