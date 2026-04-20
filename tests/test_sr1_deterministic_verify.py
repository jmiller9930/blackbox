"""SR-1 — deterministic closed trades (E2E v2.1); see runtime/student_loop_lab_proof_v1/README.md."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_verify_student_loop_sr1_script_exits_zero() -> None:
    """One command, no manual DB/window changes — must produce ≥1 replay outcome."""
    repo = _repo_root()
    env = {**os.environ, "PYTHONPATH": str(repo)}
    r = subprocess.run(
        [sys.executable, str(repo / "scripts/verify_student_loop_sr1.py")],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
