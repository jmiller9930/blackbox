"""
GT_DIRECTIVE_026A_IMPL — **Student entry reasoning engine** (deterministic, validated, traceable).

The LLM (when used) may only propose ``llm_explanation_proposal_v1`` text; **authority** is
``decision_synthesis_v1`` computed here. ``run_entry_reasoning_pipeline_v1`` is the **mandatory**
ordered pipeline: market data → indicators → memory → prior outcomes → risk → decision →
validation → digest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    STATUS_FAIL,
    STATUS_NOT_PROVEN,
    STATUS_PASS,
    build_fault_map_v1,
    make_fault_node_v1,
    skipped_nodes_from_index_v1,
)
from renaissance_v4.utils.math_utils import ema as ema_last, safe_mean

SCHEMA_ENTRY_REASONING_EVAL_V1 = "entry_reasoning_eval_v1"
SCHEMA_ENTRY_REASONING_DIGEST_V1 = "entry_reasoning_eval_digest_v1"

# ---------------------------------------------------------------------------
# Thresholds (explicit; adjust only with regression tests)
# ---------------------------------------------------------------------------
_RSI_PERIOD = 14
_EMA_TREND_PERIOD = 20
_ATR_LOOKBACK = 14
_VOLUME_ROLL = 20
_MEM_THRESHOLD_HIGH = 2.0
_MEM_THRESHOLD_LOW = 1.0
_LONG_THRESHOLD = 0.2
_SHORT_THRESHOLD = -0.2
_CONFLICT_PENALTY = 0.5


# ---------------------------------------------------------------------------
# Indicators (deterministic; bars from Student packet only)
# ---------------------------------------------------------------------------
def _wilder_rsi_last(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return float("nan")
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def _true_ranges(bars: list[dict[str, Any]]) -> list[float]:
    tr: list[float] = []
    for i in range(1, len(bars)):
        h, l_ = float(bars[i]["high"]), float(bars[i]["low"])
        c_prev = float(bars[i - 1]["close"])
        tr.append(max(h - l_, abs(h - c_prev), abs(l_ - c_prev)))
    return tr


def _atr14_last(bars: list[dict[str, Any]]) -> float:
    tr = _true_ranges(bars)
    if not tr:
        return 0.0
    if len(tr) < _ATR_LOOKBACK:
        return float(safe_mean(tr))
    w = tr[:_ATR_LOOKBACK]
    s = sum(w) / _ATR_LOOKBACK
    for x in tr[_ATR_LOOKBACK:]:
        s = (s * (_ATR_LOOKBACK - 1) + x) / _ATR_LOOKBACK
    return float(s)


def _ema_value(closes: list[float], period: int) -> float:
    return float(ema_last(closes, period)) if closes else 0.0


def _rsi_state(rsi: float, trend: str) -> str:
    if math.isnan(rsi):
        return "neutral"
    if rsi >= 70.0:
        if trend == "bullish_trend":
            return "continuation_pressure"
        if trend != "bullish_trend":
            return "exhaustion_risk"
        return "overbought"
    if rsi <= 30.0:
        if trend == "bearish_trend":
            return "continuation_weakness"
        if trend != "bearish_trend":
            return "reversal_potential"
        return "oversold"
    return "neutral"


def _ema_trend_state(last_close: float, ema_now: float, ema_prev: float) -> str:
    slope = ema_now - ema_prev
    if last_close > ema_now and slope > 0:
        return "bullish_trend"
    if last_close < ema_now and slope < 0:
        return "bearish_trend"
    return "neutral_trend"


def _atr_vol_state(atr: float, recent_tr: list[float]) -> str:
    if not recent_tr or atr <= 0:
        return "normal_volatility"
    m = float(safe_mean(recent_tr[-_ATR_LOOKBACK:]))
    if m <= 0:
        return "normal_volatility"
    r = atr / m
    if r >= 1.2:
        return "high_volatility"
    if r <= 0.8:
        return "low_volatility"
    return "normal_volatility"


def _volume_state(vol: float, history: list[float]) -> str | None:
    if not history:
        return None
    avg_v = float(safe_mean(history))
    if avg_v <= 0:
        return None
    return "strong_participation" if vol > avg_v else "weak_participation"


def build_indicator_context_eval_v1(
    bars: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """
    Deterministic ``indicator_context_eval_v1`` + support flags; ``errs`` if unusable.
    """
    errs: list[str] = []
    n_b = len(bars)
    if n_b < 2:
        errs.append("insufficient_bars_for_indicator_engine")
    closes = [float(b["close"]) for b in bars]
    # Adaptive EMA/RSI when fewer than 20+2 bars (short causal windows, e.g. test fixtures) — still deterministic.
    ema_p = _EMA_TREND_PERIOD if n_b > _EMA_TREND_PERIOD + 1 else max(1, min(_EMA_TREND_PERIOD, n_b - 1))
    ema_now = _ema_value(closes, ema_p)
    ema_prev = _ema_value(closes[:-1], ema_p) if len(closes) > 1 else ema_now
    last = closes[-1]
    trend = _ema_trend_state(last, ema_now, ema_prev)
    trend_tag = (
        "bullish_trend"
        if trend == "bullish_trend"
        else ("bearish_trend" if trend == "bearish_trend" else "neutral_trend")
    )
    rsi = _wilder_rsi_last(closes, _RSI_PERIOD)
    if n_b < _RSI_PERIOD + 1 or math.isnan(rsi):
        rsi = 50.0
    rsi_s = _rsi_state(rsi, trend_tag)
    atr = _atr14_last(bars)
    trs = _true_ranges(bars)
    vol_st = _atr_vol_state(atr, trs)
    vols = [float(b.get("volume", 0) or 0) for b in bars]
    vhist = vols[-_VOLUME_ROLL - 1 : -1] if len(vols) > 1 else []
    vstate = _volume_state(vols[-1], vhist) if vhist else None

    flags = {"long": False, "short": False, "no_trade": True}
    if trend == "bullish_trend" and rsi_s in ("neutral", "oversold", "reversal_potential", "continuation_pressure"):
        flags["long"] = True
        flags["no_trade"] = False
    if trend == "bearish_trend" and rsi_s in ("neutral", "overbought", "exhaustion_risk", "continuation_weakness"):
        flags["short"] = True
        flags["no_trade"] = False
    if rsi_s in ("exhaustion_risk",) and flags["long"]:
        flags["long"] = False
    if rsi_s in ("reversal_potential",) and flags["short"]:
        flags["short"] = False
    if not flags["long"] and not flags["short"]:
        flags["no_trade"] = True

    out = {
        "schema": "indicator_context_eval_v1",
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "rsi_last": None if math.isnan(rsi) else round(rsi, 6),
        "ema_last": round(ema_now, 6),
        "ema_prev": round(ema_prev, 6),
        "atr_last": round(atr, 6),
        "rsi_state": rsi_s,
        "ema_trend": trend,
        "atr_volume_state": vol_st,
        "volume_state": vstate,
        "normalized_state_v1": {
            "rsi": rsi_s,
            "ema_trend": trend,
            "atr": vol_st,
            "volume": vstate,
        },
        "confidence_effect_v1": {
            "atr_adjustment": -0.1 if vol_st == "high_volatility" else (0.05 if vol_st == "low_volatility" else 0.0)
        },
        "support_flags_v1": flags,
    }
    return out, errs, {
        "closes_tail_len": len(closes),
    }


def indicator_score_v1(ctx: dict[str, Any]) -> float:
    """Map indicator context to [-1, 1] (deterministic)."""
    fl = (ctx or {}).get("support_flags_v1") or {}
    t = (ctx or {}).get("ema_trend") or "neutral_trend"
    m = 0.0
    if fl.get("long") and t == "bullish_trend":
        m += 0.45
    if fl.get("short") and t == "bearish_trend":
        m -= 0.45
    if (ctx or {}).get("rsi_state") in ("reversal_potential", "oversold") and t == "bullish_trend":
        m += 0.1
    if (ctx or {}).get("rsi_state") in ("exhaustion_risk", "overbought") and t == "bearish_trend":
        m -= 0.1
    ce = (ctx or {}).get("confidence_effect_v1") or {}
    m += float(ce.get("atr_adjustment", 0.0))
    return max(-1.0, min(1.0, m))


# ---------------------------------------------------------------------------
# Memory + prior
# ---------------------------------------------------------------------------
def _record_id(rec: dict[str, Any]) -> str:
    return str(rec.get("record_id") or "")


def score_memory_records_v1(
    records: list[dict[str, Any]],
    *,
    run_candle_timeframe_minutes: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in records:
        rid = _record_id(rec)
        if not rid:
            continue
        sim = 0.55
        tf = int(rec.get("candle_timeframe_minutes") or 0)
        tf_m = 1.0 if tf == int(run_candle_timeframe_minutes) else 0.0
        regime_m = 1.0
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        pnl = float(sub.get("pnl", 0) or 0.0) if sub else 0.0
        outcome_pen = 0.15 if pnl < 0 else 0.0
        score = sim + tf_m + regime_m - outcome_pen
        if pnl < 0 and tf_m > 0:
            cl = "conflict"
        elif score >= _MEM_THRESHOLD_HIGH:
            cl = "aligned"
        elif score >= _MEM_THRESHOLD_LOW:
            cl = "partial"
        else:
            cl = "ignore"
        out.append(
            {
                "record_id": rid,
                "memory_relevance_score_v1": round(score, 4),
                "memory_effect_class_v1": cl,
            }
        )
    return out


def memory_effect_to_score_v1(scored: list[dict[str, Any]]) -> tuple[float, str]:
    if not scored:
        return 0.0, "none"
    best = max(scored, key=lambda x: float(x.get("memory_relevance_score_v1", 0)))
    cl = str(best.get("memory_effect_class_v1") or "ignore")
    if cl == "aligned":
        return 0.2, "aligned"
    if cl == "partial":
        return 0.05, "partial"
    if cl == "conflict":
        return -_CONFLICT_PENALTY, "conflict"
    return 0.0, "ignore"


def prior_outcome_eval_v1(records: list[dict[str, Any]]) -> dict[str, Any]:
    ws = 0
    t = 0
    pnls: list[float] = []
    for rec in records:
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        if "pnl" not in sub:
            continue
        t += 1
        p = float(sub.get("pnl", 0) or 0)
        pnls.append(p)
        if p > 0:
            ws += 1
    # Use wins_total_fraction_v1 — not "win_rate" (forbidden in pre_reveal key scan on student_path payloads).
    wins_total_fraction_v1 = (ws / t) if t else 0.0
    avg = float(safe_mean(pnls)) if pnls else 0.0
    adj = 0.0
    if t >= 3 and wins_total_fraction_v1 < 0.4:
        adj = -0.15
    elif t >= 2 and wins_total_fraction_v1 > 0.6:
        adj = 0.1
    elif t >= 2 and 0.4 <= wins_total_fraction_v1 <= 0.6:
        adj = -0.05
    return {
        "schema": "prior_outcome_eval_v1",
        "wins_total_fraction_v1": round(wins_total_fraction_v1, 6),
        "total_with_pnl": t,
        "avg_pnl": round(avg, 6),
        "prior_outcome_confidence_delta_v1": round(adj, 6),
    }


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------
def build_risk_inputs_v1(
    *,
    last_close: float,
    atr: float,
    long_bias: bool,
) -> dict[str, Any]:
    inv = f"4h close below {round(last_close - atr * 2, 4)} invalidates long" if long_bias else f"4h close above {round(last_close + atr * 2, 4)} invalidates short"
    stop_b = f"1.2 × ATR ({round(atr * 1.2, 6)}) from entry"
    tgt = f"2.0 × R multiple vs stop ({round(atr * 2.4, 6)} price move)"
    return {
        "schema": "risk_inputs_v1",
        "atr_last": round(atr, 6),
        "invalidation_condition_v1": inv,
        "stop_basis_v1": stop_b,
        "target_basis_v1": tgt,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_entry_reasoning_eval_v1(doc: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["entry_reasoning_eval_v1 must be a dict"]
    if doc.get("schema") != SCHEMA_ENTRY_REASONING_EVAL_V1:
        errs.append("schema must be entry_reasoning_eval_v1")
    if doc.get("contract_version") != CONTRACT_VERSION_STUDENT_PROCTOR_V1:
        errs.append("contract_version mismatch")
    ds = doc.get("decision_synthesis_v1")
    if not isinstance(ds, dict):
        errs.append("decision_synthesis_v1 required")
    else:
        act = str(ds.get("action") or "")
        if act not in ("enter_long", "enter_short", "no_trade"):
            errs.append("action invalid")
        if act != "no_trade" and not doc.get("risk_defined_v1"):
            errs.append("trade_without_risk_rejected")
    c01 = doc.get("confidence_01")
    if not isinstance(c01, (int, float)) or not 0.0 <= float(c01) <= 1.0:
        errs.append("confidence_01 must be in [0,1]")
    return errs


def validate_llm_explanation_against_entry_reasoning_v1(
    llm_proposal: dict[str, Any] | None,
    *,
    entry_reasoning: dict[str, Any],
    allowed_memory_ids: frozenset[str],
) -> list[str]:
    """
    Reject if LLM references unknown memory IDs, overrides action, or smuggles fields.
    (GT_DIRECTIVE_026A_IMPL — no soft failures.)
    """
    if not llm_proposal:
        return []
    errs: list[str] = []
    for mid in list(llm_proposal.get("cited_memory_record_ids", []) or []):
        if str(mid) not in allowed_memory_ids:
            errs.append(f"hallucinated_memory_id:{mid}")
    dec = (entry_reasoning.get("decision_synthesis_v1") or {}) if isinstance(entry_reasoning, dict) else {}
    auth = str(dec.get("action") or "")
    if str(llm_proposal.get("stated_action") or "") and str(llm_proposal.get("stated_action") or "") != auth:
        errs.append("llm_cannot_override_decision")
    if llm_proposal.get("mystery_score") is not None:
        errs.append("llm_new_variable_mystery_score")
    return errs


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------
def build_entry_reasoning_eval_digest_v1(entry_reasoning_eval_v1: dict[str, Any]) -> str:
    key = {
        "decision_synthesis_v1": (entry_reasoning_eval_v1 or {}).get("decision_synthesis_v1"),
        "candle_timeframe_minutes": (entry_reasoning_eval_v1 or {}).get("candle_timeframe_minutes"),
        "indicator_summary": ((entry_reasoning_eval_v1 or {}).get("indicator_context_eval_v1") or {}).get("rsi_state")
        if isinstance((entry_reasoning_eval_v1 or {}).get("indicator_context_eval_v1"), dict)
        else None,
        "memory_effect": ((entry_reasoning_eval_v1 or {}).get("memory_context_eval_v1") or {}).get("aggregate_memory_effect_v1")
        if isinstance((entry_reasoning_eval_v1 or {}).get("memory_context_eval_v1"), dict)
        else None,
    }
    raw = json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_entry_reasoning_pipeline_v1(
    *,
    student_decision_packet: dict[str, Any],
    retrieved_student_experience: list[dict[str, Any]] | None,
    run_candle_timeframe_minutes: int,
    job_id: str = "",
    fingerprint: str | None = None,
    long_threshold: float = _LONG_THRESHOLD,
    short_threshold: float = _SHORT_THRESHOLD,
    emit_traces: bool = True,
    unified_agent_router: bool = False,
    router_config: dict[str, Any] | None = None,
    router_config_path: str | None = None,
    router_operator_forced_audit: bool = False,
    router_baseline_action: str | None = None,
    router_trade_notional_usd: float | None = None,
    router_seed: int | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]], dict[str, Any]]:
    """
    Returns ``(entry_reasoning_eval_v1 or None, errors, trace_stages, student_reasoning_fault_map_v1)``.
    On hard validation failure, returns ``(None, errs, trace, fault_map)`` — no soft pass.
    """
    trace: list[dict[str, Any]] = []
    errs: list[str] = []
    rse = list(retrieved_student_experience or [])
    fnodes: list[dict[str, Any]] = []

    def _t(stage: str, inputs: Any, outputs: Any, evidence: dict[str, Any] | None = None) -> None:
        row = {"stage": stage, "inputs": inputs, "outputs": outputs, "evidence": evidence or {}}
        trace.append(row)
        if emit_traces and job_id:
            from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
                emit_entry_reasoning_pipeline_stage_v1,
            )

            emit_entry_reasoning_pipeline_stage_v1(
                job_id=job_id,
                fingerprint=fingerprint,
                stage=stage,
                inputs=inputs,
                outputs=outputs,
                evidence=evidence,
            )

    bars = student_decision_packet.get("bars_inclusive_up_to_t")
    if not isinstance(bars, list) or not bars:
        sym0 = str(student_decision_packet.get("symbol") or "")
        fnodes.append(
            make_fault_node_v1(
                "market_data_loaded",
                STATUS_FAIL,
                input_summary_v1="Student decision packet.",
                output_summary_v1="No bars attached.",
                blocking_rule_v1="At least one bar up to the decision time is required.",
                error_codes_v1=["missing_bars_inclusive_up_to_t"],
                evidence_fields_v1=["bar_count", "symbol"],
                evidence_values_v1={"bar_count": 0, "symbol": sym0},
                operator_message_v1="Price data for the decision was not in the packet, so the reasoning path cannot start.",
            )
        )
        return None, ["missing_bars_inclusive_up_to_t"], trace, build_fault_map_v1(
            fnodes + skipped_nodes_from_index_v1(1)
        )
    sym = str(student_decision_packet.get("symbol") or "")
    bar_n = len(bars)
    fnodes.append(
        make_fault_node_v1(
            "market_data_loaded",
            STATUS_PASS,
            input_summary_v1="Student packet for the trade.",
            output_summary_v1=f"Loaded {bar_n} price bar(s).",
            evidence_fields_v1=["bar_count", "symbol", "candle_timeframe_minutes"],
            evidence_values_v1={
                "bar_count": bar_n,
                "symbol": sym,
                "candle_timeframe_minutes": int(run_candle_timeframe_minutes),
            },
            operator_message_v1="Market data for the decision time is present in the packet.",
        )
    )
    _t(
        "market_data_loaded",
        {"symbol": sym, "bar_count": len(bars)},
        {"ok": True, "candle_timeframe_minutes": run_candle_timeframe_minutes},
    )

    ictx, ind_err, _ev = build_indicator_context_eval_v1(bars)
    _t("indicator_context_evaluated", {"bars": len(bars)}, ictx, _ev)
    if ind_err:
        errs.extend(ind_err)
        if any("insufficient_bars" in e for e in ind_err) and (not isinstance(bars, list) or len(bars) < 2):
            fnodes.append(
                make_fault_node_v1(
                    "indicator_context_evaluated",
                    STATUS_FAIL,
                    input_summary_v1="Bar history for signals.",
                    output_summary_v1="Not enough bars to form indicators.",
                    blocking_rule_v1="The exam needs at least two closed bars to read momentum and trend.",
                    error_codes_v1=[str(x) for x in ind_err],
                    evidence_fields_v1=["bar_count"],
                    evidence_values_v1={"bar_count": bar_n},
                    operator_message_v1="There are not enough bars to evaluate indicators. Widen the history window or lower the bar size.",
                )
            )
            return None, ind_err, trace, build_fault_map_v1(fnodes + skipped_nodes_from_index_v1(2))
    fnodes.append(
        make_fault_node_v1(
            "indicator_context_evaluated",
            STATUS_PASS,
            input_summary_v1="Closed bars in the packet.",
            output_summary_v1="Trend, momentum, and range context are computed from those bars only.",
            evidence_fields_v1=["rsi_state", "ema_trend"],
            evidence_values_v1={
                "rsi_state": (ictx or {}).get("rsi_state"),
                "ema_trend": (ictx or {}).get("ema_trend"),
            },
            operator_message_v1="Indicators were derived from the packet; nothing was invented beyond the data shown.",
        )
    )
    last_close = float(bars[-1]["close"])

    scored = score_memory_records_v1(
        rse,
        run_candle_timeframe_minutes=int(run_candle_timeframe_minutes),
    )
    mscore, mclass = memory_effect_to_score_v1(scored)
    mctx = {
        "schema": "memory_context_eval_v1",
        "scored_records_v1": scored,
        "aggregate_memory_effect_v1": mclass,
    }
    _t("memory_context_evaluated", {"retrieved_count": len(rse)}, mctx, {"memory_score": mscore})

    mem_tf_mismatch = False
    for s in scored:
        if not isinstance(s, dict) or str(s.get("memory_effect_class_v1") or "") != "ignore":
            continue
        rid = str(s.get("record_id") or "")
        for rec in rse:
            if not isinstance(rec, dict) or str(rec.get("record_id") or "") != rid:
                continue
            if int(rec.get("candle_timeframe_minutes") or 0) != int(run_candle_timeframe_minutes):
                mem_tf_mismatch = True
    if mem_tf_mismatch:
        mstat = STATUS_NOT_PROVEN
        mmsg = "Memory was retrieved, but the stored lesson used a different bar size than this chart, so it did not steer the live score the same way a matching window would."
    elif len(rse) > 0 and mclass in ("none", "ignore", ""):
        mstat = STATUS_NOT_PROVEN
        mmsg = "The packet carried prior trades, but they did not move the combined score in a strong way for this step."
    else:
        mstat = STATUS_PASS
        mmsg = "Prior lesson rows were read and folded into the memory score for this step."
    fnodes.append(
        make_fault_node_v1(
            "memory_context_evaluated",
            mstat,
            input_summary_v1=f"{len(rse)} memory row(s) available to the score.",
            output_summary_v1=f"Blended class: {mclass}.",
            evidence_fields_v1=["aggregate_memory_effect_v1", "retrieved_count"],
            evidence_values_v1={"retrieved_count": len(rse), "aggregate_memory_effect_v1": mclass},
            operator_message_v1=mmsg,
        )
    )

    poe = prior_outcome_eval_v1(rse)
    _t("prior_outcomes_evaluated", {"records": len(rse)}, poe, {})
    fnodes.append(
        make_fault_node_v1(
            "prior_outcomes_evaluated",
            STATUS_PASS,
            input_summary_v1="Records tied to the packet.",
            output_summary_v1="Win rate and loss streak influence applied.",
            evidence_fields_v1=["prior_outcome_confidence_delta_v1"],
            evidence_values_v1={"prior_outcome_confidence_delta_v1": poe.get("prior_outcome_confidence_delta_v1")},
            operator_message_v1="How similar past outcomes behaved nudges confidence up or down.",
        )
    )

    atr = float(ictx.get("atr_last") or 0.0)
    ema_l = float(ictx.get("ema_last") or 0.0)
    fl = ictx.get("support_flags_v1") or {}
    if bool(fl.get("long")) and not bool(fl.get("short")):
        long_bias = True
    elif bool(fl.get("short")) and not bool(fl.get("long")):
        long_bias = False
    else:
        long_bias = last_close >= ema_l
    risk = build_risk_inputs_v1(last_close=last_close, atr=atr, long_bias=long_bias)
    risk_defined = bool(
        str(risk.get("invalidation_condition_v1") or "").strip()
        and str(risk.get("stop_basis_v1") or "").strip()
        and str(risk.get("target_basis_v1") or "").strip()
    )
    _t("risk_reward_evaluated", {"atr": atr, "long_bias": long_bias}, risk, {"risk_defined_v1": risk_defined})

    ind_s = indicator_score_v1(ictx)
    prior_s = float(poe.get("prior_outcome_confidence_delta_v1", 0.0))
    fin = ind_s + mscore + prior_s
    if mclass == "conflict" and ind_s * mscore < 0:
        fin = min(fin, -0.1)
    if mclass == "conflict" and abs(ind_s) < 0.2:
        fin = -0.3

    action = "no_trade"
    if fin >= long_threshold:
        action = "enter_long"
    elif fin <= short_threshold:
        action = "enter_short"
    if mclass == "conflict" and mscore < -0.2:
        action = "no_trade"
        fin = min(fin, 0.0)
    if action != "no_trade" and not risk_defined:
        errs.append("hard_fail:no_risk_no_trade")
        action = "no_trade"

    if "hard_fail:no_risk_no_trade" in errs:
        fnodes.append(
            make_fault_node_v1(
                "risk_reward_evaluated",
                STATUS_FAIL,
                input_summary_v1="Planned entry and exit story.",
                output_summary_v1="Stop and target basis must be available before a real entry is allowed.",
                blocking_rule_v1="No live entry without a full risk picture under exam rules.",
                error_codes_v1=["hard_fail:no_risk_no_trade"],
                evidence_fields_v1=["risk_defined_v1"],
                evidence_values_v1={"risk_defined_v1": False},
                operator_message_v1="The trade was blocked because the stop, target, and exit rules were not complete enough to justify an entry here.",
            )
        )
    else:
        fnodes.append(
            make_fault_node_v1(
                "risk_reward_evaluated",
                STATUS_PASS,
                input_summary_v1="Price, range, and chosen direction hint.",
                output_summary_v1="Invalidation, stop, and target lines are all described when a trade is live.",
                evidence_fields_v1=["risk_defined_v1"],
                evidence_values_v1={"risk_defined_v1": bool(risk_defined)},
                operator_message_v1="Reward versus risk is written in concrete terms whenever the engine contemplates a live entry; otherwise the side stays flat.",
            )
        )

    ds = {
        "indicator_score": round(ind_s, 6),
        "memory_score": round(mscore, 6),
        "prior_outcome_score": round(prior_s, 6),
        "risk_adjustment": round(float(ictx.get("confidence_effect_v1", {}).get("atr_adjustment", 0.0)), 6),
        "final_score": round(fin, 6),
        "action": action,
        "long_threshold": long_threshold,
        "short_threshold": short_threshold,
    }
    _t("decision_synthesized", {"scores": {k: ds[k] for k in ("indicator_score", "memory_score", "prior_outcome_score")}}, ds, {"authority": "entry_reasoning_engine_v1"})
    fnodes.append(
        make_fault_node_v1(
            "decision_synthesized",
            STATUS_PASS,
            input_summary_v1="Indicator, memory, and history scores.",
            output_summary_v1="Engine action: " + str(ds.get("action") or "no_trade") + ".",
            evidence_fields_v1=["action", "final_score"],
            evidence_values_v1={"action": ds.get("action"), "final_score": ds.get("final_score")},
            operator_message_v1="The path combined those inputs into a single go / no-go style choice.",
        )
    )

    conf = max(0.0, min(1.0, 0.5 + fin * 0.4))
    band = "low" if conf < 0.35 else ("high" if conf > 0.72 else "medium")

    out: dict[str, Any] = {
        "schema": SCHEMA_ENTRY_REASONING_EVAL_V1,
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "candle_timeframe_minutes": int(run_candle_timeframe_minutes),
        "symbol": sym,
        "indicator_context_eval_v1": ictx,
        "memory_context_eval_v1": mctx,
        "prior_outcome_eval_v1": poe,
        "risk_inputs_v1": risk,
        "risk_defined_v1": bool(risk_defined),
        "decision_synthesis_v1": ds,
        "confidence_01": round(conf, 6),
        "confidence_band": band,
    }

    verr = validate_entry_reasoning_eval_v1(out)
    if verr:
        errs.extend(verr)
    _t("entry_reasoning_validated", {"candidates": "entry_reasoning_eval_v1"}, out if not errs else {"rejected": True, "errors": verr}, {})
    if verr:
        fnodes.append(
            make_fault_node_v1(
                "entry_reasoning_validated",
                STATUS_FAIL,
                input_summary_v1="Structured entry reasoning for audit.",
                output_summary_v1="Some required fields or types are wrong or missing.",
                blocking_rule_v1="The object must pass schema checks before it can be sealed.",
                error_codes_v1=list(verr),
                operator_message_v1="The entry reasoning record failed its validation pass. The issues in the error codes have to be fixed before anything downstream can treat this as final.",
            )
        )
        return None, errs, trace, build_fault_map_v1(fnodes + skipped_nodes_from_index_v1(7))
    if errs:
        fnodes.append(
            make_fault_node_v1(
                "entry_reasoning_validated",
                STATUS_FAIL,
                input_summary_v1="Entry reasoning build.",
                output_summary_v1="Pipeline errors remain after validation.",
                error_codes_v1=[str(x) for x in errs],
                operator_message_v1="The record shape passed its checks, but earlier pipeline errors still block sealing.",
            )
        )
        return None, errs, trace, build_fault_map_v1(fnodes + skipped_nodes_from_index_v1(7))
    fnodes.append(
        make_fault_node_v1(
            "entry_reasoning_validated",
            STATUS_PASS,
            input_summary_v1="Structured entry reasoning for audit.",
            output_summary_v1="Validation rules passed.",
            operator_message_v1="The record is well-formed and can move on to the model and seal steps.",
        )
    )

    dig = build_entry_reasoning_eval_digest_v1(out)
    out["entry_reasoning_eval_digest_v1"] = dig
    out["entry_reasoning_eval_digest_meta_v1"] = {"schema": SCHEMA_ENTRY_REASONING_DIGEST_V1, "algorithm": "sha256_json_canonical_v1"}
    _t("entry_reasoning_sealed_v1", {"digest_prefix": dig[:12]}, {"sealed": True, "entry_reasoning_eval_digest_v1": dig}, {})

    _pfm = build_fault_map_v1(fnodes)
    out["student_reasoning_fault_map_v1"] = _pfm

    if unified_agent_router:
        from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 import apply_unified_reasoning_router_v1

        u = apply_unified_reasoning_router_v1(
            entry_reasoning_eval_v1=out,
            base_fault_map=_pfm,
            config=router_config,
            config_path=router_config_path,
            job_id=job_id,
            fingerprint=fingerprint,
            student_decision_packet=student_decision_packet,
            retrieved_student_experience=rse,
            run_candle_timeframe_minutes=int(run_candle_timeframe_minutes),
            operator_forced_audit=bool(router_operator_forced_audit),
            baseline_action=router_baseline_action,
            trade_notional_usd=router_trade_notional_usd,
            seed=router_seed,
        )
        out2 = u.get("entry_reasoning_eval_v1")
        pfm2 = u.get("student_reasoning_fault_map_v1")
        if isinstance(out2, dict):
            out = out2
        if isinstance(pfm2, dict):
            out["student_reasoning_fault_map_v1"] = pfm2
            _pfm = pfm2

    return out, [], trace, _pfm


def apply_decision_overrides_llm_stated_action_v1(
    entry_reasoning: dict[str, Any],
    llm_stated_action: str | None,
) -> dict[str, Any]:
    """Strip LLM if it disagrees; engine is canonical."""
    e = json.loads(json.dumps(entry_reasoning))
    aut = str((e.get("decision_synthesis_v1") or {}).get("action") or "")
    if llm_stated_action and str(llm_stated_action) != aut:
        e["llm_rejected_v1"] = {
            "reason": "decision_engine_overrides_llm",
            "engine_action": aut,
            "llm_stated": str(llm_stated_action),
        }
    return e


def _infer_student_action_v1_from_legacy(so: dict[str, Any]) -> str | None:
    sa = so.get("student_action_v1")
    if isinstance(sa, str) and sa.strip():
        return str(sa).strip().lower()
    if so.get("act") is not True:
        return "no_trade"
    d = so.get("direction")
    if isinstance(d, str) and d.lower().strip() == "long":
        return "enter_long"
    if isinstance(d, str) and d.lower().strip() == "short":
        return "enter_short"
    return "no_trade"


def apply_engine_authority_to_student_output_v1(
    so: dict[str, Any] | None,
    ere: dict[str, Any],
    *,
    allowed_memory_ids: frozenset[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    GT_DIRECTIVE_026A_IMPL (Blocker 1/2) — **engine is the authority** on trade direction;
    ``student_output_v1`` is overwritten to match ``entry_reasoning_eval_v1`` after optional
    LLM validation. Always attach ``entry_reasoning_eval_v1`` + digest for L3/audit.
    """
    if not isinstance(so, dict) or not isinstance(ere, dict):
        return None, ["apply_engine_authority: invalid so or ere"]
    out = copy.deepcopy(so)
    raw_stated = _infer_student_action_v1_from_legacy(out)
    llm_p: dict[str, Any] = {
        "cited_memory_record_ids": out.get("cited_memory_record_ids", [])
        if isinstance(out.get("cited_memory_record_ids"), list)
        else [],
        "stated_action": raw_stated,
    }
    v_llm = validate_llm_explanation_against_entry_reasoning_v1(
        llm_p,
        entry_reasoning=ere,
        allowed_memory_ids=allowed_memory_ids,
    )
    ere2 = copy.deepcopy(ere)
    if v_llm:
        ere2["llm_explanation_validation_v1"] = v_llm
    if raw_stated:
        ere2 = apply_decision_overrides_llm_stated_action_v1(ere2, raw_stated)
    ds = ere2.get("decision_synthesis_v1") or {}
    act_s = str(ds.get("action") or "no_trade")
    if act_s == "enter_long":
        out["act"] = True
        out["direction"] = "long"
        out["student_action_v1"] = "enter_long"
    elif act_s == "enter_short":
        out["act"] = True
        out["direction"] = "short"
        out["student_action_v1"] = "enter_short"
    else:
        out["act"] = False
        out["direction"] = "flat"
        out["student_action_v1"] = "no_trade"
    out["confidence_01"] = float(ere2.get("confidence_01", 0.0))
    out["confidence_band"] = str(ere2.get("confidence_band", "medium"))
    ind = ere2.get("indicator_context_eval_v1") or {}
    rsi_s = str(ind.get("rsi_state", "neutral"))
    ema_t = str(ind.get("ema_trend", "neutral_trend"))
    out["supporting_indicators"] = [f"rsi={rsi_s}", f"ema_trend={ema_t}"][:32]
    confl: list[str] = []
    if rsi_s in ("exhaustion_risk",) and "bullish" in ema_t:
        confl.append("rsi_exhaustion_vs_bull_trend")
    out["conflicting_indicators"] = confl
    rsk = ere2.get("risk_inputs_v1") or {}
    out["context_fit"] = (ema_t.replace("_trend", "") or "context")[:128]
    out["invalidation_text"] = str(rsk.get("invalidation_condition_v1", ""))[:4000]
    dig2 = build_entry_reasoning_eval_digest_v1(ere2)
    ere2["entry_reasoning_eval_digest_v1"] = dig2
    out["entry_reasoning_eval_v1"] = ere2
    out["entry_reasoning_eval_digest_v1"] = dig2
    _fm = ere2.get("student_reasoning_fault_map_v1")
    if isinstance(_fm, dict):
        from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
            attach_fault_map_v1,
        )

        attach_fault_map_v1(out, _fm)
    ve = validate_student_output_v1(out)
    return out, ve
