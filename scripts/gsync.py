#!/usr/bin/env python3
"""
gsync — git commit (optional), push to origin, pull on lab host, restart **only if needed**.

**Operator prompt — what this script is for (lab deploy loop)**

1. **Commit code locally** (when the working tree is dirty and you did not pass ``--no-commit``):
   default mode stages **tracked** changes only (``git add -u``). Untracked files are **not**
   committed unless you stage them first (``git add …``) or use ``--pattern-game`` (which runs
   ``git add`` on the pattern-game tree and listed scripts). To commit **everything** including
   untracked files in one shot, pass ``--add-all`` (runs ``git add -A``; review ``git status`` first).
2. **Push to origin, then update the remote clone** — ``git push`` your current branch, then SSH
   ``git pull`` on the lab host under ``~/BLACKBOX_REMOTE_HOME`` (default ``~/blackbox``). This is
   how code gets **onto** the server (push + remote pull, not “pull to remote” in the sense of
   pulling from the server to your laptop).
3. **Restart services on the lab host** when pulled commits touch monitored paths (or use
   ``--force-restart``): **UIUX.Web** docker (``web`` build, ``up -d``, ``api`` restart) and/or
   **pattern-game Flask** on port **8765** via ``scripts/pattern_game_remote_restart.sh``.
   ``--pattern-game``: always restarts Flask after pull; does **not** run UIUX docker.

If any step does not match what you need, use the flags below or ``scripts/sync.py`` for
unconditional UIUX.Web deploy.

Compared to ``scripts/sync.py`` (always rebuilds/restarts UIUX.Web on the remote), **gsync** runs:

- **UIUX.Web** ``docker compose`` when pulled commits touch paths under ``UIUX.Web/`` (or when
  ``--force-restart``).
- **Pattern-game Flask UI** (``python3 -m renaissance_v4.game_theory.web_app`` on port **8765**)
  when pulled commits touch ``renaissance_v4/game_theory/`` or other configured prefixes (or when
  ``--force-restart``). Remote helper: ``scripts/pattern_game_remote_restart.sh``.

**Single-command pattern-game deploy (recommended):** ``./scripts/deploy_pattern_game.sh`` or
``./scripts/sync_pattern_game.sh`` or ``python3 scripts/gsync.py --pattern-game``

That mode: runs ``git add`` on the ``renaissance_v4/game_theory`` tree (and a few script paths) so
new tracked **and** untracked files there are included — **remove or move scratch files** you do not
want committed before running. Then commits if needed, pushes your current branch, SSH ``git pull`` on the **same**
branch, and **always** restarts the Flask process so the live port matches disk. It does **not**
run UIUX.Web docker.

After a successful run, **verification is mandatory (exit non-zero on failure)** unless
``--no-verify``: (1) remote ``~/blackbox`` ``HEAD`` must equal ``origin/<branch>`` on this clone;
(2) ``curl`` to ``http://127.0.0.1:8765/`` on the lab host must return ``X-Pattern-Game-UI-Version``
(retries briefly so Flask can bind). Use ``--no-verify`` only for broken labs or debugging.

If the remote repo was **already up to date** (no new commits pulled), default gsync exits **unless**
``--force-restart`` is set — then it still runs the selected restarts so operators do not have to guess.

Process (default mode):
  1. If the working tree is dirty and ``--no-commit`` is not set: ``git add -u`` and commit
     (default message is timestamped; override with ``-m``). Untracked files are not staged unless
     you use ``--pattern-game`` (see above) or ``git add`` paths yourself.
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
                                    (default: renaissance_v4/game_theory/,scripts/agent_context_bundle.py,
                                    scripts/pattern_game_agent_reflect.py)

Usage (repo root):
  ./scripts/deploy_pattern_game.sh              # canonical name — full E2E + verify (same as below)
  ./scripts/sync_pattern_game.sh               # alias — same as --pattern-game
  python3 scripts/gsync.py --pattern-game       # commit+push+pull+restart+verify pattern-game (no UIUX docker)
  python3 scripts/gsync.py --pattern-game --no-verify   # skip HEAD/HTTP checks (emergency only)
  python3 scripts/gsync.py
  python3 scripts/gsync.py -m "describe change"
  python3 scripts/gsync.py --add-all -m "ship all local files including untracked"
  python3 scripts/gsync.py --dry-run
  python3 scripts/gsync.py --no-commit          # push + remote pull; no local commit
  python3 scripts/gsync.py --skip-push            # commit only; then remote pull + conditional restart
  python3 scripts/gsync.py --force-restart      # always run UIUX.Web compose after remote pull
  python3 scripts/gsync.py --no-remote          # commit + push only (no SSH)

For Jupiter/SeanV3 stack use ``scripts/jupsync.py``. For unconditional UIUX.Web deploy use
``scripts/sync.py``.

**Quick checklist**

| Step | Default ``gsync`` | ``--pattern-game`` |
|------|--------------------|--------------------|
| Local commit if dirty | ``git add -u`` + commit (or ``--add-all`` → ``git add -A``) | Stages game_theory + scripts, then commit |
| Push to ``origin`` | Yes (unless ``--skip-push``) | Yes |
| Remote ``git pull`` | Yes (unless ``--no-remote``) | Yes |
| Restart Flask (8765) | If paths match or ``--force-restart`` | **Always** after pull |
| Restart UIUX.Web docker | If ``UIUX.Web/`` changed or ``--force-restart`` | No |
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
        "renaissance_v4/game_theory/,scripts/agent_context_bundle.py,scripts/pattern_game_agent_reflect.py",
    )
    .strip()
    or "renaissance_v4/game_theory/"
)

# Staged before commit in --pattern-game mode so new files under game_theory are not skipped (git add -u alone does not add untracked files).
PATTERN_GAME_STAGING_PATHS = (
    "renaissance_v4/game_theory",
    "runtime",
    "scripts/pattern_game_remote_restart.sh",
    "scripts/pattern_game_agent_reflect.py",
    "scripts/agent_context_bundle.py",
    "scripts/openai_adapter_smoke_v1.sh",
    "scripts/gt_026b_lifecycle_trace_proof_v1.py",
    "scripts/sync_pattern_game.sh",
    "scripts/deploy_pattern_game.sh",
    "scripts/gsync.py",
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


def _stage_pattern_game_paths(repo: str, *, dry_run: bool) -> None:
    """``git add`` paths that include untracked files under game_theory (not covered by ``git add -u``)."""
    for rel in PATTERN_GAME_STAGING_PATHS:
        p = os.path.join(repo, rel)
        if not os.path.exists(p):
            continue
        if dry_run:
            print(f"[dry-run] git add {rel!r}", flush=True)
        else:
            subprocess.run(["git", "add", "--", rel], cwd=repo, check=False)


def _verify_remote_matches_pushed_branch(
    repo: str,
    branch: str,
    ssh_target: str,
    remote_dir_name: str,
    *,
    strict: bool,
) -> bool:
    """After SSH pull, confirm lab ``HEAD`` matches ``origin/<branch>`` on this clone."""
    try:
        _run(["git", "fetch", "origin"], cwd=repo)
        want = _run(["git", "rev-parse", f"origin/{branch}"], cwd=repo).stdout.strip()
    except subprocess.CalledProcessError as e:
        msg = f"gsync: could not verify (local fetch/rev-parse failed): {e}"
        if strict:
            print(msg, file=sys.stderr)
            return False
        print(msg, file=sys.stderr)
        return True
    try:
        got = _run(
            [
                "ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=30",
                ssh_target,
                f"cd ~/{remote_dir_name} && git rev-parse HEAD",
            ],
            cwd=repo,
        ).stdout.strip()
    except subprocess.CalledProcessError as e:
        msg = f"gsync: could not verify (ssh rev-parse failed): {e}"
        if strict:
            print(msg, file=sys.stderr)
            return False
        print(msg, file=sys.stderr)
        return True
    if want != got:
        print(
            f"gsync: {'FATAL' if strict else 'WARNING'}: remote ~/{remote_dir_name} HEAD {got[:12]}… != "
            f"your origin/{branch} {want[:12]}… (wrong branch on server, partial pull, or push did not run).",
            file=sys.stderr,
        )
        return False
    print(f"gsync: OK — remote HEAD matches origin/{branch} ({want[:12]}…).", flush=True)
    return True


def _verify_pattern_game_http_header(ssh_target: str, *, dry_run: bool) -> bool:
    """On the lab host, GET / on port 8765 and require ``X-Pattern-Game-UI-Version`` (Flask is up)."""
    if dry_run:
        print("[dry-run] would verify pattern-game HTTP header on remote :8765", flush=True)
        return True
    # Retry in remote shell: Flask may need a moment after nohup.
    remote_cmd = (
        "for i in 1 2 3 4 5 6 7 8; do "
        "if curl -sfI http://127.0.0.1:8765/ 2>/dev/null | grep -qi '^X-Pattern-Game-UI-Version:'; "
        "then exit 0; fi; sleep 1; done; exit 1"
    )
    try:
        r = subprocess.run(
            [
                "ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=30",
                ssh_target,
                remote_cmd,
            ],
            check=False,
        )
        if r.returncode == 0:
            print("gsync: OK — pattern-game Flask responds with X-Pattern-Game-UI-Version on :8765.", flush=True)
            return True
        print(
            "gsync: FATAL: pattern-game HTTP check failed (no X-Pattern-Game-UI-Version on http://127.0.0.1:8765/). "
            "Is Flask running? See runtime/logs/pattern_game_web.log under the repo (or $BLACKBOX_PML_RUNTIME_ROOT/logs/).",
            file=sys.stderr,
        )
        return False
    except OSError as e:
        print(f"gsync: FATAL: SSH HTTP check failed: {e}", file=sys.stderr)
        return False


def _auto_commit(
    repo: str,
    *,
    dry_run: bool,
    no_commit: bool,
    message: str | None,
    add_all: bool,
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
    add_cmd = "git add -A" if add_all else "git add -u"
    if dry_run:
        print(f"[dry-run] {add_cmd} && git commit -m {msg!r}")
        return
    print(
        f"Working tree dirty — staging ({add_cmd}) and committing …",
        flush=True,
    )
    subprocess.run(["git", "add", "-A"] if add_all else ["git", "add", "-u"], cwd=repo, check=True)
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


def _remote_script_pattern_game_only(remote_dir_name: str, pull_branch: str) -> str:
    """Pull on lab host and always restart pattern-game Flask (no docker / UIUX)."""
    return f"""set -eu
