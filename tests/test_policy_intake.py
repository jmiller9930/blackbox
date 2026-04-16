"""Policy intake pipeline (DV-ARCH-KITCHEN-POLICY-INTAKE-048)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from renaissance_v4.policy_intake.pipeline import run_intake_pipeline


def test_intake_pipeline_ts_fixture() -> None:
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "minimal_direction_policy.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "minimal_direction_policy.ts", test_window_bars=400)
    assert rep.get("schema") == "policy_intake_report_v1"
    assert "submission_id" in rep
    assert rep.get("pass") is True, rep.get("errors")
