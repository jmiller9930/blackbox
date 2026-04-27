"""
GT_DIRECTIVE_026B — full trade lifecycle reasoning (per-bar, deterministic, 026AI-router compatible).
"""

from __future__ import annotations

import copy
from typing import Any

from renaissance_v4.game_theory.student_proctor.contracts_v1 import CONTRACT_VERSION_STUDENT_PROCTOR_V1
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    build_indicator_context_eval_v1,
    indicator_score_v1,
    memory_effect_to_score_v1,
    prior_outcome_eval_v1,
    score_memory_records_v1,
)
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import merge_lifecycle_reasoning_fault_nodes_v1
SCHEMA_LIFECYCLE = "lifecycle_reasoning_eval_v1"
CONTRACT_LIFECYCLE = 1

# Exit reason codes (subset; extensible)
EXIT_CODE_THESIS_INVALIDATED = "thesis_invalidated_v1"
EXIT_CODE_STOP_HIT = "stop_hit_v1"
EXIT_CODE_TARGET_HIT = "target_hit_v1"
EXIT_CODE_TIME_EXPIRED = "time_expired_v1"
EXIT_CODE_CONFIDENCE_COLLAPSE = "confidence_collapse_v1"
EXIT_CODE_OPPOSING_SIGNAL = "opposing_signal_strength_v1"
EXIT_CODE_NONE = ""

RISK_STABLE = "stable"
RISK_TIGHTENING = "tightening"
RISK_ELEVATED = "elevated"
RISK_BREACHED = "breached"

PHASE_ENTRY = "entry"
PHASE_HOLD = "hold"
PHASE_MANAGE = "manage"
PHASE_EXIT = "exit"

DEC_HOLD = "hold"
DEC_REDUCE = "reduce"  # reserved; engine maps to hold (026B non-goal)
DEC_EXIT = "exit"
DEC_FORCE = "force_exit"


def build_entry_thesis_v1(
    *,
    side: str,
    entry_reasoning_eval_v1: dict[str, Any],
) -> dict[str, Any]:
    """Snapshot thesis at entry from sealed entry record (reproducible)."""
    ds = (entry_reasoning_eval_v1 or {}).get("decision_synthesis_v1") or {}
    ictx = (entry_reasoning_eval_v1 or {}).get("indicator_context_eval_v1") or {}
    risk = (entry_reasoning_eval_v1 or {}).get("risk_inputs_v1") or {}
    return {
        "schema": "entry_thesis_v1",
        "contract_version": CONTRACT_LIFECYCLE,
        "side_v1": str(side or "").lower(),
        "summary_english_v1": f"side={side}; entry engine action was {ds.get('action')!s}; ema_trend={ictx.get('ema_trend')!s}; rsi_state={ictx.get('rsi_state')!s}.",
        "invalidation_rules_text_v1": str(risk.get("invalidation_condition_v1") or ""),
        "entry_confidence_01": float((entry_reasoning_eval_v1 or {}).get("confidence_01") or 0.0),
    }


def _bars_up_to(
    all_bars: list[dict[str, Any]], last_index: int
) -> list[dict[str, Any]]:
    if last_index < 0 or not all_bars:
        return []
    u = min(last_index, len(all_bars) - 1)
    return [dict(b) for b in all_bars[: u + 1]]


