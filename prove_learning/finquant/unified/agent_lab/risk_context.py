"""
FinQuant — Risk Context Module

Context IS risk management. The same context that determines ENTER vs NO_TRADE
also determines how much capital to deploy. One computation, two outputs.

Principle: R is the anchor — context is the throttle.
  baseline_risk_pct = 1.23% (Sean's floor — never goes below this, never changes)
  final_risk_pct = baseline × vol_factor × struct_factor × signal_factor × session_factor × health_factor
  bounds: [0.5%, 2.0%]

Factor ranges:
  volatility_factor : 0.5 (dangerous volatile) → 1.0 (normal) → 1.2 (quiet trending)
  structure_factor  : 0.5 (ranging/chop) → 1.0 (mild trend) → 1.3 (HH_HL confirmed)
  signal_factor     : 0.6 (min spread=0.20) → 1.0 (spread=0.35) → 1.5 (spread=0.55+)
  session_factor    : 0.6 (Asian session) → 1.0 (US/EU peak) → 1.1 (extended hours)
  health_factor     : 0.5 (3+ recent losses) → 1.0 (neutral) → 1.2 (winning streak)

Usage:
  from risk_context import compute_risk_context
  ctx = compute_risk_context(
      atr_pct=0.45,
      regime="trending_up",
      swing_structure="HH_HL",
      confidence_spread=0.42,
      utc_hour=15,
      pattern_win_rate=0.65,
      recent_losses=1,
      recent_wins=3,
  )
  # ctx["final_risk_pct"] → 1.46
  # ctx["factor_notes"]   → human-readable explanation
"""

from __future__ import annotations

from typing import Any

BASELINE_RISK_PCT = 1.23   # Sean's floor — never changes
MIN_RISK_PCT      = 0.50   # absolute floor
MAX_RISK_PCT      = 2.00   # absolute ceiling


# ---------------------------------------------------------------------------
# Factor computations
# ---------------------------------------------------------------------------

def _volatility_factor(atr_pct: float | None) -> tuple[float, str]:
    """
    Volatility factor from ATR% of price.
    High volatility = reduce risk (harder to predict direction).
    Normal volatility = full risk.
    Low volatility trending = slight increase (smoother moves).
    """
    if atr_pct is None:
        return 0.8, "ATR unknown — applying caution"
    if atr_pct >= 0.015:   # > 1.5% — very high volatility
        return 0.5, f"ATR%={atr_pct:.3f}% very high — reduce risk significantly"
    if atr_pct >= 0.010:   # 1.0-1.5%
        return 0.7, f"ATR%={atr_pct:.3f}% elevated — moderate risk reduction"
    if atr_pct >= 0.006:   # 0.6-1.0% — normal expanded
        return 1.0, f"ATR%={atr_pct:.3f}% normal expanded — full baseline"
    if atr_pct >= 0.003:   # 0.3-0.6% — normal
        return 1.0, f"ATR%={atr_pct:.3f}% normal — full baseline"
    # < 0.3% — very quiet, trending smoothly
    return 1.1, f"ATR%={atr_pct:.3f}% quiet — slight increase for smooth trend"


def _structure_factor(regime: str, swing_structure: str | None) -> tuple[float, str]:
    """
    Structure factor from regime and swing structure.
    Ranging/chop = reduce risk.
    Confirmed trend (HH_HL or LH_LL) = increase risk.
    """
    if regime == "ranging" or regime == "unknown":
        return 0.6, f"Regime={regime} — reduce risk, no directional edge"
    if swing_structure == "HH_HL" and regime == "trending_up":
        return 1.3, "HH_HL swing structure + trending_up — strong trend confirmed"
    if swing_structure == "LH_LL" and regime == "trending_down":
        return 1.3, "LH_LL swing structure + trending_down — strong trend confirmed"
    if regime in ("trending_up", "trending_down") and swing_structure in ("HH_HL", "LH_LL"):
        return 1.2, f"Trend confirmed by swing structure {swing_structure}"
    if regime in ("trending_up", "trending_down"):
        return 1.0, f"Regime={regime} trend present, swing not fully confirmed"
    if regime == "volatile":
        return 0.8, "Volatile regime — structure unclear, moderate reduction"
    return 0.9, f"Regime={regime} — mild caution"


