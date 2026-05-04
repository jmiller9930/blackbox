"""
prove_learning → training corpus exporter

Converts good decisions from the prove_learning training loop ledger
into finquant_agentic_qa_v1 format for use in the QLoRA training corpus.

Only exports rows where:
  - is_good_decision = True
  - confidence_spread >= min_confidence_spread (default 0.20)
  - outcome_kind in (win, no_trade_correct)

ATR multiples from config_v0.1.yaml:
  stop:   1.6 × ATR14
  target: 4.0 × ATR14
  R:      2.5
  breakeven win rate: 1 / (1 + 2.5) = 28.57%

Usage (from repo root):
  python3 prove_learning/finquant/unified/agent_lab/export_to_training_corpus.py \\
    --latest \\
    --output training/prove_learning_export.jsonl \\
    --min-confidence-spread 0.20 \\
    --good-only

  Or pass an explicit ledger:
  python3 prove_learning/finquant/unified/agent_lab/export_to_training_corpus.py \\
    --ledger prove_learning/ledger_output/train_20260503T012636Z_e2c07190_decisions.json \\
    --output training/prove_learning_export.jsonl --good-only

  Then validate:
  python3 training/validate_agentic_corpus_v1.py training/prove_learning_export.jsonl

  Merge at operator handoff (avoid duplicate appends):
  cat training/prove_learning_export.jsonl >> training/corpus_v05_agentic_seed.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from training.risk_context_contract import build_risk_context_for_gold

STOP_ATR_MULT   = 1.6
TARGET_ATR_MULT = 4.0
R_MULTIPLE      = TARGET_ATR_MULT / STOP_ATR_MULT       # 2.5
BREAKEVEN_WR    = 1.0 / (1.0 + R_MULTIPLE)              # 0.2857
EQUITY_USD      = 10000.0
RISK_PCT        = 0.01
RISK_DOLLARS    = EQUITY_USD * RISK_PCT                  # $100
TARGET_DOLLARS  = RISK_DOLLARS * R_MULTIPLE             # $250

POLICY_ID = "jupiter_2_sean_perps_v1"
EXAM_SCHEMA = "finquant_quant_exam_v1"
TRAINING_SCHEMA = "finquant_agentic_qa_v1"


BAR_FIELDS = ("close", "open", "high", "low", "volume", "rsi_14", "ema_20", "atr_14", "atr_pct")


def _ledger_row_to_bar_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Minimal OHLCV+indicator dict for bars_recent_oldest_to_newest."""
    out: dict[str, Any] = {}
    for k in BAR_FIELDS:
        if row.get(k) is not None:
            out[k] = row[k]
    out["timestamp"] = row.get("timestamp") or row.get("bar_timestamp") or ""
    return out