def _synthetic_entry_for_router_v1(
    lifecycle_eval: dict[str, Any],
) -> dict[str, Any]:
    """
    Map lifecycle bar eval to a minimal entry_reasoning_eval_v1 for 026AI router reuse (advisory only).
    """
    le = dict(lifecycle_eval or {})
    ictx = le.get("indicator_context_eval_v1")
    mctx = le.get("memory_context_eval_v1")
    conf = float(le.get("confidence_01") or 0.0)
    return {
        "schema": "entry_reasoning_eval_v1",
        "contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "candle_timeframe_minutes": int(le.get("candle_timeframe_minutes") or 0),
        "symbol": str(le.get("symbol") or ""),
        "indicator_context_eval_v1": ictx if isinstance(ictx, dict) else {},
        "memory_context_eval_v1": mctx if isinstance(mctx, dict) else {"schema": "memory_context_eval_v1"},
        "prior_outcome_eval_v1": le.get("prior_outcome_eval_v1") or {"schema": "prior_outcome_eval_v1"},
        "risk_inputs_v1": le.get("risk_inputs_v1") or {},
        "risk_defined_v1": bool(le.get("risk_defined_v1", True)),
        "decision_synthesis_v1": {
            "indicator_score": 0.0,
            "memory_score": 0.0,
            "prior_outcome_score": 0.0,
            "risk_adjustment": 0.0,
            "final_score": conf - 0.5,
            "action": "no_trade",
            "long_threshold": 0.2,
            "short_threshold": -0.2,
        },
        "confidence_01": max(0.0, min(1.0, conf)),
        "confidence_band": "low" if conf < 0.35 else "medium",
    }


def apply_unified_reasoning_router_for_lifecycle_v1(
    *,
    lifecycle_reasoning_eval_v1: dict[str, Any],
    base_fault_map: dict[str, Any],
    config: dict[str, Any] | None = None,
    config_path: str | None = None,
    job_id: str = "",
    fingerprint: str | None = None,
    student_decision_packet: dict[str, Any] | None = None,
    retrieved_student_experience: list[dict[str, Any]] | None = None,
    run_candle_timeframe_minutes: int = 5,
    operator_forced_audit: bool = False,
    baseline_action: str | None = None,
    trade_notional_usd: float | None = None,
    seed: int | None = None,
    scenario_id: str | None = None,
    trade_id: str | None = None,
) -> dict[str, Any]:
    """Reuses 026AI router on a synthetic entry slice built from the current lifecycle bar (advisory; engine rules stay in lifecycle eval)."""
    from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_v1 import apply_unified_reasoning_router_v1

    syn = _synthetic_entry_for_router_v1(lifecycle_reasoning_eval_v1)
    u = apply_unified_reasoning_router_v1(
        entry_reasoning_eval_v1=syn,
        base_fault_map=base_fault_map,
        config=config,
        config_path=config_path,
        job_id=job_id,
        fingerprint=fingerprint,
        student_decision_packet=student_decision_packet,
        retrieved_student_experience=retrieved_student_experience,
        run_candle_timeframe_minutes=run_candle_timeframe_minutes,
        operator_forced_audit=operator_forced_audit,
        baseline_action=baseline_action,
        trade_notional_usd=trade_notional_usd,
        seed=seed,
        scenario_id=scenario_id,
        trade_id=trade_id,
    )
    out = dict(lifecycle_reasoning_eval_v1)
    udec = u.get("reasoning_router_decision_v1")
    if udec:
        out["reasoning_router_decision_lifecycle_v1"] = udec
    urev = u.get("external_reasoning_review_v1")
    if urev:
        out["external_reasoning_review_lifecycle_v1"] = urev
    leg = (u.get("entry_reasoning_eval_v1") or {}).get("external_api_call_ledger_v1")
    if leg:
        out["external_api_call_ledger_lifecycle_v1"] = leg
    fm = u.get("student_reasoning_fault_map_v1")
    if isinstance(fm, dict):
        out["student_reasoning_fault_map_v1"] = fm
    return {
        "lifecycle_reasoning_eval_v1": out,
        "student_reasoning_fault_map_v1": fm if isinstance(fm, dict) else base_fault_map,
        "reasoning_router_decision_v1": udec,
        "external_reasoning_review_v1": urev,
    }


