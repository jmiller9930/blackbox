"""E2E Step 3 — operator-visible API path for SR-2 / SR-3 / AC-2."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def test_verify_student_loop_step3_script(tmp_path: Path) -> None:
    repo = _repo()
    proof = tmp_path / "step3_proof_test.json"
    env = {
        **os.environ,
        "PYTHONPATH": str(repo),
        "PATTERN_GAME_NO_SESSION_LOG": "1",
    }
    r = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/verify_student_loop_step3_operator_path.py"),
            "--write-proof",
            str(proof),
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(proof.read_text(encoding="utf-8"))
    assert data.get("gates", {}).get("sr2_cross_run_difference") is True
    assert data.get("gates", {}).get("sr3_reset_matches_run_a") is True
    assert data.get("gates", {}).get("ac2_observability_keys") is True


def test_pattern_game_student_learning_store_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "custom_store.jsonl"
    monkeypatch.setenv("PATTERN_GAME_STUDENT_LEARNING_STORE", str(p))
    from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
        default_student_learning_store_path_v1,
    )

    assert default_student_learning_store_path_v1().resolve() == p.resolve()
