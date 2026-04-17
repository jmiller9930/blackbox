#!/usr/bin/env python3
"""
Renaissance / research sync — align local git with origin, pull on the lab host, rebuild and restart UI.

**Default (full):** push (if needed), remote ``git pull``, then ``docker compose build`` (all services with
a build), ``docker compose up -d``, and ``docker compose restart api``. This keeps **nginx** (``web``),
**baked static assets**, and **api** images aligned with the repo — same class of fix as nginx
``/assets/`` routing and ``COPY assets`` into the web image.

**Faster path:** ``--api-only`` — only ``docker compose up -d api`` + ``restart api`` when you know only
repo-mounted Python/HTML via the API changed and nginx/static did not.

**Git only:** ``--git-only`` — remote pull only; no docker.

Environment (optional, same family as ``sync.py`` / ``jupsync.py``):
  BLACKBOX_SYNC_SSH / RENSYNC_SSH   SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME              Remote repo dir under ~ (default: blackbox)
  BLACKBOX_REMOTE_BRANCH / RENSYNC_BRANCH  Branch to pull on remote (default: main)

Usage (from repo root):
  python3 scripts/rensync.py
  python3 scripts/quant.py            # rensync then jupsync (SeanV3/Jupiter)
  python3 scripts/rensync.py --dry-run
  python3 scripts/rensync.py --skip-push
  python3 scripts/rensync.py --api-only      # restart api only (no full compose build)
  python3 scripts/rensync.py --git-only      # remote git pull only; no docker
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
    mode: str,
) -> str:
    git_block = f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "REMOTE_HEAD=$(git rev-parse HEAD)"
"""
    if mode == "git_only":
        return git_block

    if mode == "api_only":
        return git_block + f"""
echo "--- UIUX.Web: api only (up + restart) — use default rensync for full rebuild ---"
cd ~/{remote_dir_name}/UIUX.Web
docker compose up -d api
docker compose restart api
docker compose ps api
"""

    # full — build all images in compose file, bring stack up, restart api for import reload
    return git_block + f"""
echo "--- UIUX.Web: docker compose build + up -d + restart api (full) ---"
cd ~/{remote_dir_name}/UIUX.Web
docker compose build
docker compose up -d
docker compose restart api
docker compose ps
"""


def _remote_rensync(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
    mode: str,
) -> None:
    body = _remote_script(
        remote_dir_name,
        pull_branch,
        mode=mode,
    )
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    labels = {
        "git_only": "git pull only",
        "api_only": "git pull + api restart only",
        "full": "git pull + docker compose build + up -d + restart api",
    }
    print(f"SSH {ssh_target}: {labels[mode]} …", flush=True)
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
        description="Push to origin, pull on remote, then rebuild UIUX.Web stack (default) or api-only."
    )
    ap.add_argument("--ssh", default=DEFAULT_SSH, help=f"SSH user@host (default: {DEFAULT_SSH})")
    ap.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help="Directory under remote home (default: blackbox → ~/blackbox)",
    )
    ap.add_argument("--remote-branch", default=DEFAULT_REMOTE_BRANCH, help="Branch to pull on remote")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH pull + docker")
    ap.add_argument(
        "--git-only",
        action="store_true",
        help="Only git fetch/pull on remote; do not run docker compose",
    )
    ap.add_argument(
        "--api-only",
        action="store_true",
        help="Skip full compose build; only docker compose up -d api + restart api (faster)",
    )
    ap.add_argument(
        "--rebuild-web",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = ap.parse_args()

    if args.git_only and args.api_only:
        sys.stderr.write("rensync.py: use only one of --git-only or --api-only.\n")
        sys.exit(2)

    if args.rebuild_web:
        print(
            "rensync.py: note: --rebuild-web is obsolete; full rebuild is now the default (remove the flag).",
            file=sys.stderr,
        )

    if args.git_only:
        mode = "git_only"
    elif args.api_only:
        mode = "api_only"
    else:
        mode = "full"

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
        mode=mode,
    )


if __name__ == "__main__":
    main()
