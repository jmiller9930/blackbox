"""DV-ARCH-KITCHEN-SIGNAL-CONTRACT-065 — harness signal shape + API/browser parity (same pipeline)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from renaissance_v4.policy_intake.pipeline import run_intake_pipeline


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_normalize_accepts_alias_long_short() -> None:
    root = Path(__file__).resolve().parents[1]
    code = """
import { normalizeIntakeSignalOutput } from './renaissance_v4/policy_intake/intake_signal_normalize.mjs';
const a = normalizeIntakeSignalOutput({ long: true, short: false, signalPrice: 1 });
const b = normalizeIntakeSignalOutput({ longSignal: true, shortSignal: false, signalPrice: 1 });
if (!a.longSignal || a.shortSignal || !b.longSignal) process.exit(1);
process.exit(0);
"""
    r = subprocess.run(
        ["node", "--input-type=module", "-e", code],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 0, r.stderr + r.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_fixture_minimal_passes_with_signal_contract_in_report() -> None:
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "minimal_direction_policy.ts"
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "minimal_direction_policy.ts", test_window_bars=400)
    assert rep.get("pass") is True, rep.get("errors")
    det = (rep.get("stages") or {}).get("stage_5_deterministic") or {}
    assert det.get("harness_revision") == "int_ohlc_v4"
    sc = det.get("signal_contract") or {}
    assert sc.get("schema") == "kitchen_intake_signal_v1"
    assert sc.get("export_name") == "generateSignalFromOhlc"
    assert sc.get("content_sha256")
    assert len(sc.get("first_five_bar_returns") or []) == 5
    assert len(sc.get("last_five_bar_returns") or []) == 5
    vi = sc.get("viability_inputs") or {}
    assert int(vi.get("signals_total") or 0) > 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_alias_only_fixture_passes() -> None:
    """Policy using only long/short aliases (no longSignal keys) must count signals (DV-065)."""
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "alias_only_signal_policy.ts"
    if not fix.is_file():
        pytest.skip("fixture missing")
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "alias_only_signal_policy.ts", test_window_bars=400)
    assert rep.get("pass") is True, rep.get("errors")
    det = (rep.get("stages") or {}).get("stage_5_deterministic") or {}
    first = (det.get("signal_contract") or {}).get("first_five_bar_returns") or []
    assert first, "expected signal_contract probes"
    assert any((x.get("normalized") or {}).get("source") == "alias_long_short" for x in first)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_stage1_sha_matches_bytes() -> None:
    root = Path(__file__).resolve().parents[1]
    fix = root / "tests" / "fixtures" / "policy_intake" / "minimal_direction_policy.ts"
    import hashlib

    h = hashlib.sha256(fix.read_bytes()).hexdigest()
    raw = fix.read_bytes()
    rep = run_intake_pipeline(root, raw, "minimal_direction_policy.ts", test_window_bars=120)
    st1 = (rep.get("stages") or {}).get("stage_1_intake") or {}
    assert st1.get("content_sha256") == h
    det = (rep.get("stages") or {}).get("stage_5_deterministic") or {}
    assert det.get("signal_contract", {}).get("content_sha256") == h
