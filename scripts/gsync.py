#!/usr/bin/env python3
"""
gsync — git commit (optional), push to origin, pull on lab host, restart **only if needed**.

Compared to ``scripts/sync.py`` (always rebuilds/restarts UIUX.Web on the remote), **gsync** runs
``docker compose`` under ``UIUX.Web`` only when the commits **just pulled** on the remote touch
paths under ``UIUX.Web/`` (operator nginx/api/dashboard). Pure Python / docs / ``game_theory/``
changes skip docker.

Process:
  1. If the working tree is dirty and ``--no-commit`` is not set: ``git add -u`` and commit
     (default message is timestamped; override with ``-m``). Untracked files are not staged;
     ``git add`` them first if needed.
  2. ``git push`` current branch to origin (unless already aligned or ``--skip-push``).
  3. SSH to the lab host: ``git pull``. If nothing new was pulled, **done** (no compose).
  4. If new commits changed any file under ``UIUX.Web/``, run the same compose steps as
     ``sync.py`` (``build web``, ``up -d``, ``restart api``). Otherwise print skip message.

Environment (optional):
  BLACKBOX_SYNC_SSH / GSYNC_SSH     SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME              Remote repo dir under ~ (default: blackbox)
  BLACKBOX_REMOTE_BRANCH / GSYNC_BRANCH  Branch to pull (default: main)
  GSYNC_RESTART_PREFIXES            Comma-separated path prefixes that trigger compose
                                    (default: UIUX.Web/)

Usage (repo root):
  python3 scripts/gsync.py
  python3 scripts/gsync.py -m "describe change"
  python3 scripts/gsync.py --dry-run
  python3 scripts/gsync.py --no-commit          # push + remote pull; no local commit
  python3 scripts/gsync.py --skip-push          # commit only; then remote pull + conditional restart
  python3 scripts/gsync.py --force-restart      # always run UIUX.Web compose after remote pull
  python3 scripts/gsync.py --no-remote          # commit + push only (no SSH)

For Jupiter/SeanV3 stack use ``scripts/jupsync.py``. For unconditional UIUX.Web deploy use
``scripts/sync.py``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

DEFAULT_SSH = os.environ.get("GSYNC_SSH") or os.environ.get("BLACKBOX_SYNC_SSH", "jmiller@clawbot.a51.corp")
DEFAULT_REMOTE_DIR = os.environ.get("BLACKBOX_REMOTE_HOME", "blackbox")
DEFAULT_REMOTE_BRANCH = os.environ.get("GSYNC_BRANCH") or os.environ.get("BLACKBOX_REMOTE_BRANCH", "main")
DEFAULT_PREFIXES = os.environ.get("GSYNC_RESTART_PREFIXES", "UIUX.Web/").strip() or "UIUX.Web/"


def _find_git_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            sys.stderr.write(f"gsync.py: no .git found above {__file__}\n")
            sys.exit(1)
        cur = parent


def _run(cmd: list[str], *, cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True)


def _branch(repo: str) -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).stdout.strip()


def _working_tree_dirty(repo: str) -> bool:
    return bool(_run(["git", "status", "--porcelain"], cwd=repo).stdout.strip())


def _auto_commit(
    repo: str,
    *,
    dry_run: bool,
    no_commit: bool,
    message: str | None,
) -> None:
    if no_commit:
        if _working_tree_dirty(repo):
            print(
                "Working tree has uncommitted changes; --no-commit set — push may not include them.",
                file=sys.stderr,
            )
        return
    if not _working_tree_dirty(repo):
        print("Working tree clean; nothing to commit.")
        return
    default_msg = f"gsync auto-commit {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    msg = (message or default_msg).strip() or default_msg
    if dry_run:
        print(f"[dry-run] git add -u && git commit -m {msg!r}")
        return
    print("Working tree dirty — staging tracked changes (git add -u) and committing …", flush=True)
    subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if staged.returncode == 0:
        print("Nothing left to commit after staging (e.g. only untracked files changed).", file=sys.stderr)
        print("  Stage new files with: git add <paths>", file=sys.stderr)
        return
    subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True)
    print("Commit OK.", flush=True)


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
            "--skip-push set, skipping.",
        )
        return
    if dry_run:
        print(f"[dry-run] git push origin {branch}")
        return
    print(f"Pushing {branch} to origin …")
    subprocess.run(["git", "push", "origin", branch], cwd=repo, check=True)
    print("Push OK.")


def _bash_case_arms_for_prefixes(prefixes: list[str]) -> str:
    """One `path/*) NEED=1 ;;` line per prefix for `case \"$f\" in`."""
    lines: list[str] = []
    for raw in prefixes:
        p = raw.strip().rstrip("/")
        if not p:
            continue
        lines.append(f"      {p}/*) NEED=1 ;;")
    if not lines:
        lines.append("      *) ;;")
    return "\n".join(lines)


def _remote_script(
    remote_dir_name: str,
    pull_branch: str,
    *,
    prefixes: list[str],
    force_restart: bool,
) -> str:
    arms = _bash_case_arms_for_prefixes(prefixes)
    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
OLD=$(git rev-parse HEAD)
git pull origin {pull_branch}
NEW=$(git rev-parse HEAD)
if [ "$OLD" = "$NEW" ]; then
  echo "gsync: remote already up to date (HEAD unchanged); skipping compose."
  exit 0
fi
CHANGED=$(git diff --name-only "$OLD" "$NEW" || true)
echo "gsync: pulled commits; changed files:"
echo "$CHANGED" | sed 's/^/  /' || true
NEED=0
if [ "{int(force_restart)}" -eq 1 ]; then
  NEED=1
  echo "gsync: --force-restart: restarting UIUX.Web compose."
else
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
{arms}
    esac
  done <<< "$CHANGED"
  if [ "$NEED" -eq 1 ]; then
    echo "gsync: monitored path prefix matched; rebuilding/restarting UIUX.Web compose."
  else
    echo "gsync: no monitored path prefix in changed files; skipping docker compose."
    exit 0
  fi
fi
cd UIUX.Web
docker compose build web
docker compose up -d
docker compose restart api
docker compose ps
"""


