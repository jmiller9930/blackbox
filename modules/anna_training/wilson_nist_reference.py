"""
NIST-style reference check for Wilson score 95% intervals (binomial proportion).

The **float** implementation lives in ``anna_modules.analysis_math.wilson_score_interval_95``.
This module holds a **Decimal** (high-precision) Wilson formula as an independent oracle.
Training / school can run :func:`run_wilson_reference_check` before sessions to catch regressions.
"""
from __future__ import annotations

import math
from decimal import Decimal, getcontext
from typing import Any, Callable

# Enough precision that float64 comparison is stable vs Decimal→float.
getcontext().prec = 80

_Z95 = Decimal("1.96")


def wilson_score_interval_95_decimal(wins: int, n: int) -> tuple[Decimal, Decimal]:
    """Wilson score interval (95% nominal), high-precision reference."""
    if n <= 0:
        return Decimal(0), Decimal(1)
    z = _Z95
    z2 = z * z
    p = Decimal(wins) / Decimal(n)
    denom = Decimal(1) + z2 / Decimal(n)
    center = (p + z2 / (Decimal(2) * Decimal(n))) / denom
    inner = (p * (Decimal(1) - p) + z2 / (Decimal(4) * Decimal(n))) / Decimal(n)
    margin = (z / denom) * inner.sqrt()
    lo = max(Decimal(0), center - margin)
    hi = min(Decimal(1), center + margin)
    return lo, hi


# Certified-style cases: (case_id, wins, n) — edges, small n, moderate n, large n.
WILSON_NIST_CASES: tuple[tuple[str, int, int], ...] = (
    ("edge_n0", 0, 0),
    ("w0_n1", 0, 1),
    ("w1_n1", 1, 1),
    ("w0_n5", 0, 5),
    ("w5_n5", 5, 5),
    ("w3_n10", 3, 10),
    ("w0_n30", 0, 30),
    ("w15_n30", 15, 30),
    ("w17_n42", 17, 42),
    ("w1_n100", 1, 100),
    ("w50_n100", 50, 100),
    ("w0_n100", 0, 100),
    ("w500_n1000", 500, 1000),
)


def _float_matches_decimal(a: float, b_dec: Decimal) -> bool:
    """Compare float result to Decimal oracle (handles float underflow to 0)."""
    b = float(b_dec)
    if not math.isfinite(a) or not math.isfinite(b):
        return a == b
    diff = abs(a - b)
    scale = max(abs(a), abs(b), 1e-300)
    return diff <= max(1e-15, 1e-12 * scale)


def run_wilson_reference_check(
    wilson_float: Callable[[int, int], tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """
    Run all NIST-style Wilson cases: float implementation vs Decimal oracle.

    Returns JSON-serializable dict: ok, engine, cases_total, cases_passed, failures.
    """
    if wilson_float is None:
        wilson_float = _load_wilson_float()

    failures: list[dict[str, Any]] = []
    for cid, w, n in WILSON_NIST_CASES:
        lo_d, hi_d = wilson_score_interval_95_decimal(w, n)
        lo_f, hi_f = wilson_float(w, n)
        ok_lo = _float_matches_decimal(lo_f, lo_d)
        ok_hi = _float_matches_decimal(hi_f, hi_d)
        if not (ok_lo and ok_hi):
            failures.append(
                {
                    "case_id": cid,
                    "wins": w,
                    "n": n,
                    "expected_lo": float(lo_d),
                    "expected_hi": float(hi_d),
                    "got_lo": lo_f,
                    "got_hi": hi_f,
                }
            )

    passed = len(WILSON_NIST_CASES) - len(failures)
    return {
        "ok": len(failures) == 0,
        "engine": "wilson_score_95_float_vs_decimal",
        "cases_total": len(WILSON_NIST_CASES),
        "cases_passed": passed,
        "failures": failures,
    }


def _load_wilson_float() -> Callable[[int, int], tuple[float, float]]:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    rt = root / "scripts" / "runtime"
    for p in (str(root), str(rt)):
        if p not in sys.path:
            sys.path.insert(0, p)
    from anna_modules.analysis_math import wilson_score_interval_95

    return wilson_score_interval_95