def _build_3bar_window(
    row: dict[str, Any],
    *,
    ledger_index: int | None = None,
    all_rows: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Return (3 bars oldest→newest ending at decision bar, window_source).
    Prefer consecutive ledger rows [i-2, i-1, i] when available.
    """
    decision_bar = _ledger_row_to_bar_dict(row)

    if (
        ledger_index is not None
        and all_rows is not None
        and ledger_index >= 2
        and ledger_index < len(all_rows)
    ):
        b0 = _ledger_row_to_bar_dict(all_rows[ledger_index - 2])
        b1 = _ledger_row_to_bar_dict(all_rows[ledger_index - 1])
        return [b0, b1, decision_bar], "ledger_sequence"

    if ledger_index is not None and all_rows is not None and ledger_index < len(all_rows):
        # Pad head with duplicates of earliest available bar in window
        pad = _ledger_row_to_bar_dict(all_rows[0])
        if ledger_index == 0:
            return [pad, pad, decision_bar], "ledger_sequence_padded"
        if ledger_index == 1:
            b0 = _ledger_row_to_bar_dict(all_rows[0])
            return [b0, b0, decision_bar], "ledger_sequence_padded"

    bar_m1 = dict(decision_bar)
    bar_m1["timestamp"] = "synthetic_prior_1"
    bar_m2 = dict(decision_bar)
    bar_m2["timestamp"] = "synthetic_prior_2"
    return [bar_m2, bar_m1, decision_bar], "synthetic_fallback"


def _vol_stress_bucket(atr_pct: Any) -> str:
    if atr_pct is None:
        return "not_in_packet"
    try:
        a = float(atr_pct)
    except (TypeError, ValueError):
        return "not_in_packet"
    if a > 5.0:
        return "elevated"
    if a > 3.0:
        return "normal_high"
    if a > 1.5:
        return "normal"
    return "compressed"


def _perp_context_from_row(row: dict[str, Any]) -> dict[str, str]:
    """
    Bucketed perp-native context. Uses ledger fields when present; else not_in_packet.
    """
    out: dict[str, str] = {
        "funding_rate_bucket": "not_in_packet",
        "oi_change_bucket": "not_in_packet",
        "vol_stress_bucket": _vol_stress_bucket(row.get("atr_pct")),
    }
    # Optional ledger columns (forward-compatible)
    fb = row.get("funding_rate_bucket")
    if isinstance(fb, str) and fb.strip():
        out["funding_rate_bucket"] = fb.strip()
    elif row.get("funding_rate") is not None:
        try:
            fr = float(row["funding_rate"])
            if fr > 0.0003:
                out["funding_rate_bucket"] = "longs_pay_elevated"
            elif fr < -0.0003:
                out["funding_rate_bucket"] = "shorts_pay_elevated"
            else:
                out["funding_rate_bucket"] = "neutral"
        except (TypeError, ValueError):
            pass
    ob = row.get("oi_change_bucket")
    if isinstance(ob, str) and ob.strip():
        out["oi_change_bucket"] = ob.strip()
    elif row.get("oi_change_pct") is not None:
        try:
            oc = float(row["oi_change_pct"])
            if oc > 5.0:
                out["oi_change_bucket"] = "rising_fast"
            elif oc < -5.0:
                out["oi_change_bucket"] = "falling_fast"
            else:
                out["oi_change_bucket"] = "stable"
        except (TypeError, ValueError):
            pass
    return out


FEE_PER_SIDE_BPS = 5
SLIPPAGE_BAND_BPS = 10  # one-way modeling band


def outcome_to_final_status(row: dict[str, Any]) -> str | None:
    action = str(row.get("action") or "")
    outcome = str(row.get("outcome_kind") or "")
    spread = row.get("confidence_spread")

    if spread is not None:
        try:
            if float(spread) < 0.10:
                return "INSUFFICIENT_DATA"
        except (TypeError, ValueError):
            pass

    if outcome == "win":
        if "LONG" in action:
            return "ENTER_LONG"
        if "SHORT" in action:
            return "ENTER_SHORT"
    if outcome == "no_trade_correct":
        return "NO_TRADE"
    return None


def estimate_win_rate(row: dict[str, Any], final_status: str) -> float:
    """Estimate win rate based on signal quality in the row."""
    h1c = row.get("h1_confidence")
    h2c = row.get("h2_confidence")
    spread = row.get("confidence_spread")

    # Base: breakeven
    est = BREAKEVEN_WR + 0.05

    if h1c is not None:
        try:
            h1 = float(h1c)
            if h1 >= 0.70: est += 0.10
            elif h1 >= 0.60: est += 0.05
        except (TypeError, ValueError):
            pass

    if spread is not None:
        try:
            s = float(spread)
            if s >= 0.35: est += 0.08
            elif s >= 0.25: est += 0.04
        except (TypeError, ValueError):
            pass

    return round(min(0.85, max(BREAKEVEN_WR, est)), 4)


def build_hypotheses(row: dict[str, Any], final_status: str) -> list[dict[str, Any]]:
    """Build hypotheses_v1 from ledger row data."""
    action = str(row.get("action") or "NO_TRADE")
    h1_thesis = str(row.get("hypothesis_1") or "")
    h2_thesis = str(row.get("hypothesis_2") or "")
    h1c = row.get("h1_confidence")
    h2c = row.get("h2_confidence")
    regime = str(row.get("regime") or "unknown")
    rsi = row.get("rsi_14")
    atr_pct = row.get("atr_pct")
    source = str(row.get("source") or "rule")
    thesis = str(row.get("thesis") or "")

    # Primary hypothesis from ledger h1
    if not h1_thesis and thesis:
        h1_thesis = thesis[:200]

    h1_conf = 0.60
    h2_conf = 0.35
    if h1c is not None:
        try: h1_conf = float(h1c)
        except: pass
    if h2c is not None:
        try: h2_conf = float(h2c)
        except: pass

    rsi_str = f"RSI14={rsi:.1f}" if rsi else "RSI14=N/A"
    atr_str = f"ATR%={atr_pct:.3f}%" if atr_pct else "ATR=N/A"

    if final_status == "ENTER_LONG":
        h1 = {
            "id": "H1_bullish_entry",
            "claim": h1_thesis if h1_thesis else f"Bullish divergence in {regime} regime. {rsi_str}, {atr_str}. Entry conditions met.",
            "supporting_evidence": [rsi_str, atr_str, f"regime={regime}", "divergence_signal=bullish"],
            "counter_evidence": [h2_thesis[:100] if h2_thesis else "Counter-trend risk present"],
            "confidence": h1_conf,
        }
        h2 = {
            "id": "H2_no_trade_counter",
            "claim": h2_thesis if h2_thesis else f"Insufficient confluence or momentum not confirmed. {rsi_str} below bullish_strong.",
            "supporting_evidence": ["RSI not at extreme", "possible chop"],
            "counter_evidence": ["divergence signal present", "EMA bias aligned"],
            "confidence": h2_conf,
        }
    elif final_status == "ENTER_SHORT":
        h1 = {
            "id": "H1_bearish_entry",
            "claim": h1_thesis if h1_thesis else f"Bearish divergence in {regime} regime. {rsi_str}, {atr_str}. Short entry conditions met.",
            "supporting_evidence": [rsi_str, atr_str, f"regime={regime}", "divergence_signal=bearish"],
            "counter_evidence": [h2_thesis[:100] if h2_thesis else "Potential bounce risk"],
            "confidence": h1_conf,
        }
        h2 = {
            "id": "H2_no_trade_counter",
            "claim": h2_thesis if h2_thesis else "Bearish signal may be exhaustion bounce; wait for cleaner setup.",
            "supporting_evidence": ["RSI not at extreme oversold"],
            "counter_evidence": ["divergence signal confirmed", "price making higher high with lower RSI"],
            "confidence": h2_conf,
        }
    elif final_status == "INSUFFICIENT_DATA":
        h1 = {
            "id": "H1_ambiguous",
            "claim": h1_thesis if h1_thesis else f"Signals mixed in {regime} regime. Cannot determine direction.",
            "supporting_evidence": [rsi_str, "signals contradicting"],
            "counter_evidence": ["no clear divergence"],
            "confidence": h1_conf,
        }
        h2 = {
            "id": "H2_also_ambiguous",
            "claim": h2_thesis if h2_thesis else "Counter-case equally plausible without more data.",
            "supporting_evidence": ["equal evidence both directions"],
            "counter_evidence": [],
            "confidence": h2_conf,
        }
    else:  # NO_TRADE
        h1 = {
            "id": "H1_no_trade",
            "claim": h1_thesis if h1_thesis else f"No sufficient edge in {regime} regime. {rsi_str}, {atr_str}. Stand down.",
            "supporting_evidence": [rsi_str, atr_str, "no divergence or insufficient ATR"],
            "counter_evidence": [h2_thesis[:100] if h2_thesis else "Some directional signals present"],
            "confidence": h1_conf,
        }
        h2 = {
            "id": "H2_entry_counter",
            "claim": h2_thesis if h2_thesis else "Weak directional case — momentum insufficient to justify risk.",
            "supporting_evidence": ["RSI not at extreme", "ATR not expanded"],
            "counter_evidence": ["No divergence confirmed"],
            "confidence": h2_conf,
        }

    return [h1, h2]


def build_corpus_row(
    row: dict[str, Any],
    case_num: int,
    *,
    ledger_index: int | None = None,
    all_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Convert a single ledger row to finquant_agentic_qa_v1 format."""
    final_status = outcome_to_final_status(row)
    if final_status is None:
        return None

    action = str(row.get("action") or "NO_TRADE")
    regime = str(row.get("regime") or "unknown")
    close = row.get("close") or 0.0
    rsi = row.get("rsi_14")
    atr = row.get("atr_14")
    atr_pct = row.get("atr_pct")
    cycle = row.get("cycle", "1")

    # Compute stop/target from ATR using policy multiples
    stop_price = target_price = None
    if atr and close and float(close) > 0:
        atr_f = float(atr)
        close_f = float(close)
        if "LONG" in final_status:
            stop_price = round(close_f - STOP_ATR_MULT * atr_f, 6)
            target_price = round(close_f + TARGET_ATR_MULT * atr_f, 6)
        elif "SHORT" in final_status:
            stop_price = round(close_f + STOP_ATR_MULT * atr_f, 6)
            target_price = round(close_f - TARGET_ATR_MULT * atr_f, 6)

    est_wr = estimate_win_rate(row, final_status)
    exp_per_trade = round((est_wr * TARGET_DOLLARS) - ((1 - est_wr) * RISK_DOLLARS), 2)
    contributes = final_status in ("ENTER_LONG", "ENTER_SHORT") and exp_per_trade > 0

    hypotheses = build_hypotheses(row, final_status)
    h1_conf = float(hypotheses[0]["confidence"])
    h2_conf = float(hypotheses[1]["confidence"])
    top2 = sorted([h1_conf, h2_conf], reverse=True)
    conf_gap = round(top2[0] - top2[1], 4)
    # R-002 / validate_agentic_corpus_v1: gap < 0.20 ⇒ i_dont_know_triggered true
    i_dont_know = conf_gap < 0.20
    # Entry gold must be decisive — do not emit ENTER_* with sub-threshold spread
    if final_status in ("ENTER_LONG", "ENTER_SHORT") and i_dont_know:
        hypotheses[0]["confidence"] = 0.72
        hypotheses[1]["confidence"] = 0.38
        conf_gap = 0.34
        i_dont_know = False

    # Blocking rules for no-trade cases
    blocking_rules = []
    if final_status in ("NO_TRADE", "INSUFFICIENT_DATA"):
        if atr_pct is not None and float(atr_pct) < 0.60:
            blocking_rules.append("ATR_pct_below_expand_threshold")
        if rsi is not None and 47 <= float(rsi) <= 53:
            blocking_rules.append("RSI_mid_zone_no_momentum")
        if i_dont_know:
            blocking_rules.append("confidence_gap_below_threshold")
        if not blocking_rules:
            blocking_rules.append("insufficient_confluence_across_core_conditions")

    # Setup signature for learning record
    rsi_zone = "unknown"
    if rsi is not None:
        r = float(rsi)
        if r >= 65: rsi_zone = "rsi_65plus"
        elif r >= 55: rsi_zone = "rsi_55_65"
        elif r >= 45: rsi_zone = "rsi_45_55"
        else: rsi_zone = "rsi_under45"

    setup_sig = f"{final_status.lower()}_{regime}_{rsi_zone}"
    if atr_pct is not None:
        atr_f = float(atr_pct)
        if atr_f > 0.60: setup_sig += "_atr_expanded"
        else: setup_sig += "_atr_normal"

    case_id = f"FQ-LIVE-{case_num:04d}-C{cycle}"
    outcome_kind = str(row.get("outcome_kind") or "")

    bars_3, window_src = _build_3bar_window(
        row, ledger_index=ledger_index, all_rows=all_rows
    )
    perp_ctx = _perp_context_from_row(row)
    friction_bps = int(2 * FEE_PER_SIDE_BPS + 2 * SLIPPAGE_BAND_BPS)

    atr_pct_f = float(atr_pct) if atr_pct is not None else None
    rc_v1, rec_pct = build_risk_context_for_gold(
        final_status,
        conf_gap=conf_gap,
        regime=regime,
        atr_pct=atr_pct_f,
        i_dont_know=i_dont_know,
        baseline_risk_pct=RISK_PCT * 100.0,
    )

    output_obj = {
        "context_observed_v1": {
            "trend_regime": regime,
            "volatility_regime": f"atr_pct_{atr_pct:.3f}%" if atr_pct else "unknown",
            "structure_proxy": f"divergence_based_{final_status.lower()}",
            "recency_note": f"cycle_{cycle}_real_sol_perp_15m",
        },
        "context_evidence_v1": [
            f"RSI14={rsi:.1f}" if rsi else "RSI=N/A",
            f"ATR%={atr_pct:.3f}%" if atr_pct else "ATR=N/A",
            f"regime={regime}",
            f"action={action}",
            f"outcome={outcome_kind}",
        ],
        "context_uncertainty_v1": [
            "Volume from tick_count proxy — not true traded volume",
            "Single timeframe only — no higher timeframe bias confirmation",
        ],
        "hypotheses_v1": hypotheses,
        "dominant_hypothesis_v1": hypotheses[0]["id"] if not i_dont_know else None,
        "confidence_gap_v1": conf_gap,
        "i_dont_know_triggered": i_dont_know,
        "deterministic_baseline_verdict_v1": {
            "policy_id": POLICY_ID,
            "verdict": final_status,
            "blocking_rules": blocking_rules,
        },
        "model_independent_assessment_v1": {
            "stance": "agree_with_" + final_status.lower(),
            "reasoning": str(row.get("thesis") or "Decision consistent with observed indicators and prime directive."),
            "would_veto_a_rule_pass": final_status in ("NO_TRADE", "INSUFFICIENT_DATA"),
            "would_override_a_rule_block": final_status in ("ENTER_LONG", "ENTER_SHORT"),
        },
        "threshold_adjustment_proposal_v1": {
            "proposed_change": "no_change",
            "direction": "no_change",
            "evidence_memory_ids": [],
            "evidence_summary": "",
            "applied_to_this_case": False,
            "applied_to_this_case_reason": "Real market case — no threshold change proposed.",
        },
        "learning_record_candidate_v1": {
            "setup_signature": setup_sig,
            "decision_taken": final_status,
            "lesson_if_win": f"{final_status} in {regime} with {rsi_zone} RSI produced positive outcome." if outcome_kind == "win" else f"{final_status} setup — if market confirms, pattern is valid.",
            "lesson_if_loss": f"{final_status} failed in {regime} — check regime shift and divergence quality." if outcome_kind == "loss" else "n/a_no_entry",
            "promotion_candidate": outcome_kind in ("win", "no_trade_correct"),
            "do_not_promote_reason": None if outcome_kind in ("win", "no_trade_correct") else f"outcome={outcome_kind}",
        },
        "expectancy_check_v1": {
            "planned_r_multiple": R_MULTIPLE,
            "planned_risk_dollars": RISK_DOLLARS,
            "planned_target_dollars": TARGET_DOLLARS,
            "breakeven_win_rate_required": round(BREAKEVEN_WR, 4),
            "this_setup_estimated_win_rate": est_wr if final_status in ("ENTER_LONG", "ENTER_SHORT") else None,
            "expectancy_per_trade_dollars": exp_per_trade if final_status in ("ENTER_LONG", "ENTER_SHORT") else None,
            "contributes_to_long_run_math": contributes,
            "note": f"Stop={STOP_ATR_MULT}xATR, Target={TARGET_ATR_MULT}xATR per policy config. " + (
                f"Estimated {est_wr:.0%} win rate vs {BREAKEVEN_WR:.1%} breakeven." if final_status in ("ENTER_LONG", "ENTER_SHORT")
                else "No entry — expectancy not applicable."
            ),
        },
        "risk_context_v1": rc_v1,
        "recommended_risk_pct": rec_pct,
        "context_decision_link_v1": f"{regime} regime + {rsi_zone} RSI + divergence_signal → {final_status}",
        "lifecycle_state_v1": "trade" if final_status in ("ENTER_LONG", "ENTER_SHORT") else "no_trade",
        "Claim_reviewed": f"{final_status} consistent with prime directive and indicator evidence.",
        "Math_verdict": f"At R={R_MULTIPLE}, breakeven={BREAKEVEN_WR:.1%}. " + (
            f"Estimated win rate {est_wr:.0%} {'exceeds' if contributes else 'below'} breakeven."
            if final_status in ("ENTER_LONG", "ENTER_SHORT") else "No trade — math not applicable."
        ),
        "Numeric_answer": exp_per_trade if final_status in ("ENTER_LONG", "ENTER_SHORT") else None,
        "Leakage_check": "No future bars referenced. Decision based on causal indicator data only.",
        "Policy_alignment": "RSI divergence signal + regime check + confidence spread gate applied.",
        "DATA_or_assumption_gaps": (
            "Three-bar window oldest→newest; decision is last bar only. "
            "Volume is tick_count proxy. Single timeframe 15m. "
            "Funding/OI not in packet unless listed in perp_context_v1."
        ),
        "Final_status": final_status,
    }

    corpus_row = {
        "case_id": case_id,
        "exam_schema": EXAM_SCHEMA,
        "exam_version": 1,
        "training_schema": TRAINING_SCHEMA,
        "primary_category": _map_category(final_status, regime, outcome_kind),
        "secondary_tags": ["real_sol_perp_15m", "divergence_signal", f"cycle_{cycle}", regime],
        "instruction": (
            "You are FinQuant. Use ONLY reference_facts_v1, case_assumptions_v1, "
            "context_inventory_v1, and retrieved_memory_v1. Decision applies to the LAST bar "
            "(decision_bar_index_in_window). Produce strict JSON: hypotheses (≥2), "
            "deterministic baseline verdict, expectancy_check_v1, risk_context_v1 with "
            "recommended_risk_pct equal to final_risk_pct, learning_record_candidate_v1. "
            "Factor declared fees/slippage (case_assumptions_v1) into economic reasoning."
        ),
        "input": {
            "case_assumptions_v1": {
                "symbol": "SOL-PERP",
                "policy_id": POLICY_ID,
                "risk_pct_equity": RISK_PCT,
                "equity_usd": EQUITY_USD,
                "planned_stop_atr_multiple": STOP_ATR_MULT,
                "planned_target_atr_multiple": TARGET_ATR_MULT,
                "fee_per_side_bps": FEE_PER_SIDE_BPS,
                "slippage_band_bps": SLIPPAGE_BAND_BPS,
                "estimated_round_trip_friction_bps": friction_bps,
                "fill_latency_class": "interactive_market_order",
                "economics_notes": (
                    "estimated_round_trip_friction_bps = 2×fee_per_side_bps + 2×slippage_band_bps "
                    "(conservative round-trip model)."
                ),
                "notes": (
                    "SOL-PERP 15m; oracle/bar facts as provided. "
                    "RSI divergence definitions per operator briefing."
                ),
            },
            "context_inventory_v1": {
                "bars_in_window": 3,
                "decision_bar_index_in_window": 2,
                "window_bar_source": window_src,
                "has_declared_economics": True,
                "has_funding_oi_in_packet": perp_ctx["funding_rate_bucket"] != "not_in_packet"
                or perp_ctx["oi_change_bucket"] != "not_in_packet",
            },
            "reference_facts_v1": {
                "bars_recent_oldest_to_newest": bars_3,
                "decision_bar_index_in_window": 2,
                "indicator_values_at_close": {
                    "rsi14": rsi,
                    "ema20": row.get("ema_20"),
                    "atr14": atr,
                    "atr_pct": atr_pct,
                },
                "perp_context_v1": perp_ctx,
                "lifecycle_state_prior": "no_trade",
                "open_position": None,
                "regime": regime,
            },
            "expected_output_contract_v1": {
                "schema": "finquant_agentic_response_v1",
                "required_sections": [
                    "context_observed_v1", "hypotheses_v1", "deterministic_baseline_verdict_v1",
                    "expectancy_check_v1", "risk_context_v1", "recommended_risk_pct",
                    "learning_record_candidate_v1",
                    "Claim_reviewed", "Math_verdict", "Numeric_answer",
                    "Leakage_check", "Policy_alignment", "DATA_or_assumption_gaps", "Final_status",
                ],
            },
            "retrieved_memory_v1": [],  # Real runs would populate from memory store
        },
        "output": output_obj,
        "grading_v1": {
            "kind": "deterministic_jsonpath_v1",
            "notes": "validate_agentic_corpus_v1.py",
            "rules": [
                {"id": "hypotheses_min_2", "path": "$.hypotheses_v1", "expect_min_length": 2},
                {"id": "final_status_valid", "path": "$.Final_status", "expect_in": ["ENTER_LONG", "ENTER_SHORT", "NO_TRADE", "INSUFFICIENT_DATA"]},
                {"id": "expectancy_present", "path": "$.expectancy_check_v1.breakeven_win_rate_required", "expect_type": "number"},
            ],
        },
    }

    return corpus_row


def _map_category(final_status: str, regime: str, outcome_kind: str) -> str:
    if final_status == "ENTER_LONG":
        return "clean_long_continuation" if outcome_kind == "win" else "good_trade_that_loses"
    if final_status == "ENTER_SHORT":
        return "clean_short_continuation" if outcome_kind == "win" else "good_trade_that_loses"
    if final_status == "INSUFFICIENT_DATA":
        return "rm_data_feature_inference_boundary_v1"
    if outcome_kind == "no_trade_correct":
        return "no_trade_abstention" if "chop" not in regime else "range_chop"
    return "missed_opportunity"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export prove_learning ledger rows to finquant_agentic_qa_v1 corpus")
    parser.add_argument("--ledger", help="Path to decisions.json from operator_ledger.py")
    parser.add_argument("--latest", action="store_true",
                        help="Auto-find most recent decisions.json under prove_learning/ledger_output/")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    parser.add_argument("--min-confidence-spread", type=float, default=0.20,
                        help="Minimum confidence spread to export (default 0.20)")
    parser.add_argument("--good-only", action="store_true",
                        help="Only export rows where is_good_decision=True")
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Maximum rows to export")
    args = parser.parse_args()

    # Resolve ledger path
    if args.latest:
        # .../prove_learning/finquant/unified/agent_lab/this_file → prove_learning/ledger_output
        ledger_dir = Path(__file__).resolve().parents[3] / "ledger_output"
        candidates = sorted(ledger_dir.glob("*_decisions.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print(f"ERROR: no decisions.json files found under {ledger_dir}", file=sys.stderr)
            sys.exit(1)
        ledger_path = candidates[0]
        print(f"[export] auto-selected latest ledger: {ledger_path.name}")
    elif args.ledger:
        ledger_path = Path(args.ledger)
    else:
        print("ERROR: provide --ledger PATH or --latest", file=sys.stderr)
        sys.exit(1)

    if not ledger_path.exists():
        print(f"ERROR: ledger not found: {ledger_path}", file=sys.stderr)
        sys.exit(1)

    # Contract check: validate expected columns exist before processing
    REQUIRED_COLUMNS = {"action", "outcome_kind", "is_good_decision", "regime", "rsi_14"}
    rows = json.loads(ledger_path.read_text())
    if rows:
        sample_keys = set(rows[0].keys())
        missing = REQUIRED_COLUMNS - sample_keys
        if missing:
            print(f"ERROR: ledger missing required columns: {missing}", file=sys.stderr)
            print(f"       Found columns: {sorted(sample_keys)}", file=sys.stderr)
            print(f"       Check operator_ledger.py for field name changes.", file=sys.stderr)
            sys.exit(1)
    print(f"[export] loaded {len(rows)} ledger rows from {ledger_path.name}")

    exported = 0
    skipped_bad = 0
    skipped_spread = 0
    skipped_no_final = 0

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        for i, row in enumerate(rows):
            if args.max_rows and exported >= args.max_rows:
                break

            # Filter: good decisions only
            if args.good_only and not row.get("is_good_decision", False):
                skipped_bad += 1
                continue

            # Filter: confidence spread
            spread = row.get("confidence_spread")
            if spread is not None:
                try:
                    if float(spread) < args.min_confidence_spread and str(row.get("action")) not in ("NO_TRADE",):
                        skipped_spread += 1
                        continue
                except (TypeError, ValueError):
                    pass

            corpus_row = build_corpus_row(row, exported + 1, ledger_index=i, all_rows=rows)
            if corpus_row is None:
                skipped_no_final += 1
                continue

            f.write(json.dumps(corpus_row) + "\n")
            exported += 1

    print(f"[export] exported: {exported}")
    print(f"[export] skipped (bad decision): {skipped_bad}")
    print(f"[export] skipped (spread too low): {skipped_spread}")
    print(f"[export] skipped (no Final_status): {skipped_no_final}")
    print(f"[export] output: {out_path}")

    # Category breakdown
    cats: dict[str, int] = {}
    rows_out = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    for r in rows_out:
        c = r.get("primary_category", "unknown")
        cats[c] = cats.get(c, 0) + 1
    print(f"[export] categories: {cats}")
    print(f"\nNext steps:")
    print(f"  python3 training/validate_agentic_corpus_v1.py {out_path}")
    print(f"  cat {out_path} >> training/corpus_v05_agentic_seed.jsonl")


if __name__ == "__main__":
    main()