def _remote_pull_maybe_compose(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    prefixes: list[str],
    force_restart: bool,
    dry_run: bool,
) -> None:
    body = _remote_script(remote_dir_name, pull_branch, prefixes=prefixes, force_restart=force_restart)
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    print(f"SSH {ssh_target}: git pull + conditional UIUX.Web compose …", flush=True)
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
        description="Commit (optional), push, remote pull, restart UIUX.Web compose only if needed.",
    )
    ap.add_argument("-m", "--message", default=None, help="Commit message when auto-committing dirty tree")
    ap.add_argument("--no-commit", action="store_true", help="Do not commit; warn if dirty")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH if not --no-remote")
    ap.add_argument("--no-remote", action="store_true", help="Skip SSH (local commit + push only)")
    ap.add_argument(
        "--force-restart",
        action="store_true",
        help="After remote pull, always run UIUX.Web docker compose (ignore path filter)",
    )
    ap.add_argument("--ssh", default=DEFAULT_SSH, help="SSH user@host")
    ap.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="Remote repo directory under ~")
    ap.add_argument("--remote-branch", default=DEFAULT_REMOTE_BRANCH, help="Branch to pull on remote")
    args = ap.parse_args()

    repo = _find_git_root()
    branch = _branch(repo)
    if branch == "HEAD":
        sys.stderr.write("gsync.py: detached HEAD; checkout a branch before syncing.\n")
        sys.exit(1)

    prefixes = [p.strip() for p in DEFAULT_PREFIXES.split(",") if p.strip()]
    if not prefixes:
        prefixes = ["UIUX.Web/"]

    print(f"gsync: repo={repo} branch={branch}", flush=True)
    if branch != args.remote_branch:
        print(
            f"Note: local branch is {branch!r}; remote pull uses {args.remote_branch!r}.",
            file=sys.stderr,
        )

    _auto_commit(repo, dry_run=args.dry_run, no_commit=args.no_commit, message=args.message)
    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)

    if args.no_remote:
        print("gsync: --no-remote set; skipping SSH.")
        return

    _remote_pull_maybe_compose(
        args.ssh,
        args.remote_dir,
        args.remote_branch,
        prefixes=prefixes,
        force_restart=args.force_restart,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
