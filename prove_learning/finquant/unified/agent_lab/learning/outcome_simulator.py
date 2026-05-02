"""
FinQuant — Outcome Simulator

Computes realistic per-decision outcomes from candle data.

For each decision (ENTER_LONG, ENTER_SHORT, NO_TRADE), produces:
  - direction (long/short/flat)
  - entry_price, exit_price
  - pnl (in price units)
  - pnl_pct
  - win/loss/no_trade verdict
  - bars_held
  - hit_target / hit_stop / closed_at_horizon

This is the deterministic "execution" the architect spec calls for.
"""

from __future__ import annotations

from typing import Any

# Default risk geometry (operator-overridable via config)
DEFAULT_STOP_ATR_MULT = 1.5
DEFAULT_TARGET_ATR_MULT = 2.5
DEFAULT_HORIZON_BARS = 5


def simulate_outcome(
    *,
    proposed_action: str,
    case: dict[str, Any],
    horizon_bars: int = DEFAULT_HORIZON_BARS,
    stop_atr_mult: float = DEFAULT_STOP_ATR_MULT,
    target_atr_mult: float = DEFAULT_TARGET_ATR_MULT,
) -> dict[str, Any]:
    """
    Simulate the outcome of a proposed action against the case's hidden future candles.

    Returns:
      {
        "direction_v1": "long"|"short"|"flat",
        "entry_price_v1": float|None,
        "exit_price_v1": float|None,
        "pnl_v1": float,                    # 0.0 if no trade
        "pnl_pct_v1": float,                # 0.0 if no trade
        "outcome_v1": "win"|"loss"|"no_trade",
        "bars_held_v1": int,
        "hit_target_v1": bool,
        "hit_stop_v1": bool,
        "closed_at_horizon_v1": bool,
        "no_trade_correct_v1": bool|None    # only meaningful when proposed_action == NO_TRADE
      }
    """
    candles = case.get("candles") or []
    hide_from = int(case.get("hidden_future_start_index", 0) or 0)
    if not candles or hide_from <= 0 or hide_from > len(candles):
        return _flat_outcome(reason="no_candles_or_no_outcome_window")

    entry_candle = candles[hide_from - 1]
    future_candles = candles[hide_from:hide_from + horizon_bars]

    # NO_TRADE outcome
    if proposed_action == "NO_TRADE":
        return _no_trade_outcome(entry_candle, future_candles)

    # ENTER_LONG / ENTER_SHORT
    if proposed_action not in ("ENTER_LONG", "ENTER_SHORT"):
        # HOLD/EXIT happen mid-lifecycle; reuse long-style geometry
        if proposed_action in ("HOLD", "EXIT"):
            return _flat_outcome(reason=f"action={proposed_action}_not_simulated_independently")
        return _flat_outcome(reason=f"unknown_action={proposed_action}")

    if not future_candles:
        return _flat_outcome(reason="no_future_candles_visible")

    direction = "long" if proposed_action == "ENTER_LONG" else "short"
    entry_price = float(entry_candle.get("close", 0.0) or 0.0)
    atr = float(entry_candle.get("atr_14") or 0.0)

    if entry_price <= 0:
        return _flat_outcome(reason="invalid_entry_price")

    if atr <= 0:
        atr = max(0.01 * entry_price, 0.01)

    if direction == "long":
        target_price = entry_price + atr * target_atr_mult
        stop_price = entry_price - atr * stop_atr_mult
    else:
        target_price = entry_price - atr * target_atr_mult
        stop_price = entry_price + atr * stop_atr_mult

    # Walk forward bar-by-bar
    exit_price = entry_price
    bars_held = 0
    hit_target = False
    hit_stop = False
    closed_at_horizon = False

    for bar in future_candles:
        bars_held += 1
        high = float(bar.get("high", bar.get("close", 0.0)) or 0.0)
        low = float(bar.get("low", bar.get("close", 0.0)) or 0.0)
        close = float(bar.get("close", 0.0) or 0.0)

        if direction == "long":
            if low <= stop_price:
                exit_price = stop_price
                hit_stop = True
                break
            if high >= target_price:
                exit_price = target_price
                hit_target = True
                break
            exit_price = close
        else:
            if high >= stop_price:
                exit_price = stop_price
                hit_stop = True
                break
            if low <= target_price:
                exit_price = target_price
                hit_target = True
                break
            exit_price = close

    if not hit_target and not hit_stop:
        closed_at_horizon = True

    if direction == "long":
        pnl = exit_price - entry_price
    else:
        pnl = entry_price - exit_price

    pnl_pct = (pnl / entry_price) if entry_price else 0.0

    if pnl > 0:
        outcome = "win"
    elif pnl < 0:
        outcome = "loss"
    else:
        outcome = "no_trade"

    return {
        "direction_v1": direction,
        "entry_price_v1": round(entry_price, 6),
        "exit_price_v1": round(exit_price, 6),
        "pnl_v1": round(pnl, 6),
        "pnl_pct_v1": round(pnl_pct, 6),
        "outcome_v1": outcome,
        "bars_held_v1": bars_held,
        "hit_target_v1": hit_target,
        "hit_stop_v1": hit_stop,
        "closed_at_horizon_v1": closed_at_horizon,
        "no_trade_correct_v1": None,
        "stop_price_v1": round(stop_price, 6),
        "target_price_v1": round(target_price, 6),
    }


