"""Deterministic baseline lifecycle proof harness (real bridge + temp DBs)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_deterministic_lifecycle_harness_end_to_end(tmp_path: Path) -> None:
    """Runs scripts/ops/baseline_lifecycle_deterministic_harness.py; asserts pass criteria."""
    script = ROOT / "scripts" / "ops" / "baseline_lifecycle_deterministic_harness.py"
    env = {**os.environ, "BASELINE_HARNESS_TMP": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, str(script)],
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
    assert abs(float(out.get("size") or 0) - 1.0) > 1e-6
    held = out.get("held_duration_minutes")
    assert held is not None and float(held) > 5.0
    pop = out.get("position_open_payload") or {}
    assert pop.get("virtual_sl") is not None
    assert pop.get("virtual_tp") is not None
    assert pop.get("size_source") == "notional_usd_div_entry_price"
