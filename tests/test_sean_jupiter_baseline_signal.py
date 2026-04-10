"""Sean baseline signal — thin adapter over Jupiter_2 Sean policy (``evaluate_jupiter_2_sean``)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bar(i: int, *, o: float, h: float, l: float, c: float) -> dict:
    return {
        "id": i,
        "canonical_symbol": "SOL-PERP",
        "timeframe": "5m",
        "candle_open_utc": f"2026-01-01T00:{i:03d}:00Z",
        "candle_close_utc": f"2026-01-01T00:{i:03d}:05Z",
        "market_event_id": f"SOL-PERP_5m_test_{i:04d}",
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "tick_count": 3,
        "price_source": "test",
        "computed_at": "2026-01-01T00:00:00Z",
    }


def test_insufficient_history() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    bars = [_bar(i, o=100.0, h=101.0, l=99.0, c=100.0) for i in range(MIN_BARS - 1)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is False
    assert out.reason_code == "insufficient_history"


def test_aggregate_candles_flags_short_parity() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import aggregate_candles_signal_flags

    prev_c = {"high": 100.0, "low": 99.0}
    curr_c = {"high": 100.5, "low": 99.0}
    short, long_ = aggregate_candles_signal_flags(
        prev_candle=prev_c,
        curr_candle=curr_c,
        prev_rsi_raw=65.0,
        current_rsi_raw=62.0,
    )
    assert short is True
    assert long_ is False


def test_aggregate_candles_flags_long_parity() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import aggregate_candles_signal_flags

    prev_c = {"high": 101.0, "low": 100.0}
    curr_c = {"high": 100.5, "low": 98.5}
    short, long_ = aggregate_candles_signal_flags(
        prev_candle=prev_c,
        curr_candle=curr_c,
        prev_rsi_raw=38.0,
        current_rsi_raw=39.0,
    )
    assert short is False
    assert long_ is True


def test_flat_closes_often_no_signal() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    bars = [_bar(i, o=100.0, h=100.0, l=100.0, c=100.0) for i in range(MIN_BARS + 5)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is False
    # Flat series: Jupiter_2 may block on ATR ratio before ``jupiter_2_no_signal``.
    assert out.reason_code in ("no_signal", "atr_ratio_below_min")


def test_rsi_trading_core_length_matches_ts() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import RSI_PERIOD, rsi_trading_core

    closes = [100.0 + i * 0.1 for i in range(30)]
    r = rsi_trading_core(closes)
    assert len(r) == len(closes)
    assert math.isnan(r[RSI_PERIOD - 1])
    assert not math.isnan(r[RSI_PERIOD])


def test_resolve_atr_ratio_from_features() -> None:
    from modules.anna_training.sean_jupiter_baseline_signal import _resolve_atr_ratio_from_features

    assert _resolve_atr_ratio_from_features({}) is None
    assert _resolve_atr_ratio_from_features({"tile": {"atr_ratio": 1.5}}) == 1.5
    assert _resolve_atr_ratio_from_features(
        {"tile": {"atr_current": 2.7, "atr_avg200": 2.0}}
    ) == pytest.approx(1.35)
    assert _resolve_atr_ratio_from_features(
        {"tile": {"atr_current": 1.0, "atr_avg200": 0.0}}
    ) is None


def test_tile_atr_ratio_matches_jupiter_2_generate_signal() -> None:
    """Baseline tile uses same simple-TR ratio as jupiter_2_sean_policy.generate_signal_from_ohlc."""
    import random

    from modules.anna_training.jupiter_2_sean_policy import generate_signal_from_ohlc
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    random.seed(7)
    p = 100.0
    bars = []
    for i in range(MIN_BARS + 20):
        p = p + random.uniform(-0.4, 0.4)
        o = p
        c = p + random.uniform(-0.2, 0.2)
        h = max(o, c) + random.uniform(0, 0.15)
        l = min(o, c) - random.uniform(0, 0.15)
        bars.append(
            _bar(
                i,
                o=o,
                h=h,
                l=l,
                c=c,
            )
        )
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    _, _, _, diag = generate_signal_from_ohlc(closes, highs, lows)
    tr = out.features.get("tile") or {}
    assert tr.get("atr_ratio") == pytest.approx(float(diag["atr_ratio"]), rel=1e-9, abs=1e-12)


def test_atr_ratio_below_min_final_veto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Jupiter_2 ATR ratio block maps to baseline ``atr_ratio_below_min`` + policy_blockers."""
    import modules.anna_training.sean_jupiter_baseline_signal as m
    from modules.anna_training.jupiter_2_sean_policy import Jupiter2SeanPolicyResult, REFERENCE_SOURCE
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    fake_feat = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": "jupiter_2_sean_perps_v1",
        "supertrend_bullish": False,
        "ema200": 100.0,
        "current_rsi": 50.0,
        "atr": 1.0,
        "avg_atr_window": 1.0,
        "atr_ratio": 1.0,
        "long_signal_core": False,
        "short_signal_core": True,
        "reason_detail": "atr_ratio_below_1_35",
    }
    fake_res = Jupiter2SeanPolicyResult(
        trade=False,
        side="flat",
        reason_code="jupiter_2_atr_ratio_block",
        pnl_usd=None,
        features=fake_feat,
    )
    monkeypatch.setattr(m, "evaluate_jupiter_2_sean", lambda **kw: fake_res)

    bars = [_bar(i, o=100.0, h=101.0, l=99.0, c=100.0) for i in range(MIN_BARS)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is False
    assert out.reason_code == "atr_ratio_below_min"
    assert out.features.get("policy_blockers") == ["atr_ratio_below_1.35"]


def test_atr_ratio_at_min_allows_trade(monkeypatch: pytest.MonkeyPatch) -> None:
    import modules.anna_training.sean_jupiter_baseline_signal as m
    from modules.anna_training.jupiter_2_sean_policy import (
        ATR_RATIO_MIN,
        Jupiter2SeanPolicyResult,
        REFERENCE_SOURCE,
    )
    from modules.anna_training.sean_jupiter_baseline_signal import MIN_BARS, evaluate_sean_jupiter_baseline_v1

    fake_feat = {
        "reference": REFERENCE_SOURCE,
        "catalog_id": "jupiter_2_sean_perps_v1",
        "supertrend_bullish": False,
        "ema200": 100.0,
        "current_rsi": 45.0,
        "atr": ATR_RATIO_MIN,
        "avg_atr_window": 1.0,
        "atr_ratio": ATR_RATIO_MIN,
        "long_signal_core": False,
        "short_signal_core": True,
    }
    fake_res = Jupiter2SeanPolicyResult(
        trade=True,
        side="short",
        reason_code="jupiter_2_short_signal",
        pnl_usd=0.0,
        features=fake_feat,
    )
    monkeypatch.setattr(m, "evaluate_jupiter_2_sean", lambda **kw: fake_res)

    bars = [_bar(i, o=100.0, h=101.0, l=99.0, c=100.0) for i in range(MIN_BARS)]
    out = evaluate_sean_jupiter_baseline_v1(bars_asc=bars)
    assert out.trade is True
    assert out.reason_code == "jupiter_policy_short_signal"


def test_jupiter_ema200_last_defined_for_long_series() -> None:
    """Jupiter_2 ``ema()`` uses SMA seed + recursive alpha (policy port — not pandas ewm)."""
    import random

    from modules.anna_training.jupiter_2_sean_policy import EMA_PERIOD, ema

    random.seed(42)
    closes = [100.0 + random.random() for _ in range(220)]
    ema_s = ema(closes)
    assert len(ema_s) == len(closes)
    assert not math.isnan(float(ema_s[-1]))
