#!/usr/bin/env python3
"""GT066 — run offline parallel-batch terminal proof (pytest harness). Exit non-zero on failure."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="GT066 offline batch terminal proof harness.")
    ap.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="pytest quiet mode",
    )
    args = ap.parse_args()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "renaissance_v4/game_theory/tests/test_gt066_offline_parallel_batch_terminal_proof_v1.py",
    ]
    if args.quiet:
        cmd.append("-q")
    cmd.extend(["--tb=short"])
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    py_path = str(root)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = py_path if not prev else f"{py_path}:{prev}"
    return subprocess.call(cmd, cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