def _signal_factor(confidence_spread: float | None) -> tuple[float, str]:
    """
    Signal factor from R-002 confidence spread.
    Minimum spread 0.20 (R-002 gate) maps to 0.6.
    Strong spread 0.50+ maps to 1.5.
    """
    if confidence_spread is None:
        return 0.7, "Confidence spread unknown — applying caution"
    if confidence_spread < 0.20:
        return 0.0, f"Spread={confidence_spread:.2f} below R-002 minimum — NO TRADE"
    if confidence_spread < 0.25:
        return 0.65, f"Spread={confidence_spread:.2f} minimal conviction — reduce risk"
    if confidence_spread < 0.30:
        return 0.80, f"Spread={confidence_spread:.2f} moderate conviction"
    if confidence_spread < 0.40:
        return 1.00, f"Spread={confidence_spread:.2f} good conviction — full baseline"
    if confidence_spread < 0.50:
        return 1.20, f"Spread={confidence_spread:.2f} strong conviction — increase risk"
    return 1.50, f"Spread={confidence_spread:.2f} very strong conviction — significant increase"


def _session_factor(utc_hour: int | None) -> tuple[float, str]:
    """
    Session factor from UTC hour.
    Asian session (00:00-13:00 UTC) = low liquidity = reduce risk.
    US/EU overlap (13:00-20:00 UTC) = peak liquidity = full risk.
    US late (20:00-24:00) = acceptable.
    """
    if utc_hour is None:
        return 0.9, "Session time unknown — slight caution"
    if 0 <= utc_hour < 7:
        return 0.6, f"UTC {utc_hour:02d}:00 deep Asian session — low liquidity"
    if 7 <= utc_hour < 13:
        return 0.75, f"UTC {utc_hour:02d}:00 late Asian session — improving liquidity"
    if 13 <= utc_hour < 17:
        return 1.1, f"UTC {utc_hour:02d}:00 US/EU overlap peak — best liquidity"
    if 17 <= utc_hour < 20:
        return 1.0, f"UTC {utc_hour:02d}:00 US session — good liquidity"
    return 0.9, f"UTC {utc_hour:02d}:00 US late / extended hours — acceptable"


