"""Tests for risk_context.py — context-as-risk-management module."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from risk_context import compute_risk_context, risk_context_summary, BASELINE_RISK_PCT, MIN_RISK_PCT, MAX_RISK_PCT


def test_baseline_never_changes():
    assert BASELINE_RISK_PCT == 1.23


def test_no_trade_gives_zero_risk():
    ctx = compute_risk_context(action="NO_TRADE")
    assert ctx["final_risk_pct"] == 0.0
    assert ctx["no_trade_blocked"] is True


def test_insufficient_data_gives_zero_risk():
    ctx = compute_risk_context(action="INSUFFICIENT_DATA")
    assert ctx["final_risk_pct"] == 0.0


def test_spread_below_r002_blocks_trade():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        confidence_spread=0.15,  # below 0.20 R-002 floor
    )
    assert ctx["final_risk_pct"] == 0.0
    assert ctx["no_trade_blocked"] is True


def test_strong_conditions_increase_risk():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        atr_pct=0.005,             # normal
        regime="trending_up",
        swing_structure="HH_HL",
        confidence_spread=0.50,    # strong conviction
        utc_hour=15,               # peak liquidity
        pattern_win_rate=0.70,
        recent_losses=0,
        recent_wins=4,
    )
    assert ctx["final_risk_pct"] > BASELINE_RISK_PCT
    assert ctx["no_trade_blocked"] is False


def test_weak_conditions_reduce_risk():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        atr_pct=0.020,             # very high volatility
        regime="ranging",
        confidence_spread=0.22,    # just above minimum
        utc_hour=3,                # deep Asian session
        pattern_win_rate=0.35,
        recent_losses=3,
        recent_wins=0,
    )
    assert ctx["final_risk_pct"] < BASELINE_RISK_PCT
    assert ctx["final_risk_pct"] >= MIN_RISK_PCT


def test_risk_bounded_by_min():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        atr_pct=0.020,
        regime="ranging",
        confidence_spread=0.21,
        utc_hour=2,
        pattern_win_rate=0.30,
        recent_losses=3,
    )
    assert ctx["final_risk_pct"] >= MIN_RISK_PCT


def test_risk_bounded_by_max():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        atr_pct=0.001,
        regime="trending_up",
        swing_structure="HH_HL",
        confidence_spread=0.80,
        utc_hour=15,
        pattern_win_rate=0.90,
        recent_losses=0,
        recent_wins=10,
    )
    assert ctx["final_risk_pct"] <= MAX_RISK_PCT


def test_all_factors_present():
    ctx = compute_risk_context(action="ENTER_LONG", confidence_spread=0.35)
    for key in ("baseline_risk_pct", "volatility_factor", "structure_factor",
                "signal_factor", "session_factor", "health_factor",
                "final_risk_pct", "recommended_risk_pct", "factor_notes",
                "no_trade_blocked"):
        assert key in ctx


def test_summary_no_trade():
    ctx = compute_risk_context(action="NO_TRADE")
    summary = risk_context_summary(ctx)
    assert "NO DEPLOY" in summary


def test_summary_entry():
    ctx = compute_risk_context(
        action="ENTER_LONG",
        confidence_spread=0.40,
        regime="trending_up",
    )
    summary = risk_context_summary(ctx)
    assert "%" in summary
    assert "Vol=" in summary


def test_peak_liquidity_factor():
    ctx_peak = compute_risk_context(action="ENTER_LONG", confidence_spread=0.35, utc_hour=15)
    ctx_asian = compute_risk_context(action="ENTER_LONG", confidence_spread=0.35, utc_hour=3)
    assert ctx_peak["session_factor"] > ctx_asian["session_factor"]


def test_winning_streak_increases_health():
    ctx_streak = compute_risk_context(action="ENTER_LONG", confidence_spread=0.35,
                                      recent_wins=5, recent_losses=0)
    ctx_losses = compute_risk_context(action="ENTER_LONG", confidence_spread=0.35,
                                      recent_wins=0, recent_losses=3)
    assert ctx_streak["health_factor"] > ctx_losses["health_factor"]