def _no_trade_outcome(entry_candle: dict, future_candles: list[dict]) -> dict[str, Any]:
    """
    NO_TRADE is correct if the next horizon does NOT have a clear directional move
    that would have produced a win. Otherwise NO_TRADE is a missed opportunity.
    """
    if not future_candles:
        return {
            "direction_v1": "flat",
            "entry_price_v1": float(entry_candle.get("close", 0.0) or 0.0),
            "exit_price_v1": float(entry_candle.get("close", 0.0) or 0.0),
            "pnl_v1": 0.0,
            "pnl_pct_v1": 0.0,
            "outcome_v1": "no_trade",
            "bars_held_v1": 0,
            "hit_target_v1": False,
            "hit_stop_v1": False,
            "closed_at_horizon_v1": True,
            "no_trade_correct_v1": True,
        }

    entry_price = float(entry_candle.get("close", 0.0) or 0.0)
    atr = float(entry_candle.get("atr_14") or 0.0) or max(0.01 * entry_price, 0.01)

    last_close = float(future_candles[-1].get("close", entry_price) or entry_price)
    move = last_close - entry_price
    move_pct = (move / entry_price) if entry_price else 0.0

    # If the next horizon moved beyond +/- 1 ATR, NO_TRADE was a missed move
    significant_move = abs(move) > atr * 1.5
    no_trade_correct = not significant_move

    return {
        "direction_v1": "flat",
        "entry_price_v1": round(entry_price, 6),
        "exit_price_v1": round(last_close, 6),
        "pnl_v1": 0.0,
        "pnl_pct_v1": round(move_pct, 6),
        "outcome_v1": "no_trade",
        "bars_held_v1": len(future_candles),
        "hit_target_v1": False,
        "hit_stop_v1": False,
        "closed_at_horizon_v1": True,
        "no_trade_correct_v1": bool(no_trade_correct),
        "post_decision_move_v1": round(move, 6),
    }


def _flat_outcome(*, reason: str) -> dict[str, Any]:
    return {
        "direction_v1": "flat",
        "entry_price_v1": None,
        "exit_price_v1": None,
        "pnl_v1": 0.0,
        "pnl_pct_v1": 0.0,
        "outcome_v1": "no_trade",
        "bars_held_v1": 0,
        "hit_target_v1": False,
        "hit_stop_v1": False,
        "closed_at_horizon_v1": False,
        "no_trade_correct_v1": None,
        "skip_reason_v1": reason,
    }