cd ~/{remote_dir_name}
git fetch origin
git pull origin {pull_branch}
echo "gsync: remote $(hostname -f 2>/dev/null || hostname) now at $(git rev-parse --short HEAD) — $(git log -1 --oneline)"
bash scripts/pattern_game_remote_restart.sh "$HOME/{remote_dir_name}"
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


def _remote_pull_pattern_game_only(
    ssh_target: str,
    remote_dir_name: str,
    pull_branch: str,
    *,
    dry_run: bool,
) -> None:
    body = _remote_script_pattern_game_only(remote_dir_name, pull_branch)
    if dry_run:
        print("[dry-run] ssh would run on remote (pattern-game only):\n---")
        print(body)
        print("---")
        return
    print(f"SSH {ssh_target}: git pull + pattern-game restart (always) …", flush=True)
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Lab deploy loop (this script):
  1) Commit locally if dirty (git add -u by default; --add-all uses git add -A; or use --pattern-game).
  2) git push origin <branch>, then SSH: git pull on ~/BLACKBOX_REMOTE_HOME (default ~/blackbox).
  3) Restart Flask pattern-game (8765) and/or UIUX.Web docker when changed files match prefixes,
     or pass --force-restart to always restart both.
  Pattern-game only:  ./scripts/deploy_pattern_game.sh  or  python3 scripts/gsync.py --pattern-game
  Full UIUX always:     python3 scripts/sync.py
