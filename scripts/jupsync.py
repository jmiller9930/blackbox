#!/usr/bin/env python3
"""
Jupiter / SeanV3 lab sync — push local git to origin, pull on clawbot, rebuild & restart
``vscode-test/seanv3`` (``seanv3`` + ``jupiter-web``).

Process (operator):
  1. Run ``python3 scripts/jupsync.py`` from repo root (Mac or any machine with git + ssh).
  2. By default, if the working tree is dirty, the script stages **tracked** changes (``git add -u``)
     and **commits** with an auto message (override with ``-m``). Untracked files are **not** auto-added;
     run ``git add <paths>`` first for new files. Use ``--no-commit`` to skip.
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
  python3 scripts/jupsync.py --no-commit          # push/deploy only; do not auto-commit local changes
  python3 scripts/jupsync.py -m "fix login knockout"   # custom auto-commit message when dirty
  python3 scripts/jupsync.py --skip-push          # remote pull + compose only
  python3 scripts/jupsync.py --skip-health        # do not verify jupiter /health after deploy
  python3 scripts/jupsync.py --full-stack         # also rebuild/restart UIUX.Web (dashboard nginx/api)
  python3 scripts/jupsync.py --jupiter-https      # also compose jupiter-https (Caddy on :8443 → :707)

Reachability (important):
  Post-deploy health uses **the same URL operators use in a browser**, not loopback. The remote script
  (run over **SSH on the lab host**) curls ``JUPSYNC_JUPITER_HEALTH_URL`` (default
  ``http://jupv3.greyllc.net:737/health`` — WAN :737 → host :707). Override with e.g.
  ``http://clawbot.a51.corp:707/health`` if you only verify from VPN/LAN.
  For plain **http** :707 use an **http** health URL. If you use the Jupiter-only HTTPS sidecar
  (``docker-compose.jupiter-https.yml``, host **:8443**), set e.g.
  ``JUPSYNC_JUPITER_HEALTH_URL=https://clawbot.a51.corp:8443/health`` — the script uses ``curl -k``
  for **https** URLs (self-signed Caddy ``tls internal``).

Health verification runs **on the remote** after ``docker compose`` (retries with backoff). If it fails,
the script exits **non-zero** and prints ``jupiter-web`` logs — unlike older versions that always exited 0.
Optional env: ``JUPSYNC_HEALTH_ATTEMPTS`` (default 25), ``JUPSYNC_HEALTH_SLEEP_SEC`` (default 2),
``JUPSYNC_JUPITER_HEALTH_URL`` (full URL to ``/health``, default ``http://jupv3.greyllc.net:737/health``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from shlex import quote as sh_quote


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


def _working_tree_dirty(repo: str) -> bool:
    return bool(_run(["git", "status", "--porcelain"], cwd=repo).stdout.strip())


def _auto_commit(
    repo: str,
    *,
    dry_run: bool,
    no_commit: bool,
    message: str | None,
) -> None:
    """If the repo has uncommitted changes, stage all and commit so push can reach the remote."""
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
    default_msg = f"jupsync auto-commit {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    msg = (message or default_msg).strip() or default_msg
    if dry_run:
        print(f"[dry-run] git add -u && git commit -m {msg!r}")
        return
    print("Working tree dirty — staging tracked changes (git add -u) and committing …", flush=True)
    subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo)
    if staged.returncode == 0:
        print("Nothing left to commit after staging (ignored-only changes?).", file=sys.stderr)
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
            "--skip-push set, skipping."
        )
        return
    if dry_run:
        print(f"[dry-run] git push origin {branch}")
        return
    print(f"Pushing {branch} to origin …")
    subprocess.run(["git", "push", "origin", branch], cwd=repo, check=True)
    print("Push OK.")


def _jupiter_health_url() -> str:
    """Full URL for GET /health — lab hostname by default (same as operator browser), not 127.0.0.1."""
    u = (os.environ.get("JUPSYNC_JUPITER_HEALTH_URL") or os.environ.get("JUPITER_HEALTH_URL") or "").strip()
    if u:
        return u
    return "http://jupv3.greyllc.net:737/health"


def _bash_jupiter_health(
    remote_dir_name: str, health_url: str, *, jupiter_https: bool
) -> str:
    """Bash fragment: retry GET health_url; exit 1 if never OK (runs on remote over SSH)."""
    attempts = os.environ.get("JUPSYNC_HEALTH_ATTEMPTS", "25").strip() or "25"
    sleep_s = os.environ.get("JUPSYNC_HEALTH_SLEEP_SEC", "2").strip() or "2"
    uq = sh_quote(health_url)
    # Self-signed Jupiter HTTPS sidecar (Caddy tls internal) needs curl -k
    curl_flags = "-kSf" if health_url.strip().lower().startswith("https://") else "-sf"
    curl_show = "curl -kS" if health_url.strip().lower().startswith("https://") else "curl -sS"
    if jupiter_https:
        diag = f"""
  cd ~/{remote_dir_name}/vscode-test/seanv3
  docker compose -f docker-compose.yml -f docker-compose.jupiter-https.yml ps -a >&2 || true
  docker compose -f docker-compose.yml -f docker-compose.jupiter-https.yml logs --tail 50 jupiter-web >&2 || true
  docker compose -f docker-compose.yml -f docker-compose.jupiter-https.yml logs --tail 30 jupiter-https >&2 || true"""
    else:
        diag = f"""
  cd ~/{remote_dir_name}/vscode-test/seanv3
  docker compose ps -a >&2 || true
  docker compose logs --tail 50 jupiter-web >&2 || true"""
    return f"""
