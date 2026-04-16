"""Policy intake pipeline (DV-ARCH-KITCHEN-POLICY-INTAKE-048)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from renaissance_v4.policy_intake import pipeline as policy_pipeline
from renaissance_v4.policy_intake.pipeline import run_intake_pipeline


def test_parse_harness_stdout_prefers_json_line() -> None:
    """DV-060: tolerate extra stdout lines before the harness JSON on some hosts."""
    stdout = "(node:1) ExperimentalWarning: …\n{\"ok\": true, \"signals_total\": 3, \"harness_revision\": \"int_ohlc_v4\"}\n"
    got = policy_pipeline._parse_harness_stdout(stdout)
    assert got.get("ok") is True
    assert got.get("signals_total") == 3


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


def test_intake_pipeline_fixture_minimal_direction_policy_ts() -> None:
    """Named upload fixture (browser filename) — must use OHLC-array harness signature, not PolicyInput.candles."""
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "fixture_minimal_direction_policy.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "fixture_minimal_direction_policy.ts", test_window_bars=400)
    assert rep.get("schema") == "policy_intake_report_v1"
    assert rep.get("pass") is True, rep.get("errors")
    assert rep.get("candidate_policy_id") == "fixture_minimal_direction_v1"


def test_intake_pipeline_kitchen_mechanical_always_long_ts() -> None:
    """DV-067 mechanical proof policy (parity with SeanV3 jup_kitchen_mechanical_v1)."""
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "kitchen_mechanical_always_long.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "kitchen_mechanical_always_long.ts", test_window_bars=400)
    assert rep.get("pass") is True, rep.get("errors")
    assert rep.get("candidate_policy_id") == "kitchen_mechanical_always_long_v1"