""",
    )
    ap.add_argument("-m", "--message", default=None, help="Commit message when auto-committing dirty tree")
    ap.add_argument(
        "--add-all",
        action="store_true",
        help="When committing: run `git add -A` instead of `git add -u` (includes untracked files; review git status first).",
    )
    ap.add_argument("--no-commit", action="store_true", help="Do not commit; warn if dirty")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push; still SSH if not --no-remote")
    ap.add_argument("--no-remote", action="store_true", help="Skip SSH (local commit + push only)")
    ap.add_argument(
        "--force-restart",
        action="store_true",
        help="Always run UIUX.Web compose + pattern-game web restart (even if pull is a no-op)",
    )
    ap.add_argument(
        "--pattern-game",
        action="store_true",
        help="Pattern-game deploy loop: stage game_theory paths (incl. untracked), commit+push, "
        "remote pull, always restart Flask on 8765 — no UIUX docker. Requires local branch = "
        "--remote-branch (default main). After restart, verify remote HEAD vs origin and HTTP "
        "header (unless --no-verify).",
    )
    ap.add_argument(
        "--no-verify",
        action="store_true",
        help="With --pattern-game: skip remote HEAD vs origin check and Flask HTTP header check "
        "(use only when the lab is broken or for debugging).",
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

    if args.pattern_game:
        if branch != args.remote_branch:
            sys.stderr.write(
                f"gsync: --pattern-game: checkout {args.remote_branch!r} and merge your work, or pass "
                f"--remote-branch {branch!r} so pull matches what you push.\n",
            )
            sys.exit(1)
        if args.skip_push:
            sys.stderr.write("gsync: --pattern-game cannot be used with --skip-push.\n")
            sys.exit(1)
        if args.no_remote:
            sys.stderr.write("gsync: --pattern-game requires remote SSH (remove --no-remote).\n")
            sys.exit(1)
        if args.no_commit and _working_tree_dirty(repo):
            sys.stderr.write(
                "gsync: --pattern-game with --no-commit: you have local changes that are NOT on origin. "
                "Commit them first or run without --no-commit.\n",
            )
            sys.exit(1)
        _stage_pattern_game_paths(repo, dry_run=args.dry_run)

    _auto_commit(
        repo,
        dry_run=args.dry_run,
        no_commit=args.no_commit,
        message=args.message,
        add_all=args.add_all,
    )
    _sync_push(repo, branch, dry_run=args.dry_run, skip_push=args.skip_push)

    if args.no_remote:
        print("gsync: --no-remote set; skipping SSH.")
        return

    if args.pattern_game:
        _remote_pull_pattern_game_only(
            args.ssh,
            args.remote_dir,
            args.remote_branch,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(
                "[dry-run] would verify: remote HEAD == origin/%s and curl X-Pattern-Game-UI-Version on :8765"
                % (args.remote_branch,),
                flush=True,
            )
            return
        if args.no_verify:
            print("gsync: --no-verify: skipping remote HEAD and HTTP checks.", flush=True)
            return
        if not _verify_remote_matches_pushed_branch(
            repo, branch, args.ssh, args.remote_dir, strict=True
        ):
            sys.exit(1)
        if not _verify_pattern_game_http_header(args.ssh, dry_run=False):
            sys.exit(1)
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
