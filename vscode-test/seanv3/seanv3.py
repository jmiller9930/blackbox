#!/usr/bin/env python3
"""
SeanV3 — single entry point (Docker + operator TUI + report + tests).

  python3 seanv3.py deploy --pull    # container (delegates to seanv3py)
  python3 seanv3.py tui              # operator TUI (preflight + policy + Hermes + Sean ledger)
  python3 seanv3.py tui --menu
  python3 seanv3.py report           # paper P&L summary from capture/sean_parity.db
  python3 seanv3.py test             # npm test (policy + engine smoke)

All docker commands (status, logs, console, preflight, stop, …) pass through to ./seanv3py.

Environment:
  BLACKBOX_REPO / repo auto: parent of vscode-test/seanv3
  SEANV3_SQLITE_PATH — optional; default set for tui to vscode-test/seanv3/capture/sean_parity.db
"""
from __future__ import annotations

import os
import subprocess
import sys


def _here() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _repo_root() -> str:
    return os.path.normpath(os.path.join(_here(), "..", ".."))


def _usage() -> None:
    print(
        """Usage: python3 seanv3.py <command> [options]

SeanV3-native (this file):
  tui [args...]     Operator TUI — same as preflight_pyth_tui.py (--menu, --policy, etc.)
  report [args...]  Paper trade JSON summary (node report.mjs)
  test              Run unit tests (npm test)

Docker / host (delegates to ./seanv3py):
  deploy [--pull]   Build + up -d
  status            docker compose ps
  logs              docker compose logs -f
  console           tmux + logs -f
  stop              docker compose down
  restart [--pull]  down + build + up
  pull              git pull origin main (repo root)
  preflight [--require-container]

Examples:
  python3 seanv3.py deploy --pull
  python3 seanv3.py preflight --require-container
  python3 seanv3.py tui
  python3 seanv3.py report --db ./capture/sean_parity.db

Environment:
  BLACKBOX_REPO       Git / paths (seanv3py)
  SEANV3_SQLITE_PATH  Override SQLite for TUI ledger panel
"""
    )


def _run_tui(extra: list[str]) -> None:
    rr = _repo_root()
    tui = os.path.join(rr, "scripts", "operator", "preflight_pyth_tui.py")
    if not os.path.isfile(tui):
        print(f"Missing {tui}", file=sys.stderr)
        sys.exit(1)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(rr, "scripts", "runtime")
    db_default = os.path.join(rr, "vscode-test", "seanv3", "capture", "sean_parity.db")
    env.setdefault("SEANV3_SQLITE_PATH", db_default)
    os.chdir(rr)
    os.execvpe(sys.executable, [sys.executable, tui, *extra], env)


def _run_report(extra: list[str]) -> None:
    sean = _here()
    report_js = os.path.join(sean, "report.mjs")
    if not os.path.isfile(report_js):
        print(f"Missing {report_js}", file=sys.stderr)
        sys.exit(1)
    cmd = ["node", "--experimental-sqlite", report_js, *extra]
    raise SystemExit(subprocess.call(cmd, cwd=sean))


def _run_test() -> None:
    sean = _here()
    raise SystemExit(subprocess.call(["npm", "test"], cwd=sean))


def main() -> None:
    here = _here()
    sh = os.path.join(here, "seanv3py")
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        _usage()
        sys.exit(0)

    if argv[0] == "tui":
        _run_tui(argv[1:])
        return
    if argv[0] == "report":
        _run_report(argv[1:])
        return
    if argv[0] == "test":
        _run_test()
        return

    if not os.path.isfile(sh):
        print("seanv3py not found next to seanv3.py", file=sys.stderr)
        sys.exit(1)
    os.execv(sh, [sh, *argv])


if __name__ == "__main__":
    main()
