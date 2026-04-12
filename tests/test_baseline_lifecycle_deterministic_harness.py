"""Deterministic baseline lifecycle proof harness (real bridge + temp DBs)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "trading" / "scripts" / "trade_harness" / "baseline_lifecycle_deterministic_harness.py"


def test_deterministic_lifecycle_harness_end_to_end(tmp_path: Path) -> None:
    """Runs trading/scripts/trade_harness/baseline_lifecycle_deterministic_harness.py."""
    env = {**os.environ, "BASELINE_HARNESS_TMP": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    out = json.loads(r.stdout)
    assert str(out.get("trade_id") or "").startswith("bl_lc_")
    assert out.get("exit_reason") == "STOP_LOSS"
    assert float(out.get("held_duration_minutes") or 0) >= 12.0
    assert out.get("pnl_sanity_check") == "pass"
    assert abs(float(out.get("size_delta") or 0)) < 1e-6
    pop = out.get("position_open_payload") or {}
    assert pop.get("virtual_sl") is not None
    assert pop.get("virtual_tp") is not None
    assert pop.get("size_source") == "notional_usd_div_entry_price"
    cs = out.get("capital_scaling") or {}
    assert cs.get("size_match_ok") is True
    exp_sz = float(cs.get("expected_size") or 0)
    if abs(exp_sz - 1.0) > 1e-8:
        assert abs(float(out.get("actual_size") or 0) - 1.0) > 1e-6
