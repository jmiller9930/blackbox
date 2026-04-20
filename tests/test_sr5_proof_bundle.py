"""SR-5 atomic proof bundle builder (E2E Step 2) — integration smoke."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def test_build_student_loop_sr5_proof_bundle_exits_zero() -> None:
    repo = _repo()
    env = {**os.environ, "PYTHONPATH": str(repo), "PATTERN_GAME_NO_SESSION_LOG": "1"}
    r = subprocess.run(
        [sys.executable, str(repo / "scripts/build_student_loop_sr5_proof_bundle.py")],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    excerpt = repo / "runtime/student_loop_lab_proof_v1/sr5_atomic_proof_bundle/scorecard_excerpt.json"
    data = json.loads(excerpt.read_text(encoding="utf-8"))
    gates = data.get("gates") or {}
    assert gates.get("sr2_cross_run_difference") is True
    assert gates.get("sr3_reset_matches_run_a") is True
