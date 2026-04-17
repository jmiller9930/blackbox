#!/usr/bin/env python3
"""
Quant lab sync — run ``rensync.py`` (UIUX.Web / dashboard on clawbot) then ``jupsync.py`` (SeanV3 + Jupiter).

Equivalent to:

  python3 scripts/rensync.py [shared + rensync flags]
  python3 scripts/jupsync.py [shared + jupsync flags]

If the first step exits non-zero, the second does not run.

Environment defaults match ``rensync`` / ``jupsync`` (``BLACKBOX_SYNC_SSH``, ``BLACKBOX_REMOTE_HOME``, etc.).

Usage (from repo root):

  python3 scripts/quant.py
  python3 scripts/quant.py --dry-run
  python3 scripts/quant.py --rensync-only --api-only
  python3 scripts/quant.py --jupsync-only --no-commit
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent

_DEFAULT_SSH = os.environ.get("RENSYNC_SSH") or os.environ.get("BLACKBOX_SYNC_SSH", "jmiller@clawbot.a51.corp")
_DEFAULT_REMOTE_DIR = os.environ.get("BLACKBOX_REMOTE_HOME", "blackbox")
_DEFAULT_REMOTE_BRANCH = os.environ.get("RENSYNC_BRANCH") or os.environ.get("BLACKBOX_REMOTE_BRANCH", "main")


def _shared_args(ns: argparse.Namespace) -> list[str]:
    out = [
        "--ssh",
        ns.ssh,
        "--remote-dir",
        ns.remote_dir,
        "--remote-branch",
        ns.remote_branch,
    ]
    if ns.dry_run:
        out.append("--dry-run")
    if ns.skip_push:
        out.append("--skip-push")
    return out


def _rensync_argv(ns: argparse.Namespace) -> list[str]:
    cmd = _shared_args(ns)
    if ns.git_only:
        cmd.append("--git-only")
    if ns.api_only:
        cmd.append("--api-only")
    if ns.rebuild_web:
        cmd.append("--rebuild-web")
    return cmd


def _jupsync_argv(ns: argparse.Namespace) -> list[str]:
    cmd = _shared_args(ns)
    if ns.no_commit:
        cmd.append("--no-commit")
    if ns.commit_message:
        cmd.extend(["-m", ns.commit_message])
    if ns.skip_health:
        cmd.append("--skip-health")
    if ns.full_stack:
        cmd.append("--full-stack")
    return cmd


def _run_script(name: str, argv: list[str]) -> None:
    path = _SCRIPTS / name
    cmd = [sys.executable, str(path), *argv]
    print(f"\n>>> quant: {name}\n", flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run rensync (UIUX.Web on clawbot) then jupsync (SeanV3/Jupiter).",
    )
    ap.add_argument("--ssh", default=_DEFAULT_SSH, help=f"SSH user@host (default: {_DEFAULT_SSH})")
    ap.add_argument(
        "--remote-dir",
        default=_DEFAULT_REMOTE_DIR,
        help=f"Directory under remote home (default: {_DEFAULT_REMOTE_DIR})",
    )
    ap.add_argument("--remote-branch", default=_DEFAULT_REMOTE_BRANCH, help="Branch to pull on remote")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only (passed to both)")
    ap.add_argument("--skip-push", action="store_true", help="Skip git push (passed to both)")

    mx = ap.add_mutually_exclusive_group()
    mx.add_argument(
        "--rensync-only",
        action="store_true",
        help="Only run scripts/rensync.py",
    )
    mx.add_argument(
        "--jupsync-only",
        action="store_true",
        help="Only run scripts/jupsync.py",
    )

    rg = ap.add_argument_group("rensync (UIUX.Web docker on clawbot)")
    rg.add_argument(
        "--git-only",
        action="store_true",
        help="Remote git pull only; no docker (rensync)",
    )
    rg.add_argument(
        "--api-only",
        action="store_true",
        help="Faster rensync: api up + restart only, no full web build",
    )
    rg.add_argument(
        "--rebuild-web",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    jg = ap.add_argument_group("jupsync (vscode-test/seanv3 docker on clawbot)")
    jg.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not auto-commit dirty tree before push (jupsync)",
    )
    jg.add_argument(
        "-m",
        "--commit-message",
        default=None,
        metavar="MSG",
        help="Auto-commit message when dirty (jupsync)",
    )
    jg.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip Jupiter /health check after deploy (jupsync)",
    )
    jg.add_argument(
        "--full-stack",
        action="store_true",
        help="After SeanV3 compose, also rebuild UIUX.Web (jupsync)",
    )

    args = ap.parse_args()

    if args.git_only and args.api_only:
        sys.stderr.write("quant.py: use only one of --git-only or --api-only.\n")
        sys.exit(2)
    if args.rebuild_web:
        print(
            "quant.py: note: --rebuild-web is obsolete in rensync; full rebuild is the default.",
            file=sys.stderr,
        )

    if args.jupsync_only:
        _run_script("jupsync.py", _jupsync_argv(args))
        return
    if args.rensync_only:
        _run_script("rensync.py", _rensync_argv(args))
        return

    _run_script("rensync.py", _rensync_argv(args))
    _run_script("jupsync.py", _jupsync_argv(args))


if __name__ == "__main__":
    main()
