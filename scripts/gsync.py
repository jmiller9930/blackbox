#!/usr/bin/env python3
"""
gsync — git commit (optional), push to origin, pull on lab host, restart **only if needed**.

Compared to ``scripts/sync.py`` (always rebuilds/restarts UIUX.Web on the remote), **gsync** runs:

- **UIUX.Web** ``docker compose`` when pulled commits touch paths under ``UIUX.Web/`` (or when
  ``--force-restart``).
- **Pattern-game Flask UI** (``python3 -m renaissance_v4.game_theory.web_app`` on port **8765**)
  when pulled commits touch ``renaissance_v4/game_theory/`` or other configured prefixes (or when
  ``--force-restart``). Remote helper: ``scripts/pattern_game_remote_restart.sh``.

If the remote repo was **already up to date** (no new commits pulled), gsync exits **unless**
``--force-restart`` is set — then it still runs the selected restarts so operators do not have to guess.

Process:
  1. If the working tree is dirty and ``--no-commit`` is not set: ``git add -u`` and commit
     (default message is timestamped; override with ``-m``). Untracked files are not staged;
     ``git add`` them first if needed.
  2. ``git push`` current branch to origin (unless already aligned or ``--skip-push``).
  3. SSH to the lab host: ``git pull``.
  4. If nothing changed and not ``--force-restart``, **done**.
  5. Otherwise, for each monitored path group, if commits matched (or ``--force-restart``):
     run UIUX.Web compose and/or ``pattern_game_remote_restart.sh``.

Environment (optional):
  BLACKBOX_SYNC_SSH / GSYNC_SSH     SSH target (default: jmiller@clawbot.a51.corp)
  BLACKBOX_REMOTE_HOME              Remote repo dir under ~ (default: blackbox)
  BLACKBOX_REMOTE_BRANCH / GSYNC_BRANCH  Branch to pull (default: main)
  GSYNC_UIUX_PREFIXES               Comma-separated prefixes that trigger **UIUX.Web** compose.
                                    Directory prefixes end with ``/`` (default: UIUX.Web/)
  GSYNC_PATTERN_GAME_PREFIXES       Comma-separated prefixes/files for **pattern-game** web restart.
                                    Use trailing ``/`` for directories; otherwise exact path
                                    (default: renaissance_v4/game_theory/,scripts/agent_context_bundle.py)

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
# Back-compat: GSYNC_RESTART_PREFIXES used to mean UIUX.Web only.
_DEFAULT_UI = os.environ.get("GSYNC_UIUX_PREFIXES") or os.environ.get("GSYNC_RESTART_PREFIXES", "UIUX.Web/")
DEFAULT_UI_PREFIXES = (_DEFAULT_UI or "UIUX.Web/").strip() or "UIUX.Web/"
DEFAULT_PATTERN_GAME_PREFIXES = (
    os.environ.get(
        "GSYNC_PATTERN_GAME_PREFIXES",
        "renaissance_v4/game_theory/,scripts/agent_context_bundle.py",
    )
    .strip()
    or "renaissance_v4/game_theory/"
)


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


def _bash_case_arm_line(prefix: str, var: str) -> str:
    """One ``case`` arm: directory ``foo/`` → ``foo/*)``, else exact file path."""
    p = prefix.strip()
    if not p:
        return ""
    if p.endswith("/"):
        return f"      {p.rstrip('/')}/*) {var}=1 ;;"
    return f"      {p}) {var}=1 ;;"


def _bash_case_block(prefixes: list[str], var: str) -> str:
    lines: list[str] = []
    for raw in prefixes:
        line = _bash_case_arm_line(raw, var)
        if line:
            lines.append(line)
    return "\n".join(lines) if lines else "      *) ;;"


def _remote_script(
    remote_dir_name: str,
    pull_branch: str,
    *,
    ui_prefixes: list[str],
    pg_prefixes: list[str],
    force_restart: bool,
) -> str:
    ui_arms = _bash_case_block(ui_prefixes, "NEED_UI")
    pg_arms = _bash_case_block(pg_prefixes, "NEED_PG")
    force = int(force_restart)
    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
OLD=$(git rev-parse HEAD)
git pull origin {pull_branch}
NEW=$(git rev-parse HEAD)
FORCE={force}

if [ "$OLD" = "$NEW" ]; then
  if [ "$FORCE" -eq 1 ]; then
    echo "gsync: remote already at HEAD; --force-restart: UIUX.Web compose + pattern-game web."
    NEED_UI=1
    NEED_PG=1
  else
    echo "gsync: remote already up to date (HEAD unchanged); nothing to restart."
    exit 0
  fi
else
  CHANGED=$(git diff --name-only "$OLD" "$NEW" || true)
  echo "gsync: pulled commits; changed files:"
  echo "$CHANGED" | sed 's/^/  /' || true
  if [ "$FORCE" -eq 1 ]; then
    echo "gsync: --force-restart: UIUX.Web compose + pattern-game web."
    NEED_UI=1
    NEED_PG=1
  else
    NEED_UI=0
    NEED_PG=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      case "$f" in
{ui_arms}
      esac
      case "$f" in
{pg_arms}
      esac
    done <<< "$CHANGED"
  fi
fi

if [ "${{NEED_UI:-0}}" -eq 0 ] && [ "${{NEED_PG:-0}}" -eq 0 ]; then
  echo "gsync: no monitored paths in changed files; skipping restarts."
  exit 0
fi

if [ "${{NEED_UI:-0}}" -eq 1 ]; then
  echo "gsync: restarting UIUX.Web (docker compose)…"
  cd UIUX.Web
  docker compose build web
  docker compose up -d
  docker compose restart api
  docker compose ps
  cd ..
fi

if [ "${{NEED_PG:-0}}" -eq 1 ]; then
  echo "gsync: restarting pattern-game web (Flask on 8765)…"
  bash scripts/pattern_game_remote_restart.sh "$HOME/{remote_dir_name}"
fi
"""


def _remote_pull_maybe_compose(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    ui_prefixes: list[str],
    pg_prefixes: list[str],
    force_restart: bool,
    dry_run: bool,
) -> None:
    body = _remote_script(
        remote_dir_name,
        pull_branch,
        ui_prefixes=ui_prefixes,
        pg_prefixes=pg_prefixes,
        force_restart=force_restart,
    )
    if dry_run:
        print("[dry-run] ssh would run on remote:\n---")
        print(body)
        print("---")
        return
    print(
        f"SSH {ssh_target}: git pull + conditional UIUX.Web / pattern-game restarts …",
        flush=True,
    )
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
        description="Commit (optional), push, remote pull, restart UIUX.Web and/or pattern-game web when paths match.",
    )
    ap.add_argument("-m", "--message", default=None, help="Commit message when auto-committing dirty tree")
    ap.add_argument("--no-commit", action="store_true", help="Do not commit; warn if dirty")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH if not --no-remote")
    ap.add_argument("--no-remote", action="store_true", help="Skip SSH (local commit + push only)")
    ap.add_argument(
        "--force-restart",
        action="store_true",
        help="Always run UIUX.Web compose + pattern-game web restart (even if pull is a no-op)",
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

    ui_prefixes = [p.strip() for p in DEFAULT_UI_PREFIXES.split(",") if p.strip()]
    if not ui_prefixes:
        ui_prefixes = ["UIUX.Web/"]
    pg_prefixes = [p.strip() for p in DEFAULT_PATTERN_GAME_PREFIXES.split(",") if p.strip()]
    if not pg_prefixes:
        pg_prefixes = ["renaissance_v4/game_theory/"]

    print(f"gsync: repo={repo} branch={branch}", flush=True)
    print(f"gsync: UIUX prefixes: {ui_prefixes!r}", flush=True)
    print(f"gsync: pattern-game prefixes: {pg_prefixes!r}", flush=True)
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
        ui_prefixes=ui_prefixes,
        pg_prefixes=pg_prefixes,
        force_restart=args.force_restart,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
