"""Policy intake pipeline (DV-ARCH-KITCHEN-POLICY-INTAKE-048)."""

from __future__ import annotations

import shutil
import subprocess
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


def test_intake_pipeline_generated_from_operator_input() -> None:
    """OPERATOR_INPUT in generate_policy.mjs → kitchen_policy_generated.ts (single source workflow)."""
    root = Path(__file__).resolve().parents[1]
    gen_script = root / "renaissance_v4" / "policy_intake" / "generate_policy.mjs"
    fix = root / "renaissance_v4" / "policy_intake" / "kitchen_policy_generated.ts"
    if not gen_script.is_file():
        pytest.skip("generate_policy.mjs missing")
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    override = root / "tests" / "fixtures" / "policy_intake" / "generate_policy_ci_override.json"
    subprocess.run(
        ["node", str(gen_script), str(override.relative_to(root))],
        cwd=str(root),
        check=True,
        timeout=120,
    )
    if not fix.is_file():
        pytest.skip("kitchen_policy_generated.ts missing after generate")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "kitchen_policy_generated.ts", test_window_bars=800)
    assert rep.get("pass") is True, rep.get("errors")
    assert rep.get("candidate_policy_id") == "kitchen_import_template_v1"
    st = rep.get("stages") or {}
    assert (st.get("stage_6_viability") or {}).get("ok") is True


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
