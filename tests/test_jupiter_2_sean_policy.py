"""Jupiter_2 Sean policy v1.0 — entry + sizing (paper)."""

from __future__ import annotations

import math

import pytest

from modules.anna_training.jupiter_2_sean_policy import (
    MIN_BARS,
    calculate_position_size,
    evaluate_jupiter_2_sean,
    generate_signal_from_ohlc,
)


def _synthetic_bars(n: int, *, seed: float = 100.0) -> list[dict]:
    """Monotonic-ish OHLC for indicator stability."""
    out: list[dict] = []
    p = seed
    for i in range(n):
        o = p
        p = p + 0.01 * (1 if i % 7 != 0 else -1)
        h = max(o, p) + 0.02
        l = min(o, p) - 0.02
        c = p
        out.append(
            {
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "candle_open_utc": f"2026-01-01T{(i * 5) // 60:02d}:{(i * 5) % 60:02d}:00Z",
            }
        )
    return out


def test_insufficient_history() -> None:
    bars = _synthetic_bars(MIN_BARS - 1)
    r = evaluate_jupiter_2_sean(bars_asc=bars)
    assert not r.trade
    assert r.reason_code == "insufficient_history"


def test_evaluate_runs_with_full_window() -> None:
    bars = _synthetic_bars(MIN_BARS + 10)
    r = evaluate_jupiter_2_sean(bars_asc=bars, free_collateral_usd=1000.0)
    assert r.side in ("flat", "long", "short")
    assert r.reason_code


def test_calculate_position_size_tiers() -> None:
    a = calculate_position_size(1000.0, 1.6, "long")
    assert a["leverage"] == 33
    assert a["risk_pct"] == pytest.approx(0.03)
    b = calculate_position_size(1000.0, 1.25, "short")
    assert b["leverage"] == 24
    c = calculate_position_size(1000.0, 1.1, "long")
    assert c["leverage"] == 15


def test_generate_signal_atr_window_slice() -> None:
    """220 closes: avg ATR slice -214:-14 is valid."""
    bars = _synthetic_bars(220)
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ss, ls, px, d = generate_signal_from_ohlc(closes, highs, lows)
    assert isinstance(ss, bool) and isinstance(ls, bool)
    assert "atr_ratio" in d
    assert not math.isnan(float(d["atr_ratio"]))
