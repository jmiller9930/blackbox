"""Full math stack (optional heavy deps)."""
from __future__ import annotations

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("arch")
pytest.importorskip("sklearn")

from modules.anna_training.math_engine_full.cointegration_kalman import engle_granger_coint, kalman_local_level
from modules.anna_training.math_engine_full.stack import run_full_math_stack


def test_kalman_runs() -> None:
    y = [1.0, 0.5, 2.0, 1.2, 0.8]
    o = kalman_local_level(y)
    assert o.get("ok") is True
    assert "level_last" in o


def test_coint_runs_on_random_walks() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    a = np.cumsum(rng.standard_normal(80))
    b = np.cumsum(rng.standard_normal(80)) + 0.1 * a
    o = engle_granger_coint(a, b)
    assert o.get("ok") is True
    assert "pvalue" in o


def test_run_full_math_stack_empty() -> None:
    r = run_full_math_stack([])
    assert r.get("version") == "1"
    assert "sections" in r


def test_run_full_math_stack_synthetic_trades() -> None:
    # Enough distinct days for daily aggregation + ARIMA/GARCH paths; keep modest for CI speed.
    trades = [
        {
            "schema": "anna_paper_trade_v1",
            "ts_utc": f"2026-01-{i+1:02d}T12:00:00Z",
            "pnl_usd": float((-1) ** i) * 5.0,
            "result": "won" if i % 2 == 0 else "lost",
        }
        for i in range(40)
    ]
    r = run_full_math_stack(trades)
    sec = r.get("sections") or {}
    assert sec.get("trade_count") == 40
    assert "monte_carlo_bootstrap" in sec
    assert "annualized_risk" in sec or "daily" in sec
