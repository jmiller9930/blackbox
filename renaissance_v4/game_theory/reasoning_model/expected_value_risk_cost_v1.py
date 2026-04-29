"""
GT_DIRECTIVE_032 — Expected value / risk-cost layer v1 (deterministic, bounded, auditable).

Consumes Directive 3 ``pattern_memory_eval_v1`` outcomes + ``perps_state_model_v1`` + ``risk_inputs_v1``.
Does not duplicate similarity search — uses ``pattern_outcome_stats_v1`` from pattern memory eval only.
"""

from __future__ import annotations

import os
from typing import Any

SCHEMA_EXPECTED_VALUE_RISK_COST_V1 = "expected_value_risk_cost_v1"


def ev_game_min_sample_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_EV_MIN_SAMPLE_V1") or "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 256))
        except ValueError:
            pass
    from renaissance_v4.game_theory.reasoning_model.pattern_memory_v1 import pattern_memory_min_sample_v1

    return pattern_memory_min_sample_v1()


def ev_pnl_scale_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_EV_PNL_SCALE_V1") or "50.0").strip()
    try:
        s = float(raw)
    except ValueError:
        s = 50.0
    return max(1e-6, s)


def _volatility_penalty_v1(volatility_state: str) -> float:
    vs = str(volatility_state or "").strip()
    if vs == "high_volatility":
        return 0.06
    return 0.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_expected_value_risk_cost_v1(
    *,
    perps_state_model_v1: dict[str, Any],
    pattern_memory_eval_v1: dict[str, Any],
    risk_inputs_v1: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic EV(long/short/no_trade). Does not invent funding/liquidation; marks not_available_v1.
    """
    ps = perps_state_model_v1 if isinstance(perps_state_model_v1, dict) else {}
    pm = pattern_memory_eval_v1 if isinstance(pattern_memory_eval_v1, dict) else {}
    _risk = risk_inputs_v1 if isinstance(risk_inputs_v1, dict) else {}

    basis_v1 = {
        "pattern_memory_used_v1": bool(pm.get("schema") == "pattern_memory_eval_v1"),
        "state_used_v1": bool(ps.get("schema") == "perps_state_model_v1"),
        "funding_used_v1": False,
        "liquidation_used_v1": False,
    }

    vol_pen = _volatility_penalty_v1(str(ps.get("volatility_state") or ""))
    risk_costs_v1: dict[str, Any] = {
        "funding_cost_v1": "not_available_v1",
        "volatility_penalty_v1": round(vol_pen, 6),
        "liquidation_risk_penalty_v1": "not_available_v1",
        "holding_cost_v1": "not_available_v1",
    }

    stats = pm.get("pattern_outcome_stats_v1") if isinstance(pm.get("pattern_outcome_stats_v1"), dict) else {}
    n = int(stats.get("count") or 0)
    min_n = ev_game_min_sample_v1()

    reason_codes_v1: list[str] = []
    if str(pm.get("disabled_reason_v1") or "").strip():
        reason_codes_v1.append("pattern_memory_disabled_v1")

    if n < min_n:
        reason_codes_v1.append("insufficient_sample_v1")
        inner = {
            "schema": SCHEMA_EXPECTED_VALUE_RISK_COST_V1,
            "available_v1": False,
            "ev_long_v1": 0.0,
            "ev_short_v1": 0.0,
            "ev_no_trade_v1": 0.0,
            "ev_best_value_v1": 0.0,
            "preferred_action_v1": "not_available_v1",
            "sample_count_v1": n,
            "basis_v1": basis_v1,
            "risk_costs_v1": risk_costs_v1,
            "confidence_01": 0.0,
            "reason_codes_v1": reason_codes_v1,
        }
        return inner

    avg_pnl = float(stats.get("avg_pnl") or 0.0)
    wr = float(stats.get("wins_total_fraction_v1") or 0.0)
    scale = ev_pnl_scale_v1()
    # Normalized pooled signal from historical similar-pattern PnL + win rate (bounded).
    pooled = _clamp(avg_pnl / scale, -2.0, 2.0) * 0.65 + _clamp((wr - 0.5) * 2.0, -1.0, 1.0) * 0.35

    ts = str(ps.get("trend_state") or "neutral")
    if ts == "bullish_trend":
        ev_long_v1 = round(pooled - vol_pen, 6)
        ev_short_v1 = round(-_clamp(abs(pooled), 0.0, 2.0) * 0.75 - vol_pen, 6)
    elif ts == "bearish_trend":
        ev_short_v1 = round(pooled - vol_pen, 6)
        ev_long_v1 = round(-_clamp(abs(pooled), 0.0, 2.0) * 0.75 - vol_pen, 6)
    else:
        ev_long_v1 = round(pooled * 0.55 - vol_pen, 6)
        ev_short_v1 = round((-pooled) * 0.55 - vol_pen, 6)

    ev_no_trade_v1 = round(0.0 - vol_pen * 0.25, 6)

    cand = [
        ("enter_long", ev_long_v1),
        ("enter_short", ev_short_v1),
        ("no_trade", ev_no_trade_v1),
    ]
    _prio = {"enter_long": 0, "enter_short": 1, "no_trade": 2}
    preferred = str(max(cand, key=lambda t: (t[1], -_prio[str(t[0])]))[0])

    # Confidence rises modestly with sample depth (deterministic cap).
    conf = _clamp(0.35 + 0.045 * min(n, 12) + (0.02 if vol_pen == 0 else 0.0), 0.0, 1.0)

    ev_best_value_v1 = round(max(ev_long_v1, ev_short_v1, ev_no_trade_v1), 6)

    inner = {
        "schema": SCHEMA_EXPECTED_VALUE_RISK_COST_V1,
        "available_v1": True,
        "ev_long_v1": ev_long_v1,
        "ev_short_v1": ev_short_v1,
        "ev_no_trade_v1": ev_no_trade_v1,
        "ev_best_value_v1": ev_best_value_v1,
        "preferred_action_v1": preferred,
        "sample_count_v1": n,
        "basis_v1": basis_v1,
        "risk_costs_v1": risk_costs_v1,
        "confidence_01": round(conf, 6),
        "reason_codes_v1": reason_codes_v1,
    }
    return inner


def compute_ev_score_adjustment_v1(
    *,
    expected_value_risk_cost_v1: dict[str, Any],
    synthesized_action_v1: str,
) -> float:
    """
    Bounded [-0.12, 0.12] nudge when EV available and agrees/disagrees with synthesized action.
    No adjustment when unavailable or insufficient_sample.
    """
    ev = expected_value_risk_cost_v1 if isinstance(expected_value_risk_cost_v1, dict) else {}
    if not ev.get("available_v1"):
        return 0.0
    if "insufficient_sample_v1" in list(ev.get("reason_codes_v1") or []):
        return 0.0
    pref = str(ev.get("preferred_action_v1") or "").strip()
    act = str(synthesized_action_v1 or "").strip()
    if pref in ("", "not_available_v1"):
        return 0.0

    cap = 0.12
    if pref == act:
        return round(0.06, 6)
    # directional mismatch
    dir_set = {"enter_long", "enter_short"}
    if pref in dir_set and act in dir_set and pref != act:
        return round(-0.08, 6)
    if pref == "no_trade" and act in dir_set:
        return round(-0.06, 6)
    if pref in dir_set and act == "no_trade":
        return round(-0.04, 6)
    return round(-0.02, 6)


def apply_ev_decision_gate_v1(
    *,
    action_current: str,
    expected_value_risk_cost_v1: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    GT_DIRECTIVE_043 — When EV is available, gate directional trades to EV preference or no_trade.

    Does not alter scores/thresholds; action-only override after synthesis + EV score nudge.
    """
    ev = expected_value_risk_cost_v1 if isinstance(expected_value_risk_cost_v1, dict) else {}
    act0 = str(action_current or "").strip()
    if act0 not in ("enter_long", "enter_short", "no_trade"):
        act0 = "no_trade"

    audit: dict[str, Any] = {
        "schema": "ev_decision_gate_v1",
        "applied_v1": False,
        "prior_action_v1": act0,
        "post_action_v1": act0,
        "wrong_direction_blocked_v1": False,
        "forced_no_trade_ev_v1": False,
    }

    if not ev.get("available_v1"):
        return act0, audit

    pref = str(ev.get("preferred_action_v1") or "").strip()
    el = float(ev.get("ev_long_v1") or 0.0)
    es = float(ev.get("ev_short_v1") or 0.0)
    en = float(ev.get("ev_no_trade_v1") or 0.0)
    raw_best = ev.get("ev_best_value_v1")
    if raw_best is None:
        ev_best = max(el, es, en)
    else:
        ev_best = float(raw_best)

    audit["applied_v1"] = True
    post = act0

    if pref == "no_trade" or ev_best <= 0.0:
        post = "no_trade"
        if act0 != "no_trade":
            audit["forced_no_trade_ev_v1"] = True
    elif pref == "enter_long":
        if act0 == "enter_short":
            post = "no_trade"
            audit["wrong_direction_blocked_v1"] = True
    elif pref == "enter_short":
        if act0 == "enter_long":
            post = "no_trade"
            audit["wrong_direction_blocked_v1"] = True

    audit["post_action_v1"] = post
    return post, audit


__all__ = [
    "SCHEMA_EXPECTED_VALUE_RISK_COST_V1",
    "apply_ev_decision_gate_v1",
    "compute_ev_score_adjustment_v1",
    "compute_expected_value_risk_cost_v1",
    "ev_game_min_sample_v1",
]
