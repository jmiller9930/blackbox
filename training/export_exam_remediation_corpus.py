#!/usr/bin/env python3
"""
FinQuant exam remediation corpus generator.

Generates ~100 targeted finquant_agentic_qa_v1 gold rows covering the 5
hard failure categories identified by the adversarial exam v3 (2026-05-05):

  1. ATR hard rule     (atr_ratio_14_50 > 1.35 → NO_TRADE, both long and short)
  2. Lookahead leakage (future bar in context → FAIL + Leakage_check=FAIL)
  3. Same-bar kill     (SL and TP same bar → FAIL)
  4. Funding sign      (positive rate = longs pay → reject false bullish claim)
  5. Abstention        (missing ATR/fields → INSUFFICIENT_DATA)

Output: training/remediation_corpus_v0.3.jsonl  (tracked in repo)
        Also prints merge command to build merged_finquant_v0.3.jsonl on trx40.

Usage (from repo root):
  python3 training/export_exam_remediation_corpus.py --out training/remediation_corpus_v0.3.jsonl
  python3 training/validate_agentic_corpus_v1.py training/remediation_corpus_v0.3.jsonl

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
from training.risk_context_contract import build_risk_context_for_gold

POLICY_ID = "jupiter_2_sean_perps_v1"
EXAM_SCHEMA = "finquant_quant_exam_v1"
TRAINING_SCHEMA = "finquant_agentic_qa_v1"
INSTRUCTION = (
    "You are FinQuant. Use ONLY reference_facts_v1, case_assumptions_v1, "
    "context_inventory_v1, and retrieved_memory_v1. Decision applies to the LAST bar "
    "(decision_bar_index_in_window). Produce strict JSON per gold contract."
)
BASE_ASSUMPTIONS = {
    "symbol": "SOL-PERP",
    "policy_id": POLICY_ID,
    "risk_pct_equity": 0.01,
    "equity_usd": 10000,
    "planned_stop_atr_multiple": 1.6,
    "planned_target_atr_multiple": 4.0,
    "fee_per_side_bps": 5,
    "slippage_band_bps": 10,
    "estimated_round_trip_friction_bps": 30,
    "fill_latency_class": "interactive_market_order",
    "economics_notes": "estimated_round_trip_friction_bps = 2×fee_per_side_bps + 2×slippage_band_bps.",
    "atr_hard_limit_note": "atr_ratio_14_50 > 1.35 → MUST return NO_TRADE. No exceptions.",
}


def _gold_output(
    final_status: str,
    claim_reviewed: str,
    math_verdict: str,
    numeric_answer: float | None,
    leakage_check: str,
    policy_alignment: str,
    data_gaps: str,
    regime: str = "unknown",
    conf_gap: float = 0.30,
    atr_pct: float | None = None,
    hypotheses: list[dict] | None = None,
    blocking_rules: list[str] | None = None,
    setup_sig: str = "remediation_case",
    rule_checks: dict | None = None,
) -> dict[str, Any]:
    rc, rec_pct = build_risk_context_for_gold(
        final_status, conf_gap=conf_gap, regime=regime,
        atr_pct=atr_pct, i_dont_know=(conf_gap < 0.20),
        baseline_risk_pct=1.0,
    )
    if hypotheses is None:
        hypotheses = [
            {"id": "H1_primary", "claim": "Primary thesis.", "supporting_evidence": [], "counter_evidence": [], "confidence": 0.60},
            {"id": "H2_counter", "claim": "Counter thesis.", "supporting_evidence": [], "counter_evidence": [], "confidence": 0.30},
        ]
    if rule_checks is None:
        atr_ok = atr_pct is None or True  # caller knows what atr ratio is
        rule_checks = {
            "atr_filter_passed": final_status != "NO_TRADE" or conf_gap > 0.20,
            "spread_liquidity_ok": True,
            "data_quality_passed": final_status != "INSUFFICIENT_DATA",
            "confidence_gap_passed": conf_gap >= 0.20,
        }

    return {
        "context_observed_v1": {"trend_regime": regime, "volatility_regime": "atr_dependent", "structure_proxy": "remediation_case", "recency_note": "generated_for_training"},
        "context_evidence_v1": [f"final_status={final_status}", f"conf_gap={conf_gap}"],
        "context_uncertainty_v1": ["Generated remediation row."],
        "hypotheses_v1": hypotheses,
        "dominant_hypothesis_v1": hypotheses[0]["id"] if conf_gap >= 0.20 else None,
        "confidence_gap_v1": conf_gap,
        "i_dont_know_triggered": conf_gap < 0.20,
        "deterministic_baseline_verdict_v1": {
            "policy_id": POLICY_ID,
            "verdict": final_status,
            "blocking_rules": blocking_rules or [],
        },
        "model_independent_assessment_v1": {
            "stance": f"agree_with_{final_status.lower()}",
            "reasoning": policy_alignment,
            "would_veto_a_rule_pass": final_status in ("NO_TRADE", "INSUFFICIENT_DATA", "FAIL"),
            "would_override_a_rule_block": False,
        },
        "threshold_adjustment_proposal_v1": {"proposed_change": "no_change", "direction": "no_change", "evidence_memory_ids": [], "evidence_summary": "", "applied_to_this_case": False, "applied_to_this_case_reason": "Remediation exemplar."},
        "learning_record_candidate_v1": {"setup_signature": setup_sig, "decision_taken": final_status, "lesson_if_win": "n/a", "lesson_if_loss": "n/a", "promotion_candidate": False, "do_not_promote_reason": "Remediation exemplar — not a live outcome row."},
        "expectancy_check_v1": {"planned_r_multiple": 2.5, "planned_risk_dollars": 100.0, "planned_target_dollars": 250.0, "breakeven_win_rate_required": 0.2857, "this_setup_estimated_win_rate": None, "expectancy_per_trade_dollars": None, "contributes_to_long_run_math": False, "note": "Remediation: no entry."},
        "risk_context_v1": rc,
        "recommended_risk_pct": rec_pct,
        "context_decision_link_v1": f"{regime} + deterministic rule → {final_status}",
        "lifecycle_state_v1": "no_trade" if final_status != "ENTER_LONG" else "trade",
        "Claim_reviewed": claim_reviewed,
        "Math_verdict": math_verdict,
        "Numeric_answer": numeric_answer,
        "Leakage_check": leakage_check,
        "Policy_alignment": policy_alignment,
        "DATA_or_assumption_gaps": data_gaps,
        "Final_status": final_status,
        "rule_checks": rule_checks,
    }


def _row(case_id: str, category: str, tags: list[str], ref_facts: dict, output: dict, extra_assumptions: dict | None = None) -> dict[str, Any]:
    assumptions = dict(BASE_ASSUMPTIONS)
    if extra_assumptions:
        assumptions.update(extra_assumptions)
    return {
        "case_id": case_id,
        "exam_schema": EXAM_SCHEMA,
        "exam_version": 3,
        "training_schema": TRAINING_SCHEMA,
        "primary_category": category,
        "secondary_tags": tags,
        "instruction": INSTRUCTION,
        "input": {
            "case_assumptions_v1": assumptions,
            "reference_facts_v1": ref_facts,
            "context_inventory_v1": {"bars_in_window": 3, "decision_bar_index_in_window": 2, "window_bar_source": "remediation_generated", "has_declared_economics": True, "has_funding_oi_in_packet": False},
            "retrieved_memory_v1": [],
        },
        "output": output,
        "grading_v1": {"kind": "deterministic_jsonpath_v1", "rules": [{"id": "final_status_check", "path": "$.Final_status", "expect_equals": output["Final_status"]}]},
    }


def _bars(close: float, atr: float, rng: random.Random) -> list[dict]:
    return [
        {"candle_open_utc": f"2026-05-01T10:00:00Z", "open": round(close - atr * 0.3, 4), "high": round(close + atr * 0.5, 4), "low": round(close - atr * 0.6, 4), "close": round(close - atr * 0.1, 4)},
        {"candle_open_utc": f"2026-05-01T10:15:00Z", "open": round(close - atr * 0.1, 4), "high": round(close + atr * 0.4, 4), "low": round(close - atr * 0.4, 4), "close": round(close + atr * 0.05, 4)},
        {"candle_open_utc": f"2026-05-01T10:30:00Z", "open": round(close + atr * 0.05, 4), "high": round(close + atr * 0.3, 4), "low": round(close - atr * 0.2, 4), "close": close},
    ]


def generate_atr_hard_rule(rng: random.Random) -> list[dict[str, Any]]:
    """30 rows: ATR ratio > 1.35 → NO_TRADE. Various RSI, EMA combos that look tradeable."""
    rows = []
    variants = [
        (148.50, 1.36, 56.0, True, "long"),   # just over limit, bullish RSI, long signal
        (152.00, 1.42, 54.5, True, "long"),   # clearly over limit
        (149.80, 1.38, 58.0, True, "long"),   # EMA bullish stack
        (145.20, 1.50, 52.0, True, "long"),   # extreme ATR, mid RSI
        (155.00, 1.37, 60.0, True, "long"),   # RSI approaching strength
        (148.00, 1.40, 42.0, False, "short"),  # bearish RSI, ATR blocks short too
        (150.00, 1.45, 38.0, False, "short"),  # strong bearish signal, still blocked
        (147.00, 1.61, 55.0, True, "long"),   # very high ATR
        (153.00, 1.36, 57.0, True, "long"),   # boundary +0.01
        # Allow cases just below limit (atr_ratio 1.33, 1.34 → allowed)
        (148.00, 1.33, 56.0, True, "allow_long"),
        (150.00, 1.34, 54.0, True, "allow_long"),
        # More block cases
        (146.00, 1.55, 63.0, True, "long"),
        (148.50, 1.39, 55.0, True, "long"),
        (149.00, 1.43, 50.0, False, "neutral"),
        (152.50, 1.48, 45.0, False, "short"),
        # Short side blocks
        (144.00, 1.36, 41.0, False, "short"),
        (141.00, 1.40, 38.0, False, "short"),
        (139.00, 1.52, 36.0, False, "short"),
        # Mid-zone blocks
        (147.00, 1.37, 50.5, True, "long"),
        (148.00, 1.44, 49.5, False, "neutral"),
        # More allow cases (1.34) to teach boundary
        (149.50, 1.34, 57.0, True, "allow_long"),
        (151.00, 1.30, 55.0, True, "allow_long"),
        # High ATR extreme
        (155.00, 1.70, 62.0, True, "long"),
        (144.00, 1.90, 40.0, False, "short"),
        # Boundary at exactly 1.35
        (148.00, 1.35, 56.0, True, "block_long"),  # 1.35 is at limit → NO_TRADE
        (148.00, 1.35, 42.0, False, "block_short"),
        # More allow
        (147.00, 1.20, 56.0, True, "allow_long"),
        (150.00, 1.10, 54.0, True, "allow_long"),
        # Just-over with multiple bullish signals
        (153.00, 1.36, 58.0, True, "long"),
        (151.50, 1.37, 57.5, True, "long"),
    ]
    for i, (close, atr_ratio, rsi, bull, intent) in enumerate(variants):
        atr14 = round(close * atr_ratio * 0.015, 4)
        atr50 = round(atr14 / atr_ratio, 4)
        is_allow = intent.startswith("allow")
        is_block = atr_ratio >= 1.35
        final_status = "NO_TRADE" if is_block else ("ENTER_LONG" if bull else "NO_TRADE")
        conf_gap = 0.32 if is_allow else 0.28
        ema20 = round(close * 1.005 if bull else close * 0.995, 2)
        ema50 = round(close * 0.99 if bull else close * 1.01, 2)
        atr_pct = round((atr14 / close) * 100, 3)
        blocking = ["ATR_ratio_14_50_exceeds_hard_limit_1.35"] if is_block else []
        rule_checks = {
            "atr_filter_passed": not is_block,
            "spread_liquidity_ok": True,
            "data_quality_passed": True,
            "confidence_gap_passed": conf_gap >= 0.20,
        }
        policy = (
            f"ATR ratio {atr_ratio} exceeds hard limit 1.35 — NO_TRADE mandatory regardless of RSI={rsi:.1f} or EMA alignment."
            if is_block else
            f"ATR ratio {atr_ratio} within limit — other gates checked; Final_status={final_status}."
        )
        output = _gold_output(
            final_status=final_status,
            claim_reviewed=f"ATR ratio {atr_ratio} vs hard limit 1.35; RSI={rsi}; {'bullish' if bull else 'bearish'} signal context.",
            math_verdict=f"atr_ratio_14_50={atr_ratio} {'> 1.35 → hard NO_TRADE' if is_block else '≤ 1.34 → rule passes'}.",
            numeric_answer=None,
            leakage_check="PASS",
            policy_alignment=policy,
            data_gaps="Three-bar window; decision is last bar only.",
            regime="volatile" if atr_ratio > 1.5 else "trending",
            conf_gap=conf_gap,
            atr_pct=atr_pct,
            blocking_rules=blocking,
            setup_sig=f"atr_rule_{'block' if is_block else 'allow'}_{i:02d}",
            rule_checks=rule_checks,
        )
        rows.append(_row(
            case_id=f"FQ-REM-ATR-{i+1:03d}",
            category="indicator_interpretation_rsi_ema_atr",
            tags=["atr_hard_rule", "remediation", "allow" if is_allow else "block"],
            ref_facts={
                "bars_recent_oldest_to_newest": _bars(close, atr14, rng),
                "indicator_values_at_close": {
                    "rsi14": rsi, "ema20": ema20, "ema50": ema50,
                    "atr14": atr14, "atr_pct": atr_pct, "atr_ratio_14_50": atr_ratio,
                },
                "lifecycle_state_prior": "no_trade",
                "decision_bar_index_in_window": 2,
                "perp_context_v1": {"funding_rate_bucket": "not_in_packet", "oi_change_bucket": "not_in_packet", "vol_stress_bucket": "not_in_packet"},
            },
            output=output,
        ))
    return rows


def generate_lookahead(rng: random.Random) -> list[dict[str, Any]]:
    """15 rows: future bar leak in context_note → Final_status=FAIL, Leakage_check=FAIL."""
    rows = []
    for i in range(15):
        close = round(rng.uniform(140.0, 160.0), 2)
        atr14 = round(rng.uniform(1.2, 2.5), 3)
        rsi = round(rng.uniform(50.0, 62.0), 1)
        future_close = round(close + rng.uniform(2.0, 6.0), 2)
        leak_variants = [
            f"Next bar (t+1) closed at {future_close} confirming the breakout.",
            f"Follow-up candle reached {future_close} validating the long thesis.",
            f"Price hit {future_close} on the next 15m bar.",
            f"t+1 close: {future_close}.",
            f"Subsequent bar confirmed at {future_close}.",
        ]
        leak_note = leak_variants[i % len(leak_variants)]
        ema20 = round(close * 1.005, 2)
        ema50 = round(close * 0.992, 2)
        atr_ratio = round(rng.uniform(1.00, 1.28), 3)
        atr_pct = round((atr14 / close) * 100, 3)
        output = _gold_output(
            final_status="FAIL",
            claim_reviewed=f"Packet contains future bar data ({leak_note}). Decision contaminated.",
            math_verdict="Cannot evaluate — packet contains post-decision data.",
            numeric_answer=None,
            leakage_check="FAIL",
            policy_alignment="Lookahead rule violated: context_note contains future close price. Any entry based on this is invalid.",
            data_gaps="Future bar data must not appear in decision packet. Remove and resend.",
            regime="trending",
            conf_gap=0.30,
            atr_pct=atr_pct,
            blocking_rules=["lookahead_detected_in_context_note"],
            setup_sig=f"lookahead_remediation_{i:02d}",
            rule_checks={"atr_filter_passed": True, "spread_liquidity_ok": True, "data_quality_passed": False, "confidence_gap_passed": True},
        )
        output["Leakage_check"] = "FAIL"
        output["Final_status"] = "FAIL"
        rows.append(_row(
            case_id=f"FQ-REM-LEAK-{i+1:03d}",
            category="lookahead_leakage",
            tags=["lookahead", "remediation", "future_bar"],
            ref_facts={
                "bars_recent_oldest_to_newest": _bars(close, atr14, rng),
                "indicator_values_at_close": {"rsi14": rsi, "ema20": ema20, "ema50": ema50, "atr14": atr14, "atr_pct": atr_pct, "atr_ratio_14_50": atr_ratio},
                "lifecycle_state_prior": "no_trade",
                "decision_bar_index_in_window": 2,
                "context_note": leak_note,
                "perp_context_v1": {"funding_rate_bucket": "not_in_packet", "oi_change_bucket": "not_in_packet", "vol_stress_bucket": "not_in_packet"},
            },
            output=output,
        ))
    return rows


def generate_same_bar(rng: random.Random) -> list[dict[str, Any]]:
    """15 rows: SL and TP both hit within same bar → FAIL (SL assumed first)."""
    rows = []
    for i in range(15):
        entry = round(rng.uniform(140.0, 160.0), 2)
        atr14 = round(rng.uniform(1.5, 3.0), 3)
        stop = round(entry - 1.6 * atr14, 2)
        target = round(entry + 4.0 * atr14, 2)
        bar_low = round(stop - rng.uniform(0.1, 0.8), 2)
        bar_high = round(target + rng.uniform(0.1, 0.8), 2)
        loss_per_unit = round(entry - stop, 2)
        output = _gold_output(
            final_status="FAIL",
            claim_reviewed=f"Long entered at {entry}. Same bar hit both SL ({stop}) and TP ({target}). Bar range: H={bar_high} L={bar_low}.",
            math_verdict=f"SL assumed first under same-bar rule. Loss = {loss_per_unit:.2f} per unit. TP hit does NOT count.",
            numeric_answer=round(-loss_per_unit, 2),
            leakage_check="PASS",
            policy_alignment=f"Same-bar rule: when both SL and TP are touched in one bar, SL assumed first. Loss = {loss_per_unit:.2f}. No ambiguity.",
            data_gaps="Single bar outcome provided. Same-bar rule is deterministic.",
            regime="volatile",
            conf_gap=0.30,
            atr_pct=round(atr14 / entry * 100, 3),
            blocking_rules=["same_bar_sl_assumed_first"],
            setup_sig=f"same_bar_kill_{i:02d}",
            rule_checks={"atr_filter_passed": True, "spread_liquidity_ok": True, "data_quality_passed": True, "confidence_gap_passed": True},
        )
        output["Final_status"] = "FAIL"
        rows.append(_row(
            case_id=f"FQ-REM-SAMEBAR-{i+1:03d}",
            category="risk_reward",
            tags=["same_bar_rule", "remediation", "sl_first"],
            ref_facts={
                "bars_recent_oldest_to_newest": [
                    _bars(entry, atr14, rng)[0],
                    _bars(entry, atr14, rng)[1],
                    {"candle_open_utc": "2026-05-01T10:30:00Z", "open": entry, "high": bar_high, "low": bar_low, "close": round((entry + bar_high) / 2, 2)},
                ],
                "indicator_values_at_close": {"rsi14": round(rng.uniform(48.0, 62.0), 1), "ema20": round(entry * 1.003, 2), "ema50": round(entry * 0.993, 2), "atr14": atr14, "atr_pct": round(atr14 / entry * 100, 3), "atr_ratio_14_50": round(rng.uniform(0.95, 1.25), 3)},
                "lifecycle_state_prior": "in_trade",
                "open_position": {"side": "long", "entry_price": entry, "stop": stop, "target": target},
                "decision_bar_index_in_window": 2,
                "same_bar_outcome": {"high": bar_high, "low": bar_low, "stop": stop, "target": target, "rule": "sl_first"},
                "perp_context_v1": {"funding_rate_bucket": "not_in_packet", "oi_change_bucket": "not_in_packet", "vol_stress_bucket": "not_in_packet"},
            },
            output=output,
        ))
    return rows


def generate_funding_sign(rng: random.Random) -> list[dict[str, Any]]:
    """20 rows: funding semantics — positive rate = longs pay; negative = shorts pay."""
    rows = []
    cases = [
        (0.08, "long_pays_short_when_positive", True, "positive funding = LONGS PAY. High positive funding is a carry COST for new longs, not a reward. It signals crowded long positioning. Consider as a headwind."),
        (0.05, "long_pays_short_when_positive", True, "positive funding means longs pay shorts each period. This is a drag on long EV."),
        (0.10, "long_pays_short_when_positive", True, "very high positive funding rate — longs pay 0.10% per period. Significant carry cost."),
        (0.03, "long_pays_short_when_positive", True, "mild positive funding still costs longs. Cannot claim positive funding is bullish for new longs."),
        (-0.05, "long_pays_short_when_positive", False, "negative funding rate means SHORTS PAY longs. This is a carry benefit for longs, cost for shorts."),
        (-0.03, "long_pays_short_when_positive", False, "negative funding: shorts pay. Long carry is positive. Opposite of the bullish narrative trap."),
        (0.07, "long_pays_short_when_positive", True, "positive funding at 0.07% — longs pay. Cannot treat this as confirmation of bull momentum."),
        (0.02, "long_pays_short_when_positive", True, "even small positive funding is a cost to longs over multiple periods."),
        (-0.08, "long_pays_short_when_positive", False, "negative funding strongly favors longs (shorts paying). This IS a tailwind for long carry."),
        (0.04, "long_pays_short_when_positive", True, "positive funding means longs pay. Claim that positive funding is bullish is INCORRECT under this convention."),
        (0.06, "long_pays_short_when_positive", True, "longs pay 0.06% per period. At 3 funding periods per day, carry cost compounds."),
        (-0.04, "long_pays_short_when_positive", False, "negative funding: shorts pay longs. This rewards holding long positions."),
        (0.09, "long_pays_short_when_positive", True, "extreme positive funding. Longs paying this rate for 3 periods = 0.27% drag. Kills marginal trades."),
        (0.01, "long_pays_short_when_positive", True, "even 0.01% positive funding means longs pay. Convention is absolute — not directional narrative."),
        (-0.06, "long_pays_short_when_positive", False, "strongly negative: shorts pay significant carry to longs."),
        (0.08, "long_pays_short_when_positive", True, "false claim test: 'positive funding confirms longs winning'. INCORRECT — positive funding means longs PAY."),
        (0.05, "long_pays_short_when_positive", True, "positive funding at 0.05% is a COST not a reward for longs. Funding sign is arithmetic, not sentiment."),
        (-0.02, "long_pays_short_when_positive", False, "negative: shorts pay longs. Mild but real carry benefit for long holders."),
        (0.12, "long_pays_short_when_positive", True, "highest funding in set. Longs pay 0.12% per 8h. DO NOT interpret as bullish momentum."),
        (0.04, "long_pays_short_when_positive", True, "positive funding = longs pay. This is a contractual arithmetic fact, not interpretation."),
    ]
    for i, (rate, convention, longs_pay, explanation) in enumerate(cases):
        final_status = "FAIL"  # claim that positive=bullish is always FAIL
        if not longs_pay:
            final_status = "NO_TRADE"  # negative funding: longs benefit, but we still don't enter on funding alone
        output = _gold_output(
            final_status=final_status,
            claim_reviewed=f"Funding rate {rate:+.3f}%, convention: {convention}. {'Longs pay shorts.' if longs_pay else 'Shorts pay longs.'}",
            math_verdict=f"{'incorrect' if longs_pay else 'correct'}: funding rate {rate:+.3f}% under '{convention}' means {'longs pay' if longs_pay else 'shorts pay'}. {explanation}",
            numeric_answer=None,
            leakage_check="PASS",
            policy_alignment=explanation,
            data_gaps="Funding rate and convention declared in packet. No ambiguity.",
            regime="trending",
            conf_gap=0.35,
            atr_pct=2.0,
            blocking_rules=["funding_sign_claim_invalid"] if longs_pay else [],
            setup_sig=f"funding_sign_remediation_{i:02d}",
            rule_checks={"atr_filter_passed": True, "spread_liquidity_ok": True, "data_quality_passed": True, "confidence_gap_passed": True},
        )
        rows.append(_row(
            case_id=f"FQ-REM-FUND-{i+1:03d}",
            category="perp_funding_semantics",
            tags=["funding_sign", "remediation", "perp_economics"],
            ref_facts={
                "bars_recent_oldest_to_newest": _bars(148.0, 2.0, rng),
                "indicator_values_at_close": {"rsi14": 55.0, "ema20": 148.5, "ema50": 147.0, "atr14": 2.0, "atr_pct": 1.35, "atr_ratio_14_50": 1.05},
                "lifecycle_state_prior": "no_trade",
                "decision_bar_index_in_window": 2,
                "perp_context_v1": {
                    "funding_rate_pct": rate,
                    "funding_rate_bucket": "high_positive" if rate > 0.05 else ("positive" if rate > 0 else "negative"),
                    "convention": convention,
                    "oi_change_bucket": "not_in_packet",
                    "vol_stress_bucket": "not_in_packet",
                },
            },
            output=output,
        ))
    return rows


def generate_abstention(rng: random.Random) -> list[dict[str, Any]]:
    """20 rows: missing critical fields → INSUFFICIENT_DATA."""
    rows = []
    missing_variants = [
        ({"rsi14": 54.0, "ema20": 148.0}, "atr14, atr_ratio_14_50, ema50"),
        ({"rsi14": 56.0, "ema50": 145.0}, "atr14, atr_ratio_14_50, ema20"),
        ({"ema20": 148.0, "ema50": 146.0}, "rsi14, atr14, atr_ratio_14_50"),
        ({"rsi14": 52.0}, "atr14, atr_ratio_14_50, ema20, ema50"),
        ({"atr14": 1.5, "rsi14": 55.0}, "ema20, ema50, atr_ratio_14_50"),
        ({"rsi14": 58.0, "ema20": 149.0, "ema50": 147.0}, "atr14, atr_ratio_14_50"),
        ({"atr14": 2.0, "atr_ratio_14_50": 1.05}, "rsi14, ema20, ema50"),
        ({}, "rsi14, ema20, ema50, atr14, atr_ratio_14_50"),
        ({"rsi14": 50.0, "ema20": 148.0, "atr14": None, "atr_ratio_14_50": None}, "atr14=null, atr_ratio_14_50=null — stop distance cannot be computed"),
        ({"rsi14": 57.0, "ema20": 149.0, "ema50": 147.5, "atr14": 1.8}, "atr_ratio_14_50 — cannot verify ATR filter"),
        ({"rsi14": None, "ema20": 148.0, "ema50": 146.0, "atr14": 2.0, "atr_ratio_14_50": 1.05}, "rsi14=null — cannot assess momentum"),
        ({"rsi14": 55.0, "ema20": None, "ema50": 146.0, "atr14": 1.9, "atr_ratio_14_50": 1.08}, "ema20=null — cannot verify EMA alignment"),
        ({"rsi14": 56.0, "ema20": 149.0, "ema50": None, "atr14": 2.1, "atr_ratio_14_50": 1.10}, "ema50=null — cannot verify EMA stack direction"),
        ({"rsi14": 53.0, "atr14": 1.7}, "ema20, ema50 — cannot confirm trend bias"),
        ({"atr_ratio_14_50": 1.05, "ema20": 148.0}, "rsi14, atr14, ema50"),
        ({"rsi14": 60.0, "ema20": 150.0, "ema50": 148.0, "atr14": 2.5}, "atr_ratio_14_50 — hard limit check impossible"),
        ({"atr14": 2.0, "rsi14": 54.0, "ema20": 148.0}, "ema50, atr_ratio_14_50"),
        ({"rsi14": 55.0, "ema50": 145.0, "atr14": 1.8, "atr_ratio_14_50": 1.05}, "ema20 missing"),
        ({"rsi14": 57.0, "atr_ratio_14_50": 1.12, "ema20": 149.0}, "atr14 — cannot compute stop distance"),
        ({"rsi14": 52.0, "ema20": 147.0, "atr_ratio_14_50": 1.08}, "atr14 — cannot compute stop distance or position size"),
    ]
    for i, (ind, missing_desc) in enumerate(missing_variants):
        conf_gap = 0.10  # insufficient data → low gap
        output = _gold_output(
            final_status="INSUFFICIENT_DATA",
            claim_reviewed=f"Packet missing: {missing_desc}. Cannot execute gate checks.",
            math_verdict=f"insufficient — missing {missing_desc}. Stop distance or ATR filter check impossible.",
            numeric_answer=None,
            leakage_check="PASS",
            policy_alignment=f"Missing {missing_desc} — cannot verify ATR hard limit, stop distance, or momentum gate. INSUFFICIENT_DATA is mandatory.",
            data_gaps=f"Missing: {missing_desc}. Cannot proceed without complete indicator packet.",
            regime="unknown",
            conf_gap=conf_gap,
            atr_pct=None,
            blocking_rules=["missing_required_indicators"],
            setup_sig=f"abstention_missing_data_{i:02d}",
            rule_checks={"atr_filter_passed": False, "spread_liquidity_ok": True, "data_quality_passed": False, "confidence_gap_passed": False},
        )
        rows.append(_row(
            case_id=f"FQ-REM-ABSENT-{i+1:03d}",
            category="no_trade_abstention",
            tags=["missing_data", "remediation", "insufficient_data"],
            ref_facts={
                "bars_recent_oldest_to_newest": _bars(148.0, 2.0, rng),
                "indicator_values_at_close": ind,
                "lifecycle_state_prior": "no_trade",
                "decision_bar_index_in_window": 2,
                "perp_context_v1": {"funding_rate_bucket": "not_in_packet", "oi_change_bucket": "not_in_packet", "vol_stress_bucket": "not_in_packet"},
            },
            output=output,
        ))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant exam remediation corpus generator")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "remediation_corpus_v0.3.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    rows: list[dict[str, Any]] = []
    rows += generate_atr_hard_rule(rng)
    rows += generate_lookahead(rng)
    rows += generate_same_bar(rng)
    rows += generate_funding_sign(rng)
    rows += generate_abstention(rng)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Written: {args.out}")
    print(f"Total rows: {len(rows)}")
    print(f"  ATR hard rule: {len([r for r in rows if 'atr_hard_rule' in r.get('secondary_tags', [])])}")
    print(f"  Lookahead: {len([r for r in rows if 'lookahead' in r.get('secondary_tags', [])])}")
    print(f"  Same-bar: {len([r for r in rows if 'same_bar_rule' in r.get('secondary_tags', [])])}")
    print(f"  Funding sign: {len([r for r in rows if 'funding_sign' in r.get('secondary_tags', [])])}")
    print(f"  Abstention: {len([r for r in rows if 'missing_data' in r.get('secondary_tags', [])])}")
    print()
    print("Next steps:")
    print(f"  1. Validate: python3 training/validate_agentic_corpus_v1.py {args.out}")
    print("  2. On trx40 after git pull:")
    print("     cat $FINQUANT_BASE/datasets/train_agentic_v1.jsonl \\ ")
    out_rel = args.out.resolve().relative_to(Path(__file__).resolve().parents[1]) if args.out.resolve().is_relative_to(Path(__file__).resolve().parents[1]) else args.out
    print(f"         ~/blackbox/{out_rel} \\")
    print("         > $FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl")
    print("  3. Validate merged: python3 training/validate_agentic_corpus_v1.py $FINQUANT_BASE/datasets/merged_finquant_v0.3.jsonl")
    print("  4. Run train (tmux):")
    print("     tmux new-session -s finquant_v02_train \\")
    print("       \"source /data/NDE/finquant/.venv-finquant/bin/activate && \\")
    print("        python3 training/train_qlora.py full \\")
    print("          --config training/config_v0.2.yaml \\")
    print("          --dataset /data/NDE/finquant/agentic_v05/datasets/merged_finquant_v0.3.jsonl \\")
    print("          --base /data/NDE/finquant/agentic_v05 2>&1 | tee /data/NDE/finquant/agentic_v05/reports/train_v02.log\"")


if __name__ == "__main__":
    main()
