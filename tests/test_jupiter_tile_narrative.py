"""Jupiter operator tile narrative (Sean policy text block)."""

from __future__ import annotations

from modules.anna_training.sean_jupiter_baseline_signal import format_jupiter_tile_narrative_v1


def test_format_without_tile_shows_reason() -> None:
    t = format_jupiter_tile_narrative_v1(
        features={},
        reason_code="insufficient_history",
        trade=False,
        side="flat",
    )
    assert "insufficient_history" in t
    assert "trade=False" in t


def test_format_with_tile_includes_ohlc_and_signals() -> None:
    features = {
        "short_signal_raw": False,
        "long_signal_raw": True,
        "tile": {
            "candle_open_utc": "2026-04-06T18:30:00.000Z",
            "new_ohlcv": {"o": 82.0, "h": 83.0, "l": 81.0, "c": 82.1, "v": 590},
            "prev_ohlc": {"o": 82.1, "h": 83.0, "l": 82.0, "c": 82.08},
            "prev_rsi": 59.85,
            "current_rsi": 60.75,
            "supertrend_label": "BULLISH (green)",
            "atr_current": 0.133,
            "atr_avg200": 0.26,
            "atr_ratio": 1.5,
            "price_vs_ema200": "ABOVE",
            "ema200": 81.86,
            "breakdown_long": {
                "supertrend_bullish": True,
                "above_ema": True,
                "rsi_gt_52": True,
                "higher_close": True,
                "long_ok": True,
            },
            "breakdown_short": {
                "supertrend_bearish": False,
                "below_ema": False,
                "rsi_lt_48": False,
                "lower_close": False,
                "short_ok": False,
            },
        },
    }
    t = format_jupiter_tile_narrative_v1(
        features=features,
        reason_code="jupiter_policy_long_signal",
        trade=True,
        side="long",
    )
    assert "New 5-min candle formed" in t
    assert "Previous candle:" in t
    assert "Supertrend:" in t
    assert "ATR Analysis:" in t
    assert "Volatility gate: passes" in t
    assert "Signal Breakdown" in t
    assert "Signal Breakdown → Long=true" in t
    assert "RSI>52=true" in t
    assert "HigherClose=true" in t
    assert "Signal Breakdown → Short=false" in t
    assert "Signals: short=false (RSI=60.75), long=true" in t
    assert "ATR-Supertrend SIGNAL → LONG at 82.1 | ATR=0.133" in t
    assert "Processing LONG signal" in t


def test_rsi_extreme_skip_uses_operator_filter_copy() -> None:
    features = {
        "short_signal_raw": False,
        "long_signal_raw": True,
        "policy_blockers": ["rsi_extreme_long_above_75"],
        "tile": {
            "candle_open_utc": "2026-04-06T18:30:00Z",
            "new_ohlcv": {"o": 82.0, "h": 83.0, "l": 81.0, "c": 82.11571928, "v": 590},
            "prev_ohlc": {"o": 82.1, "h": 83.0, "l": 82.0, "c": 82.08},
            "prev_rsi": 59.853165914941,
            "current_rsi": 76.0,
            "supertrend_label": "BULLISH (green)",
            "atr_current": 0.133266,
            "atr_avg200": 0.260714,
            "atr_ratio": 0.51,
            "price_vs_ema200": "ABOVE",
            "ema200": 81.8602,
            "supertrend_direction": 1,
            "breakdown_long": {
                "supertrend_bullish": True,
                "above_ema": True,
                "rsi_gt_52": True,
                "higher_close": True,
                "long_ok": True,
            },
            "breakdown_short": {
                "supertrend_bearish": False,
                "below_ema": False,
                "rsi_lt_48": False,
                "lower_close": False,
                "short_ok": False,
            },
        },
    }
    t = format_jupiter_tile_narrative_v1(
        features=features,
        reason_code="rsi_extreme_skip",
        trade=False,
        side="flat",
        policy_blockers=["rsi_extreme_long_above_75"],
    )
    assert "Processing LONG signal" not in t
    assert "ATR-Supertrend SIGNAL → LONG" not in t
    assert "Signals: short=false" in t
    assert "Filter: extreme RSI" in t
    assert "Volatility gate: blocked" in t