echo "--- jupiter /health (retry until OK or fail) ---"
echo "  URL: {health_url}"
_ok=0
for _i in $(seq 1 {attempts}); do
  if curl {curl_flags} --connect-timeout 3 {uq} 2>/dev/null | grep -q '"ok"'; then
    echo "jupiter-web health OK (attempt $_i)"
    {curl_show} --connect-timeout 5 {uq}
    echo ""
    _ok=1
    break
  fi
  echo "  waiting for jupiter-web (attempt $_i/{attempts}) …"
  sleep {sleep_s}
done
if [ "$_ok" -ne 1 ]; then
  echo "jupsync: ERROR — {health_url} never became healthy." >&2
{diag}
  exit 1
fi
"""


def _remote_script(
    remote_dir_name: str,
    pull_branch: str,
    *,
    health_check: bool,
    full_stack: bool,
    health_url: str,
    jupiter_https: bool,
) -> str:
    health = (
        _bash_jupiter_health(remote_dir_name, health_url, jupiter_https=jupiter_https)
        if health_check
        else ""
    )

    ui_block = ""
    if full_stack:
        ui_block = f"""
echo "--- UIUX.Web (operator dashboard) ---"
cd ~/{remote_dir_name}/UIUX.Web
docker compose build web
docker compose up -d
docker compose restart api
docker compose ps
"""

    compose = "docker compose up -d --build"
    compose_ps = "docker compose ps"
    if jupiter_https:
        compose = (
            "docker compose -f docker-compose.yml -f docker-compose.jupiter-https.yml up -d --build"
        )
        compose_ps = "docker compose -f docker-compose.yml -f docker-compose.jupiter-https.yml ps"

    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "REMOTE_HEAD=$(git rev-parse HEAD)"
echo "--- SeanV3 + jupiter-web (vscode-test/seanv3) ---"
cd vscode-test/seanv3
{compose}
{compose_ps}
{ui_block}
{health}
"""


def _remote_jupsync(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
    health_check: bool,
    full_stack: bool,
    jupiter_https: bool,
) -> None:
    body = _remote_script(
        remote_dir_name,
        pull_branch,
        health_check=health_check,
        full_stack=full_stack,
        health_url=_jupiter_health_url(),
        jupiter_https=jupiter_https,
    )
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
    ap.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not run git add/commit when the working tree is dirty (default is to auto-commit)",
    )
    ap.add_argument(
        "-m",
        "--commit-message",
        default=None,
        metavar="MSG",
        help="Message for auto-commit when dirty (default: timestamped jupsync auto-commit)",
    )
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH pull + compose")
    ap.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip post-deploy Jupiter health verification on remote (not recommended)",
    )
    ap.add_argument(
        "--full-stack",
        action="store_true",
        help="After SeanV3 compose, also build web + up + restart api in UIUX.Web (one SSH session)",
    )
    ap.add_argument(
        "--jupiter-https",
        action="store_true",
        help="Use SeanV3 compose with docker-compose.jupiter-https.yml (Caddy TLS on host :8443 → :707); "
        "does not change UIUX.Web. Set JUPSYNC_JUPITER_HEALTH_URL to https://…:8443/health if health checks use HTTPS.",
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

    _auto_commit(repo, dry_run=args.dry_run, no_commit=args.no_commit, message=args.commit_message)
    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)
    _remote_jupsync(
        args.ssh,
        args.remote_dir,
        args.remote_branch,
        dry_run=args.dry_run,
        health_check=not args.skip_health,
        full_stack=args.full_stack,
        jupiter_https=args.jupiter_https,
    )


if __name__ == "__main__":
    main()