def _health_factor(
    pattern_win_rate: float | None,
    recent_losses: int,
    recent_wins: int,
) -> tuple[float, str]:
    """
    Health factor from pattern win rate and recent trade performance.
    Combines: how has this specific pattern performed + recent system health.
    """
    # Recent performance component (last N trades)
    total_recent = recent_losses + recent_wins
    if total_recent >= 3:
        recent_wr = recent_wins / total_recent
        if recent_losses >= 3:
            perf = 0.5
            perf_note = f"3+ recent losses ({recent_losses}L/{recent_wins}W) — reduce risk"
        elif recent_losses >= 2:
            perf = 0.75
            perf_note = f"2 recent losses ({recent_losses}L/{recent_wins}W) — mild reduction"
        elif recent_wins >= 3 and recent_losses == 0:
            perf = 1.2
            perf_note = f"Winning streak {recent_wins}W/{recent_losses}L — increase"
        else:
            perf = 1.0
            perf_note = f"Mixed recent ({recent_losses}L/{recent_wins}W) — neutral"
    else:
        perf = 1.0
        perf_note = "Insufficient recent trades for adjustment"

    # Pattern win rate component
    if pattern_win_rate is None:
        pat = 0.9
        pat_note = "No pattern win rate — new pattern, slight caution"
    elif pattern_win_rate >= 0.70:
        pat = 1.2
        pat_note = f"Pattern win rate {pattern_win_rate:.0%} — strong pattern"
    elif pattern_win_rate >= 0.55:
        pat = 1.0
        pat_note = f"Pattern win rate {pattern_win_rate:.0%} — solid pattern"
    elif pattern_win_rate >= 0.40:
        pat = 0.8
        pat_note = f"Pattern win rate {pattern_win_rate:.0%} — marginal pattern"
    else:
        pat = 0.5
        pat_note = f"Pattern win rate {pattern_win_rate:.0%} — weak pattern"

    combined = round((perf + pat) / 2, 4)
    return combined, f"{perf_note} | {pat_note}"


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_risk_context(
    *,
    atr_pct: float | None = None,
    regime: str = "unknown",
    swing_structure: str | None = None,
    confidence_spread: float | None = None,
    utc_hour: int | None = None,
    pattern_win_rate: float | None = None,
    recent_losses: int = 0,
    recent_wins: int = 0,
    action: str = "NO_TRADE",
) -> dict[str, Any]:
    """
    Compute the full risk context for a decision.

    Returns:
      baseline_risk_pct: always 1.23
      volatility_factor, structure_factor, signal_factor, session_factor, health_factor
      final_risk_pct: bounded [MIN_RISK_PCT, MAX_RISK_PCT] or 0.0 for NO_TRADE
      no_trade_blocked: True if any factor forces no-trade
      factor_notes: human-readable explanation of each factor
      recommended_risk_pct: same as final_risk_pct (for signal contract)
    """
    vol_f,  vol_note  = _volatility_factor(atr_pct)
    str_f,  str_note  = _structure_factor(regime, swing_structure)
    sig_f,  sig_note  = _signal_factor(confidence_spread)
    ses_f,  ses_note  = _session_factor(utc_hour)
    hlt_f,  hlt_note  = _health_factor(pattern_win_rate, recent_losses, recent_wins)

    # Signal factor of 0.0 means R-002 gate not met — force no-trade
    no_trade_blocked = sig_f == 0.0 or action == "NO_TRADE" or action == "INSUFFICIENT_DATA"

    if no_trade_blocked:
        final_risk = 0.0
    else:
        raw = BASELINE_RISK_PCT * vol_f * str_f * sig_f * ses_f * hlt_f
        final_risk = round(max(MIN_RISK_PCT, min(MAX_RISK_PCT, raw)), 4)

    return {
        "baseline_risk_pct": BASELINE_RISK_PCT,
        "volatility_factor": round(vol_f, 4),
        "structure_factor": round(str_f, 4),
        "signal_factor": round(sig_f, 4),
        "session_factor": round(ses_f, 4),
        "health_factor": round(hlt_f, 4),
        "raw_computed_pct": round(BASELINE_RISK_PCT * vol_f * str_f * sig_f * ses_f * hlt_f, 4) if not no_trade_blocked else 0.0,
        "final_risk_pct": final_risk,
        "recommended_risk_pct": final_risk,
        "risk_bounds": {"min": MIN_RISK_PCT, "max": MAX_RISK_PCT},
        "no_trade_blocked": no_trade_blocked,
        "factor_notes": {
            "volatility": vol_note,
            "structure":  str_note,
            "signal":     sig_note,
            "session":    ses_note,
            "health":     hlt_note,
        },
    }


def risk_context_summary(ctx: dict[str, Any]) -> str:
    """One-line human-readable summary for prompt embedding."""
    if ctx["no_trade_blocked"]:
        return f"Risk: NO DEPLOY (blocked). {ctx['factor_notes']['signal']}"
    pct = ctx["final_risk_pct"]
    direction = "above" if pct > BASELINE_RISK_PCT else "below" if pct < BASELINE_RISK_PCT else "at"
    return (
        f"Risk: {pct:.2f}% of wallet ({direction} {BASELINE_RISK_PCT}% baseline). "
        f"Vol={ctx['volatility_factor']:.2f} × "
        f"Struct={ctx['structure_factor']:.2f} × "
        f"Signal={ctx['signal_factor']:.2f} × "
        f"Session={ctx['session_factor']:.2f} × "
        f"Health={ctx['health_factor']:.2f}"
    )
