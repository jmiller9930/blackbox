"""
FinQuant — Context Builder (RMv2)

Converts raw candle history into a structured narrative context that Qwen
can reason about. Turns a photograph into a film reel.

The market is a flowing river. This module describes the flow:
  - RSI trajectory over the last N bars (rising/falling, from where to where)
  - ATR trajectory (expanding/contracting, how fast)
  - Price vs EMA history (how long above/below, recent crossover?)
  - Volume profile (expanding or contracting participation)
  - Position in the current regime (early/mid/late trend or ranging)
  - Retrieved memory with structural detail (not just stats)

All outputs are plain text strings suitable for embedding in LLM prompts.
All computations are deterministic — no LLM calls in this module.

Per prime directive:
  P-5 — Context first. Indicators mean different things in different regimes.
  P-4 — Pattern similarity. Anchor judgment in structural evidence.
  P-2 — Reason with tools. Provide the tools, not just the numbers.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Trajectory helpers
# ---------------------------------------------------------------------------

def _slope_label(values: list[float | None], n: int = 5) -> str:
    """Classify slope of last N values as rising/flat/falling."""
    valid = [v for v in values[-n:] if v is not None]
    if len(valid) < 2:
        return "insufficient_data"
    delta = valid[-1] - valid[0]
    pct = delta / abs(valid[0]) if valid[0] and abs(valid[0]) > 0 else 0.0
    if pct > 0.015:
        return "rising_strongly"
    if pct > 0.003:
        return "rising"
    if pct < -0.015:
        return "falling_strongly"
    if pct < -0.003:
        return "falling"
    return "flat"


def _rsi_trajectory(bars: list[dict[str, Any]], n: int = 5) -> dict[str, Any]:
    """Summarize RSI trajectory over last N bars."""
    rsi_vals = [b.get("rsi_14") for b in bars[-n:]]
    valid = [v for v in rsi_vals if v is not None]
    if not valid:
        return {"label": "unknown", "sequence": [], "direction": "unknown", "from": None, "to": None}

    direction = _slope_label(rsi_vals, n)
    return {
        "label": f"RSI {direction}: {valid[0]:.1f} → {valid[-1]:.1f}" if len(valid) >= 2 else f"RSI={valid[0]:.1f}",
        "sequence": [round(v, 1) for v in valid],
        "direction": direction,
        "from": round(valid[0], 1),
        "to": round(valid[-1], 1),
        "current_zone": _rsi_zone(valid[-1]),
    }


def _rsi_zone(rsi: float) -> str:
    if rsi >= 70:
        return "overbought"
    if rsi >= 60:
        return "bullish_strong"
    if rsi >= 50:
        return "bullish_range"
    if rsi >= 40:
        return "neutral_bearish"
    if rsi >= 30:
        return "bearish_range"
    return "oversold"


def _atr_trajectory(bars: list[dict[str, Any]], n: int = 5) -> dict[str, Any]:
    """Summarize ATR% trajectory — price-relative so it works at any price level."""
    entries = []
    for b in bars[-n:]:
        atr = b.get("atr_14")
        close = b.get("close", 0.0) or 0.0
        if atr is not None and close > 0:
            entries.append(float(atr) / float(close) * 100)
        else:
            entries.append(None)

    valid = [v for v in entries if v is not None]
    if not valid:
        return {"label": "unknown", "direction": "unknown", "from_pct": None, "to_pct": None}

    direction = _slope_label(entries, n)
    return {
        "label": f"ATR% {direction}: {valid[0]:.3f}% → {valid[-1]:.3f}%",
        "direction": direction,
        "from_pct": round(valid[0], 4),
        "to_pct": round(valid[-1], 4),
        "current_pct": round(valid[-1], 4),
        "volatility_class": "expanding" if direction in ("rising", "rising_strongly") else
                            "contracting" if direction in ("falling", "falling_strongly") else "stable",
    }


def _ema_relationship(bars: list[dict[str, Any]], n: int = 10) -> dict[str, Any]:
    """How many bars has price been above/below EMA, and did it recently cross?"""
    above_count = 0
    below_count = 0
    crossover_bar = None  # bars ago of most recent crossover

    prev_above = None
    for i, b in enumerate(bars[-n:]):
        close = b.get("close", 0.0) or 0.0
        ema = b.get("ema_20")
        if ema is None:
            continue
        above = close > float(ema)
        if prev_above is not None and above != prev_above:
            crossover_bar = n - i  # bars ago
        if above:
            above_count += 1
        else:
            below_count += 1
        prev_above = above

    current_bar = bars[-1]
    current_close = current_bar.get("close", 0.0) or 0.0
    current_ema = current_bar.get("ema_20")
    currently_above = (current_ema is not None and float(current_close) > float(current_ema))

    label = f"Price {'above' if currently_above else 'below'} EMA for {above_count if currently_above else below_count} of last {n} bars"
    if crossover_bar is not None:
        label += f"; crossed {'above' if currently_above else 'below'} {crossover_bar} bars ago"

    return {
        "label": label,
        "currently_above_ema": currently_above,
        "bars_above": above_count,
        "bars_below": below_count,
        "recent_crossover_bars_ago": crossover_bar,
        "ema_gap_pct": round((float(current_close) - float(current_ema)) / float(current_ema) * 100, 4)
        if current_ema and float(current_ema) > 0 else None,
    }


def _volume_profile(bars: list[dict[str, Any]], n: int = 5) -> dict[str, Any]:
    """Summarize volume trend — expanding or contracting participation."""
    vols = [float(b.get("volume", 0) or 0) for b in bars[-n:]]
    valid = [v for v in vols if v > 0]
    if len(valid) < 2:
        return {"label": "unknown", "direction": "unknown"}

    direction = _slope_label(vols, n)
    avg = sum(valid) / len(valid)
    current = valid[-1]
    vs_avg = (current - avg) / avg if avg > 0 else 0.0

    return {
        "label": f"Volume {direction}; current {'+' if vs_avg >= 0 else ''}{vs_avg*100:.1f}% vs {n}-bar avg",
        "direction": direction,
        "current": round(current, 2),
        "avg_n_bars": round(avg, 2),
        "vs_avg_pct": round(vs_avg * 100, 2),
    }


def _position_in_move(bars: list[dict[str, Any]], regime: str) -> dict[str, Any]:
    """
    Estimate how far into the current regime we are.
    Uses RSI momentum and ATR contraction to detect regime maturity.
    """
    if len(bars) < 5:
        return {"label": "insufficient_history", "phase": "unknown", "bars_in_regime": 0}

    # Count consecutive bars where RSI stayed in same zone (trending/ranging)
    current_zone = _rsi_zone(bars[-1].get("rsi_14") or 50)
    bars_in_regime = 1
    for b in reversed(bars[:-1]):
        z = _rsi_zone(b.get("rsi_14") or 50)
        if z == current_zone or (
            current_zone in ("bullish_strong", "bullish_range") and z in ("bullish_strong", "bullish_range")
        ) or (
            current_zone in ("neutral_bearish", "bearish_range") and z in ("neutral_bearish", "bearish_range")
        ):
            bars_in_regime += 1
        else:
            break

    # Classify phase based on bars in regime and RSI momentum
    rsi_vals = [b.get("rsi_14") for b in bars[-5:] if b.get("rsi_14") is not None]
    rsi_direction = _slope_label(rsi_vals, len(rsi_vals))

    if bars_in_regime <= 3:
        phase = "early"
    elif bars_in_regime <= 8:
        phase = "mid"
    else:
        # Late trend — check for exhaustion signals
        phase = "late_possible_exhaustion" if rsi_direction in ("flat", "falling") else "extended"

    label = f"Regime '{regime}' — {bars_in_regime} bars in current phase ({phase})"
    return {
        "label": label,
        "phase": phase,
        "bars_in_regime": bars_in_regime,
        "rsi_momentum": rsi_direction,
    }


# ---------------------------------------------------------------------------
# Memory record detail formatter
# ---------------------------------------------------------------------------

def format_memory_record(record: dict[str, Any], current_regime: str) -> str:
    """
    Format a single retrieved memory record with structural detail.
    Per P-4: anchor judgment in evidence, not just statistics.
    """
    action = record.get("entry_action_v1") or "UNKNOWN"
    win_rate = float(record.get("pattern_win_rate_v1") or 0.0)
    obs = int(record.get("pattern_total_obs_v1") or 0)
    status = record.get("pattern_status_v1") or "unknown"
    record_regime = record.get("regime_v1") or "unknown"
    lesson = record.get("lesson_v1") or ""
    pnl = float(record.get("pnl_v1") or 0.0)
    outcome_kind = record.get("outcome_kind_v1") or ""
    expectancy = float(record.get("pattern_expectancy_v1") or 0.0)

    regime_match = "MATCH" if record_regime == current_regime else f"DIFFERENT ({record_regime})"

    lines = [
        f"  Action: {action} | win_rate={win_rate:.0%} | obs={obs} | status={status}",
        f"  Regime: {record_regime} [{regime_match} vs current]",
        f"  Outcome: {outcome_kind} | PnL={pnl:+.4f} | Pattern expectancy={expectancy:+.4f}",
    ]
    if lesson:
        lines.append(f"  Lesson: {lesson[:150]}")

    return "\n".join(lines)


def format_memory_context(
    prior_records: list[dict[str, Any]],
    current_regime: str,
) -> str:
    """Format all retrieved memory records for the prompt."""
    if not prior_records:
        return "No validated patterns retrieved. Memory is empty — reason from indicators only."

    long_records = [r for r in prior_records if r.get("entry_action_v1") == "ENTER_LONG"]
    no_trade_records = [r for r in prior_records if r.get("entry_action_v1") == "NO_TRADE"]

    lines = [f"Retrieved {len(prior_records)} validated pattern(s) from governed memory:"]

    if long_records:
        lines.append(f"\nLONG patterns ({len(long_records)}):")
        for r in long_records[:3]:
            lines.append(format_memory_record(r, current_regime))

    if no_trade_records:
        lines.append(f"\nNO_TRADE patterns ({len(no_trade_records)}):")
        for r in no_trade_records[:2]:
            lines.append(format_memory_record(r, current_regime))

    # Regime match summary
    matching = [r for r in prior_records if r.get("regime_v1") == current_regime]
    lines.append(f"\nRegime match: {len(matching)}/{len(prior_records)} records match current regime '{current_regime}'")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main context builder
# ---------------------------------------------------------------------------

def build_rich_context(
    bars: list[dict[str, Any]],
    symbol: str,
    timeframe_minutes: int,
    regime: str,
    prior_records: list[dict[str, Any]],
    n_trajectory: int = 5,
) -> dict[str, Any]:
    """
    Build full rich context for the LLM prompt.

    Returns a dict with both structured data and formatted narrative strings.
    The narrative strings are ready to embed directly in prompts.
    """
    if not bars:
        return {
            "narrative": "No market data available.",
            "rsi_traj": {}, "atr_traj": {}, "ema_rel": {},
            "volume_profile": {}, "position": {}, "memory_narrative": "",
        }

    current_bar = bars[-1]
    close = float(current_bar.get("close", 0.0) or 0.0)
    prev_close = float(bars[-2].get("close", close) if len(bars) >= 2 else close)
    rsi = current_bar.get("rsi_14")
    atr = current_bar.get("atr_14")
    ema = current_bar.get("ema_20")
    volume = current_bar.get("volume", 0) or 0
    ref = close if close > 0 else 1.0
    atr_pct = float(atr) / ref * 100 if atr is not None else None

    rsi_traj = _rsi_trajectory(bars, n_trajectory)
    atr_traj = _atr_trajectory(bars, n_trajectory)
    ema_rel = _ema_relationship(bars, min(10, len(bars)))
    vol_prof = _volume_profile(bars, n_trajectory)
    position = _position_in_move(bars, regime)
    memory_narrative = format_memory_context(prior_records, regime)

    # Build narrative string for LLM
    price_move = close - prev_close
    price_move_pct = price_move / prev_close * 100 if prev_close > 0 else 0.0

    narrative = f"""MARKET CONTEXT — {symbol} {timeframe_minutes}m