def evaluate_lifecycle_bar_v1(
    *,
    all_bars: list[dict[str, Any]],
    current_bar_index: int,
    entry_bar_index: int,
    side: str,
    entry_thesis_v1: dict[str, Any],
    entry_atr: float,
    entry_price: float,
    run_candle_timeframe_minutes: int,
    symbol: str,
    retrieved_student_experience: list[dict[str, Any]] | None,
    initial_confidence_01: float,
    max_hold_bars: int = 32,
    prior_confidence_01: float | None = None,
    entry_confidence_01: float | None = None,
    stop_atr_mult: float = 1.2,
    target_r_multiple: float = 2.0,
    opposing_bar_streak: int = 0,
    degrading_streak: int = 0,
    retrieved_lifecycle_deterministic_learning_026c_v1: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    One bar of lifecycle reasoning. Deterministic; does not call HTTP (router is separate call).
    """
    errs: list[str] = []
    side = str(side or "").lower()
    if side not in ("long", "short"):
        errs.append("invalid_side")
    window = _bars_up_to(all_bars, current_bar_index)
    if not window or current_bar_index < entry_bar_index:
        errs.append("insufficient_bars")
    b_in_trade = max(0, current_bar_index - entry_bar_index)
    exit_reason = EXIT_CODE_NONE
    dec = DEC_HOLD
    phase = PHASE_ENTRY if b_in_trade == 0 else PHASE_HOLD

    if errs:
        ev = {
            "schema": SCHEMA_LIFECYCLE,
            "contract_version": CONTRACT_LIFECYCLE,
            "error_codes_v1": errs,
            "bar_index_in_packet_v1": int(current_bar_index),
            "bar_index_in_trade_v1": b_in_trade,
        }
        st = build_lifecycle_reasoning_stage_v1(
            bar_index=current_bar_index,
            bar_in_trade=b_in_trade,
            phase=phase,
            decision="error",
            confidence_01=0.0,
            thesis_state="error",
            risk_state="unknown",
        )
        fm = merge_lifecycle_reasoning_fault_nodes_v1(
            {"schema": "student_reasoning_fault_map_v1", "contract_version": 1, "nodes_v1": []},
            context_loaded_ok=False,
            reasoning_eval_ok=False,
            decision_ok=False,
            exit_eval_ok=False,
            operator_messages={"lifecycle_context_loaded": "Lifecycle context could not be built for this bar."},
        )
        return {
            "lifecycle_reasoning_eval_v1": ev,
            "lifecycle_reasoning_stage_v1": st,
            "student_reasoning_fault_map_v1": fm,
        }

    last = window[-1]
    close = float(last["close"])
    high = float(last["high"])
    low = float(last["low"])
    atr = float((build_indicator_context_eval_v1(window)[0] or {}).get("atr_last") or 0.0) or 1e-9
    ictx, _, _ = build_indicator_context_eval_v1(window)
    scored = score_memory_records_v1(
        list(retrieved_student_experience or []),
        run_candle_timeframe_minutes=int(run_candle_timeframe_minutes),
    )
    mscore, mclass = memory_effect_to_score_v1(scored)
    mctx = {
        "schema": "memory_context_eval_v1",
        "scored_records_v1": scored,
        "aggregate_memory_effect_v1": mclass,
    }
    poe = prior_outcome_eval_v1(list(retrieved_student_experience or []))
    rbase = max(entry_atr * stop_atr_mult, 1e-9)
    if side == "long":
        stop_px = entry_price - rbase
        target_px = entry_price + rbase * target_r_multiple
    else:
        stop_px = entry_price + rbase
        target_px = entry_price - rbase * target_r_multiple
    u_pnl = (close - entry_price) / max(entry_price, 1e-9) if side == "long" else (entry_price - close) / max(
        entry_price, 1e-9
    )
    r_unreal = (close - entry_price) / rbase if side == "long" else (entry_price - close) / rbase

    ind_s = indicator_score_v1(ictx)
    if side == "short":
        ind_against = ind_s < -0.1
    else:
        ind_against = ind_s < -0.1
    ema = str(ictx.get("ema_trend") or "")
    if side == "long" and "bear" in ema:
        ind_against = True
    if side == "short" and "bull" in ema:
        ind_against = True

    thesis_degrading = bool(mclass == "conflict" or ind_against)
    if thesis_degrading:
        degrading_streak = int(degrading_streak) + 1
    else:
        degrading_streak = 0
    if ind_against:
        opposing_bar_streak = int(opposing_bar_streak) + 1
    else:
        opposing_bar_streak = 0

    thesis_invalid = degrading_streak >= 3 or (ind_against and "exhaust" in str(ictx.get("rsi_state") or ""))
    t_upd = "Thesis still aligned with tape."
    if thesis_degrading and not thesis_invalid:
        t_upd = "Tape shows stress vs entry thesis; monitoring."
    if thesis_invalid:
        t_upd = "Thesis no longer supported by current indicator regime."

    base_c = float(prior_confidence_01) if prior_confidence_01 is not None else float(
        entry_confidence_01 if entry_confidence_01 is not None else initial_confidence_01
    )
    conf = max(0.0, min(1.0, base_c + 0.02 * (1.0 if not thesis_degrading else -0.12)))
    conf = max(0.0, min(1.0, conf + float(poe.get("prior_outcome_confidence_delta_v1") or 0.0) * 0.15))
    l026 = [x for x in (retrieved_lifecycle_deterministic_learning_026c_v1 or []) if isinstance(x, dict)][:8]
    if l026 and b_in_trade == 0:
        wsum = sum(float((x or {}).get("decay_weight_01") or 0.0) for x in l026) / max(1, len(l026))
        nudge = 0.02 * wsum * min(1.0, float(len(l026)) / 8.0)
        conf = max(0.0, min(1.0, conf + nudge))
    conf_delta = conf - float(prior_confidence_01) if prior_confidence_01 is not None else (
        conf - float(entry_confidence_01) if entry_confidence_01 is not None else 0.0
    )

    d_stop = (close - stop_px) / rbase if side == "long" else (stop_px - close) / rbase
    d_tgt = (target_px - close) / rbase if side == "long" else (close - target_px) / rbase
    if (side == "long" and low <= stop_px + 1e-9) or (side == "short" and high >= stop_px - 1e-9):
        risk = RISK_BREACHED
    elif d_stop < 0.4:
        risk = RISK_TIGHTENING
    elif atr / max(entry_atr, 1e-9) > 1.2:
        risk = RISK_ELEVATED
    else:
        risk = RISK_STABLE

    if risk in (RISK_TIGHTENING, RISK_ELEVATED) or thesis_degrading:
        phase = PHASE_MANAGE
    if b_in_trade == 0:
        phase = PHASE_ENTRY

    # exit order (first match)
    if side == "long" and low <= stop_px + 1e-9:
        dec, exit_reason, phase = DEC_FORCE, EXIT_CODE_STOP_HIT, PHASE_EXIT
    elif side == "short" and high >= stop_px - 1e-9:
        dec, exit_reason, phase = DEC_FORCE, EXIT_CODE_STOP_HIT, PHASE_EXIT
    elif side == "long" and high >= target_px - 1e-9:
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_TARGET_HIT, PHASE_EXIT
    elif side == "short" and low <= target_px + 1e-9:
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_TARGET_HIT, PHASE_EXIT
    elif thesis_invalid:
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_THESIS_INVALIDATED, PHASE_EXIT
    elif b_in_trade + 1 >= int(max_hold_bars):
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_TIME_EXPIRED, PHASE_EXIT
    elif conf < 0.2 and b_in_trade > 0:
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_CONFIDENCE_COLLAPSE, PHASE_EXIT
    elif opposing_bar_streak >= 2 and b_in_trade > 0:
        dec, exit_reason, phase = DEC_EXIT, EXIT_CODE_OPPOSING_SIGNAL, PHASE_EXIT
    else:
        dec = DEC_HOLD
        if dec == DEC_REDUCE:
            dec = DEC_HOLD  # 026B non-goal

    r_in = (entry_thesis_v1 or {}).get("invalidation_rules_text_v1", "")
    risk_inputs = {
        "schema": "lifecycle_risk_snapshot_v1",
        "stop_price_v1": round(stop_px, 6),
        "target_price_v1": round(target_px, 6),
        "distance_to_stop_r_v1": round(d_stop, 4),
        "distance_to_target_r_v1": round(d_tgt, 4),
        "atr_entry_v1": round(entry_atr, 6),
        "atr_now_v1": round(atr, 6),
        "entry_invalidation_text_v1": str(r_in)[:2000],
    }

    leval = {
        "schema": SCHEMA_LIFECYCLE,
        "contract_version": CONTRACT_LIFECYCLE,
        "symbol": symbol,
        "candle_timeframe_minutes": int(run_candle_timeframe_minutes),
        "bar_index_in_packet_v1": int(current_bar_index),
        "bar_index_in_trade_v1": b_in_trade,
        "phase_v1": phase,
        "time_in_trade_v1": b_in_trade,
        "entry_thesis_v1": copy.deepcopy(entry_thesis_v1),
        "thesis_valid_v1": bool(not thesis_invalid),
        "thesis_degrading_v1": bool(thesis_degrading and not thesis_invalid),
        "thesis_invalidated_v1": bool(thesis_invalid),
        "thesis_update_v1": t_upd,
        "confidence_01": round(conf, 6),
        "confidence_delta_v1": round(conf_delta, 6),
        "risk_state_v1": risk,
        "unrealized_pnl_r_multiple_v1": round(r_unreal, 6),
        "unrealized_pnl_fraction_v1": round(u_pnl, 8),
        "decision_v1": dec,
        "exit_reason_code_v1": exit_reason if dec in (DEC_EXIT, DEC_FORCE) else None,
        "indicator_context_eval_v1": ictx,
        "memory_context_eval_v1": mctx,
        "prior_outcome_eval_v1": poe,
        "risk_inputs_v1": risk_inputs,
        "risk_defined_v1": True,
        "opposing_bar_streak_v1": opposing_bar_streak,
        "thesis_degrading_streak_v1": degrading_streak,
    }
    if l026 and b_in_trade == 0:
        leval["deterministic_learning_context_026c_v1"] = {
            "slice_count_v1": len(l026),
            "max_decay_weight_01": max(
                (float((x or {}).get("decay_weight_01") or 0.0) for x in l026), default=0.0
            ),
        }
    st = build_lifecycle_reasoning_stage_v1(
        bar_index=current_bar_index,
        bar_in_trade=b_in_trade,
        phase=phase,
        decision=dec,
        confidence_01=conf,
        thesis_state="invalid" if thesis_invalid else ("degrading" if thesis_degrading else "valid"),
        risk_state=risk,
    )
    ctx_ok = True
    eval_ok = True
    dec_ok = True
    ex_ok = True
    fm = merge_lifecycle_reasoning_fault_nodes_v1(
        {"schema": "student_reasoning_fault_map_v1", "contract_version": 1, "nodes_v1": []},
        context_loaded_ok=ctx_ok,
        reasoning_eval_ok=eval_ok,
        decision_ok=dec_ok,
        exit_eval_ok=ex_ok,
    )
    return {
        "lifecycle_reasoning_eval_v1": leval,
        "lifecycle_reasoning_stage_v1": st,
        "student_reasoning_fault_map_v1": fm,
        "carry_degrading_streak_v1": degrading_streak,
        "carry_opposing_streak_v1": opposing_bar_streak,
        "carry_confidence_01": conf,
    }


def build_lifecycle_reasoning_stage_v1(
    *,
    bar_index: int,
    bar_in_trade: int,
    phase: str,
    decision: str,
    confidence_01: float,
    thesis_state: str,
    risk_state: str,
) -> dict[str, Any]:
    return {
        "schema": "lifecycle_reasoning_stage_v1",
        "contract_version": CONTRACT_LIFECYCLE,
        "bar_index_in_packet_v1": int(bar_index),
        "bar_index_in_trade_v1": int(bar_in_trade),
        "phase_v1": str(phase),
        "decision_v1": str(decision),
        "confidence_01": float(confidence_01),
        "thesis_state_v1": str(thesis_state),
        "risk_state_v1": str(risk_state),
    }


def run_lifecycle_tape_v1(
    *,
    all_bars: list[dict[str, Any]],
    entry_bar_index: int,
    side: str,
    entry_reasoning_eval_v1: dict[str, Any],
    run_candle_timeframe_minutes: int,
    symbol: str,
    retrieved_student_experience: list[dict[str, Any]] | None = None,
    max_hold_bars: int = 32,
    unified_agent_router: bool = False,
    router_config: dict[str, Any] | None = None,
    router_config_path: str | None = None,
    job_id: str = "",
    fingerprint: str | None = None,
    emit_lifecycle_traces: bool = False,
    trade_id: str | None = None,
    scenario_id: str | None = None,
    retrieved_lifecycle_deterministic_learning_026c_v1: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Walks forward from entry bar, one evaluation per bar, until exit or data end.
    If ``emit_lifecycle_traces`` and ``job_id`` are set, appends **lifecycle_reasoning_stage_v1** and
    **lifecycle_tape_summary_v1** to the learning-trace JSONL (same path as 026A/026R).
    """
    w = _bars_up_to(all_bars, entry_bar_index)
    l026 = [dict(x) for x in (retrieved_lifecycle_deterministic_learning_026c_v1 or []) if isinstance(x, dict)][:8]
    if not w:
        return {"schema": "lifecycle_tape_result_v1", "contract_version": 1, "error": "no_bars", "per_bar_v1": []}
    ict0, _, _ = build_indicator_context_eval_v1(w)
    atr0 = float(ict0.get("atr_last") or 0.0) or 1e-9
    entry_price = float(w[-1]["close"])
    thesis = build_entry_thesis_v1(side=side, entry_reasoning_eval_v1=entry_reasoning_eval_v1)
    c0 = float((entry_reasoning_eval_v1 or {}).get("confidence_01") or 0.5)
    d_streak = 0
    o_streak = 0
    prev_c: float | None = None
    out_rows: list[dict[str, Any]] = []
    last_fm: dict[str, Any] = {}

    def _emit_stage_row(row: dict[str, Any]) -> None:
        if not emit_lifecycle_traces or not str(job_id or "").strip():
            return
        stg = row.get("lifecycle_reasoning_stage_v1")
        if not isinstance(stg, dict):
            return
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
            emit_lifecycle_reasoning_stage_v1,
        )

        emit_lifecycle_reasoning_stage_v1(
            job_id=str(job_id).strip(),
            fingerprint=fingerprint,
            lifecycle_reasoning_stage_v1=stg,
            trade_id=trade_id,
            scenario_id=scenario_id,
        )

    def _emit_tape_done(res: dict[str, Any]) -> None:
        if not emit_lifecycle_traces or not str(job_id or "").strip():
            return
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import emit_lifecycle_tape_summary_v1

        emit_lifecycle_tape_summary_v1(
            job_id=str(job_id).strip(),
            fingerprint=fingerprint,
            lifecycle_tape_result_v1=res,
            trade_id=trade_id,
            scenario_id=scenario_id,
        )

    for i in range(entry_bar_index, len(all_bars)):
        r = evaluate_lifecycle_bar_v1(
            all_bars=all_bars,
            current_bar_index=i,
            entry_bar_index=entry_bar_index,
            side=side,
            entry_thesis_v1=thesis,
            entry_atr=atr0,
            entry_price=entry_price,
            run_candle_timeframe_minutes=run_candle_timeframe_minutes,
            symbol=symbol,
            retrieved_student_experience=retrieved_student_experience,
            initial_confidence_01=c0,
            entry_confidence_01=c0,
            max_hold_bars=max_hold_bars,
            prior_confidence_01=prev_c,
            degrading_streak=d_streak,
            opposing_bar_streak=o_streak,
            retrieved_lifecycle_deterministic_learning_026c_v1=l026,
        )
        d_streak = int(r.get("carry_degrading_streak_v1") or 0)
        o_streak = int(r.get("carry_opposing_streak_v1") or 0)
        prev_c = float((r.get("lifecycle_reasoning_eval_v1") or {}).get("confidence_01") or 0.0)
        ev = r.get("lifecycle_reasoning_eval_v1") or {}
        st = r.get("lifecycle_reasoning_stage_v1") or {}
        last_fm = r.get("student_reasoning_fault_map_v1") or last_fm
        row: dict[str, Any] = {
            "bar_index": i,
            "lifecycle_reasoning_eval_v1": ev,
            "lifecycle_reasoning_stage_v1": st,
        }
        if unified_agent_router and "error_codes_v1" not in ev:
            u = apply_unified_reasoning_router_for_lifecycle_v1(
                lifecycle_reasoning_eval_v1=ev,
                base_fault_map=last_fm,
                config=router_config,
                config_path=router_config_path,
                job_id=job_id,
                fingerprint=fingerprint,
                student_decision_packet={"symbol": symbol, "bars_inclusive_up_to_t": _bars_up_to(all_bars, i)},
                retrieved_student_experience=retrieved_student_experience,
                run_candle_timeframe_minutes=run_candle_timeframe_minutes,
                scenario_id=scenario_id,
                trade_id=trade_id,
            )
            le2 = u.get("lifecycle_reasoning_eval_v1")
            if isinstance(le2, dict):
                row["lifecycle_reasoning_eval_v1"] = le2
            if u.get("student_reasoning_fault_map_v1"):
                last_fm = u["student_reasoning_fault_map_v1"]  # type: ignore[assignment]
        out_rows.append(row)
        _emit_stage_row(row)
        d = (row.get("lifecycle_reasoning_eval_v1") or ev or {}).get("decision_v1")
        if d in (DEC_EXIT, DEC_FORCE):
            res: dict[str, Any] = {
                "schema": "lifecycle_tape_result_v1",
                "contract_version": CONTRACT_LIFECYCLE,
                "closed_v1": True,
                "exit_at_bar_index_v1": i,
                "exit_reason_code_v1": (row.get("lifecycle_reasoning_eval_v1") or ev or {}).get("exit_reason_code_v1"),
                "per_bar_v1": out_rows,
                "final_fault_map_v1": last_fm,
            }
            if l026:
                res["retrieved_lifecycle_deterministic_learning_026c_v1"] = l026
            _emit_tape_done(res)
            return res
    res = {
        "schema": "lifecycle_tape_result_v1",
        "contract_version": CONTRACT_LIFECYCLE,
        "closed_v1": False,
        "per_bar_v1": out_rows,
        "final_fault_map_v1": last_fm,
    }
    if l026:
        res["retrieved_lifecycle_deterministic_learning_026c_v1"] = l026
    _emit_tape_done(res)
    return res


__all__ = [
    "SCHEMA_LIFECYCLE",
    "build_entry_thesis_v1",
    "evaluate_lifecycle_bar_v1",
    "build_lifecycle_reasoning_stage_v1",
    "run_lifecycle_tape_v1",
    "apply_unified_reasoning_router_for_lifecycle_v1",
    "EXIT_CODE_THESIS_INVALIDATED",
    "EXIT_CODE_STOP_HIT",
    "EXIT_CODE_TARGET_HIT",
    "EXIT_CODE_TIME_EXPIRED",
    "EXIT_CODE_CONFIDENCE_COLLAPSE",
    "EXIT_CODE_OPPOSING_SIGNAL",
]
