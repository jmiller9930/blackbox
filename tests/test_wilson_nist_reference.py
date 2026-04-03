"""Wilson NIST-style reference: float implementation vs Decimal oracle."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "runtime"))

from anna_modules.analysis_math import wilson_score_interval_95  # noqa: E402
from modules.anna_training.wilson_nist_reference import (  # noqa: E402
    run_wilson_reference_check,
    wilson_score_interval_95_decimal,
)


def test_decimal_oracle_matches_float() -> None:
    out = run_wilson_reference_check(wilson_float=wilson_score_interval_95)
    assert out["ok"] is True
    assert out["cases_total"] == out["cases_passed"]
    assert out["failures"] == []


def test_wilson_decimal_edge_n0() -> None:
    lo, hi = wilson_score_interval_95_decimal(0, 0)
    assert lo == 0 and hi == 1
