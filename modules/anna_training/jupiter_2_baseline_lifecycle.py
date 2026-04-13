"""Jupiter_2 baseline — **paper** trade lifecycle (SL/TP, breakeven, monotonic trailing).

Closed 5m bars only. Entry at **bar close** when signal fires; first exit evaluation is on the **next** bar.
See directive: STOP_LOSS / TAKE_PROFIT only; same-bar ambiguity → stop-loss wins.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from modules.anna_training.execution_ledger import (
    SIGNAL_MODE_JUPITER_3,
    compute_pnl_usd,
)
from modules.anna_training.jupiter_2_sean_policy import calculate_atr

SL_ATR_MULT = 1.6
TP_ATR_MULT = 4.0
BREAKEVEN_MOVE_PCT = 0.002  # +0.2% favorable from entry (POLICY_NOTES)


ExitReason = Literal["STOP_LOSS", "TAKE_PROFIT"]


@dataclass
class BaselineOpenPosition:
    """Persisted open baseline position (one per lane — enforced by bridge)."""

    trade_id: str
    side: str  # long | short
    entry_price: float
    entry_market_event_id: str
    entry_candle_open_utc: str
    atr_entry: float
    stop_loss: float
    take_profit: float
    # Immutable entry levels (stop_loss/take_profit fields may trail / breakeven)
    initial_stop_loss: float
    initial_take_profit: float
    breakeven_applied: bool
    size: float
    last_processed_market_event_id: str
    leverage: int | None = None
    risk_pct: float | None = None
    collateral_usd: float | None = None
    notional_usd: float | None = None
    reason_code_at_entry: str = ""
    signal_features_snapshot: dict[str, Any] = field(default_factory=dict)
    size_source: str = ""
    #: Immutable UI snapshot at entry (not recomputed on refresh). V3: optional gate table in parallel.
    entry_policy_narrative_snapshot: str = ""
    entry_jupiter_v3_gates_snapshot: dict[str, Any] | None = None

    def to_json_dict(self) -> dict[str, Any]:
        d_gates = self.entry_jupiter_v3_gates_snapshot
        return {
            "trade_id": self.trade_id,
            "side": self.side,
            "entry_price": self.entry_price,
            "entry_market_event_id": self.entry_market_event_id,
            "entry_candle_open_utc": self.entry_candle_open_utc,
            "atr_entry": self.atr_entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "initial_stop_loss": self.initial_stop_loss,
            "initial_take_profit": self.initial_take_profit,
            "breakeven_applied": self.breakeven_applied,
            "size": self.size,
            "last_processed_market_event_id": self.last_processed_market_event_id,
            "leverage": self.leverage,
            "risk_pct": self.risk_pct,
            "collateral_usd": self.collateral_usd,
            "notional_usd": self.notional_usd,
            "reason_code_at_entry": self.reason_code_at_entry,
            "signal_features_snapshot": dict(self.signal_features_snapshot),
            "size_source": self.size_source,
            "entry_policy_narrative_snapshot": self.entry_policy_narrative_snapshot,
            "entry_jupiter_v3_gates_snapshot": dict(d_gates) if isinstance(d_gates, dict) else None,
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> BaselineOpenPosition:
        _raw_gates = d.get("entry_jupiter_v3_gates_snapshot")
        _gates_parsed = dict(_raw_gates) if isinstance(_raw_gates, dict) else None
        return cls(
            trade_id=str(d["trade_id"]),
            side=str(d["side"]),
            entry_price=float(d["entry_price"]),
            entry_market_event_id=str(d["entry_market_event_id"]),
            entry_candle_open_utc=str(d.get("entry_candle_open_utc") or d.get("candle_open_utc") or ""),
            atr_entry=float(d["atr_entry"]),
            stop_loss=float(d["stop_loss"]),
            take_profit=float(d["take_profit"]),
            initial_stop_loss=float(d.get("initial_stop_loss", d.get("stop_loss", 0.0))),
            initial_take_profit=float(d.get("initial_take_profit", d.get("take_profit", 0.0))),
            breakeven_applied=bool(d.get("breakeven_applied", False)),
            size=float(d.get("size", 1.0)),
            last_processed_market_event_id=str(d["last_processed_market_event_id"]),
            leverage=int(d["leverage"]) if d.get("leverage") is not None else None,
            risk_pct=float(d["risk_pct"]) if d.get("risk_pct") is not None else None,
            collateral_usd=float(d["collateral_usd"]) if d.get("collateral_usd") is not None else None,
            notional_usd=float(d["notional_usd"]) if d.get("notional_usd") is not None else None,
            reason_code_at_entry=str(d.get("reason_code_at_entry") or ""),
            signal_features_snapshot=dict(d.get("signal_features_snapshot") or {}),
            size_source=str(d.get("size_source") or ""),
            entry_policy_narrative_snapshot=str(d.get("entry_policy_narrative_snapshot") or ""),
            entry_jupiter_v3_gates_snapshot=_gates_parsed,
        )


def initial_sl_tp(*, entry: float, atr_entry: float, side: str) -> tuple[float, float]:
    """Initial virtual stop and target from ATR at entry (±1.6 / ±4.0 × ATR)."""
    sd = (side or "").strip().lower()
    sl_dist = SL_ATR_MULT * float(atr_entry)
    tp_dist = TP_ATR_MULT * float(atr_entry)
    ep = float(entry)
    if sd == "long":
        return ep - sl_dist, ep + tp_dist
    if sd == "short":
        return ep + sl_dist, ep - tp_dist
    raise ValueError("side must be long or short")


def _float_ohlc(bar: dict[str, Any]) -> tuple[float, float, float, float]:
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    return o, h, l, c


def atr_from_bar_window(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> float:
    return calculate_atr(closes, highs, lows)


def apply_breakeven(
    *,
    side: str,
    entry: float,
    stop_loss: float,
    high: float,
    low: float,
    breakeven_applied: bool,
) -> tuple[float, bool]:
    """If favorable move ≥ 0.2% from entry, ratchet stop to entry (one-time)."""
    if breakeven_applied:
        return stop_loss, False
    sd = (side or "").strip().lower()
    ep = float(entry)
    sl = float(stop_loss)
    if sd == "long":
        if ep > 0 and (float(high) - ep) / ep >= BREAKEVEN_MOVE_PCT:
            nsl = max(sl, ep)
            return nsl, True
    elif sd == "short":
        if ep > 0 and (ep - float(low)) / ep >= BREAKEVEN_MOVE_PCT:
            nsl = min(sl, ep)
            return nsl, True
    return stop_loss, False


def apply_trailing_monotonic(
    *,
    side: str,
    prev_stop: float,
    close: float,
    atr_t: float,
) -> float:
    """ATR_t-based chandelier; tightening only (never loosen vs prev_stop)."""
    sd = (side or "").strip().lower()
    dist = SL_ATR_MULT * float(atr_t)
    c = float(close)
    ps = float(prev_stop)
    if sd == "long":
        cand = c - dist
        return max(ps, cand)
    if sd == "short":
        cand = c + dist
        return min(ps, cand)
    raise ValueError("side must be long or short")


def evaluate_exit_ohlc(
    *,
    side: str,
    stop_loss: float,
    take_profit: float,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> tuple[ExitReason, float] | None:
    """
    Bar-range exit. If both SL and TP are touched → **STOP_LOSS wins**.

    Fill prices: SL at stop level; TP at take-profit level (deterministic).
    """
    sd = (side or "").strip().lower()
    sl = float(stop_loss)
    tp = float(take_profit)
    o, h, l, c = float(open_), float(high), float(low), float(close)

    if sd == "long":
        hit_sl = l <= sl
        hit_tp = h >= tp
        if hit_sl and hit_tp:
            return "STOP_LOSS", sl
        if hit_sl:
            return "STOP_LOSS", sl
        if hit_tp:
            return "TAKE_PROFIT", tp
        return None

    if sd == "short":
        hit_sl = h >= sl
        hit_tp = l <= tp
        if hit_sl and hit_tp:
            return "STOP_LOSS", sl
        if hit_sl:
            return "STOP_LOSS", sl
        if hit_tp:
            return "TAKE_PROFIT", tp
        return None

    raise ValueError("side must be long or short")


def unrealized_pnl_usd(*, entry: float, mark: float, size: float, side: str) -> float:
    return compute_pnl_usd(entry_price=float(entry), exit_price=float(mark), size=float(size), side=side)


def process_holding_bar(
    pos: BaselineOpenPosition,
    *,
    market_event_id: str,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    bar: dict[str, Any],
) -> tuple[BaselineOpenPosition | None, dict[str, Any] | None]:
    """
    Advance one closed bar while holding.

    Returns:
      (None, exit_record) if the position closes this bar.
      (new_pos, None) to continue holding.

    Skips exit OHLC check on the **entry** bar (entry assumed at prior bar close only).
    """
    mid = str(market_event_id).strip()
    if mid == pos.last_processed_market_event_id:
        return pos, None

    o, h, l, c = _float_ohlc(bar)
    atr_t = atr_from_bar_window(closes=closes, highs=highs, lows=lows)

    out: dict[str, Any] = {
        "market_event_id": mid,
        "atr_t": atr_t,
        "breakeven_event": False,
        "trail_applied": False,
    }

    sl, tp = pos.stop_loss, pos.take_profit
    br = pos.breakeven_applied

    nsl, bre_just_fired = apply_breakeven(
        side=pos.side,
        entry=pos.entry_price,
        stop_loss=sl,
        high=h,
        low=l,
        breakeven_applied=br,
    )
    if bre_just_fired:
        out["breakeven_event"] = True
    br = br or bre_just_fired
    sl = nsl

    sl_prev = sl
    sl = apply_trailing_monotonic(side=pos.side, prev_stop=sl, close=c, atr_t=atr_t)
    if abs(sl - sl_prev) > 1e-12:
        out["trail_applied"] = True

    ex = evaluate_exit_ohlc(
        side=pos.side,
        stop_loss=sl,
        take_profit=tp,
        open_=o,
        high=h,
        low=l,
        close=c,
    )
    if ex is not None:
        reason, fill = ex
        pnl = compute_pnl_usd(
            entry_price=pos.entry_price,
            exit_price=float(fill),
            size=pos.size,
            side=pos.side,
        )
        out["exit_reason"] = reason
        out["exit_price"] = float(fill)
        out["stop_at_exit"] = sl
        out["take_profit_at_exit"] = tp
        out["pnl_usd"] = round(float(pnl), 8)
        return None, out

    ur = unrealized_pnl_usd(entry=pos.entry_price, mark=c, size=pos.size, side=pos.side)
    out["unrealized_pnl_usd"] = round(float(ur), 8)
    out["stop_loss"] = sl
    out["take_profit"] = tp
    out["breakeven_applied"] = br

    new_pos = replace(
        pos,
        stop_loss=sl,
        take_profit=tp,
        breakeven_applied=br,
        last_processed_market_event_id=mid,
    )
    return new_pos, None


# When policy hints are absent or invalid, use paper notional so size is not stuck at 1.0 index stub.
_DEFAULT_BASELINE_NOTIONAL_USD = 100.0


def baseline_lifecycle_base_size_from_signal_features(
    *,
    entry_price: float,
    signal_features: dict[str, Any],
) -> tuple[float, str]:
    """
    Base position size for ``compute_pnl_usd``: ``notional_usd / entry_price``.

    Policy ``position_size_hint.notional_usd`` comes from bankroll-aware sizing
    (``resolve_free_collateral_usd_for_jupiter_policy`` → ``calculate_position_size``).
    If that path is missing or invalid, uses ``_DEFAULT_BASELINE_NOTIONAL_USD`` (100 USD paper default).
    """
    ep = float(entry_price)
    if ep <= 0 or not math.isfinite(ep):
        return 1.0, "fallback_invalid_entry_price"
    ps = dict(signal_features or {})
    psh = ps.get("position_size_hint")
    if isinstance(psh, dict):
        raw_n = psh.get("notional_usd")
        if raw_n is not None:
            try:
                notional = float(raw_n)
            except (TypeError, ValueError):
                notional = None
            else:
                if math.isfinite(notional) and notional > 0:
                    sz = notional / ep
                    if math.isfinite(sz) and sz > 0:
                        return sz, "notional_usd_div_entry_price"
    sz_d = _DEFAULT_BASELINE_NOTIONAL_USD / ep
    if math.isfinite(sz_d) and sz_d > 0:
        return float(sz_d), "default_baseline_notional_usd_100"
    return 1.0, "fallback_size_nonpositive"


def open_position_from_signal(
    *,
    trade_id: str,
    market_event_id: str,
    bar: dict[str, Any],
    side: str,
    atr_entry: float,
    reason_code: str,
    signal_features: dict[str, Any],
    signal_mode: str = "",
) -> BaselineOpenPosition:
    """Entry price = **close** of the signal bar. ``size`` = policy notional / entry (see baseline helper).

    ``entry_policy_narrative_snapshot`` / ``entry_jupiter_v3_gates_snapshot`` are set **once** at entry
    for stable dashboard display (no per-refresh recompute).
    """
    c = float(bar["close"])
    op_utc = str(bar.get("candle_open_utc") or "").strip()
    sl, tp = initial_sl_tp(entry=c, atr_entry=atr_entry, side=side)
    ps = dict(signal_features or {})
    lev = None
    rp = None
    col = None
    notional = None
    psh = ps.get("position_size_hint")
    if isinstance(psh, dict):
        lev = int(psh["leverage"]) if psh.get("leverage") is not None else None
        rp = float(psh["risk_pct"]) if psh.get("risk_pct") is not None else None
        col = float(psh["collateral_usd"]) if psh.get("collateral_usd") is not None else None
        notional = float(psh["notional_usd"]) if psh.get("notional_usd") is not None else None

    sz, sz_src = baseline_lifecycle_base_size_from_signal_features(entry_price=c, signal_features=ps)

    sm = (signal_mode or "").strip()
    nar_snap = ""
    gates_snap: dict[str, Any] | None = None
    if sm == SIGNAL_MODE_JUPITER_3:
        jn = ps.get("jupiter_policy_narrative")
        if isinstance(jn, str) and jn.strip():
            nar_snap = jn.strip()
        jg = ps.get("jupiter_v3_gates")
        gates_snap = dict(jg) if isinstance(jg, dict) else None
    elif sm:
        from modules.anna_training.sean_jupiter_baseline_signal import format_baseline_jupiter_tile_narrative

        pb = ps.get("policy_blockers")
        pbl = [str(x) for x in pb] if isinstance(pb, list) else None
        nar_snap = format_baseline_jupiter_tile_narrative(
            signal_mode=sm,
            features=ps,
            reason_code=str(reason_code or ""),
            trade=True,
            side=str(side or "flat"),
            policy_blockers=pbl,
        ).strip()

    return BaselineOpenPosition(
        trade_id=trade_id,
        side=(side or "").strip().lower(),
        entry_price=c,
        entry_market_event_id=str(market_event_id).strip(),
        entry_candle_open_utc=op_utc,
        atr_entry=float(atr_entry),
        stop_loss=sl,
        take_profit=tp,
        initial_stop_loss=float(sl),
        initial_take_profit=float(tp),
        breakeven_applied=False,
        size=float(sz),
        last_processed_market_event_id=str(market_event_id).strip(),
        leverage=lev,
        risk_pct=rp,
        collateral_usd=col,
        notional_usd=notional,
        reason_code_at_entry=str(reason_code or ""),
        signal_features_snapshot=ps,
        size_source=str(sz_src),
        entry_policy_narrative_snapshot=nar_snap,
        entry_jupiter_v3_gates_snapshot=gates_snap,
    )