CURRENT BAR:
  Close: {close:.4f} ({'+' if price_move >= 0 else ''}{price_move_pct:.3f}% from prior bar)
  RSI(14): {rsi:.1f if rsi is not None else 'N/A'} [{rsi_traj.get('current_zone', 'unknown')}]
  ATR(14): {atr:.4f if atr is not None else 'N/A'} ({atr_pct:.3f}% of price if atr_pct is not None else 'N/A')
  EMA(20): {ema:.4f if ema is not None else 'N/A'} [price {'above' if ema and close > float(ema) else 'below'} EMA]

REGIME: {regime.upper()}
{position['label']}

TRAJECTORY (last {n_trajectory} bars):
  {rsi_traj.get('label', 'RSI: unknown')}
  {atr_traj.get('label', 'ATR: unknown')} [{atr_traj.get('volatility_class', 'unknown')} volatility]
  {ema_rel.get('label', 'EMA: unknown')}
  {vol_prof.get('label', 'Volume: unknown')}

MEMORY:
{memory_narrative}"""

    return {
        "narrative": narrative,
        "current_bar": current_bar,
        "close": close,
        "rsi": rsi,
        "atr_pct": atr_pct,
        "regime": regime,
        "rsi_traj": rsi_traj,
        "atr_traj": atr_traj,
        "ema_rel": ema_rel,
        "volume_profile": vol_prof,
        "position": position,
        "memory_narrative": memory_narrative,
        "prior_records_count": len(prior_records),
    }
