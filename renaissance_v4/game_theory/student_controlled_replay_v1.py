"""
GT_DIRECTIVE_024C — Student-controlled replay lane (separate scored outcomes).

Orchestrates ``run_manifest_replay(..., student_execution_intent_v1=…)`` from the **parent**
process (after parallel workers return) so learning-trace JSONL is not written from workers.

Baseline/control rows are **not** modified; Student results are attached under
``student_controlled_replay_v1``.

Imports are mostly **lazy** to avoid a package cycle with :mod:`batch_scorecard` /
:mod:`exam_run_contract_v1`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXECUTION_LANE_BASELINE_CONTROL_V1 = "baseline_control"
EXECUTION_AUTHORITY_MANIFEST_V1 = "manifest"
EXECUTION_LANE_STUDENT_CONTROLLED_V1 = "student_controlled"
# 024C engine: Student lane only when baseline would admit an entry (baseline-gated), not full Student control.
EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1 = "baseline_gated_student"
EXECUTION_AUTHORITY_STUDENT_FULL_CONTROL_V1 = "student_full_control"
# Legacy alias — same 024C semantics; do not read as "full Student authority".
EXECUTION_AUTHORITY_STUDENT_THESIS_V1 = EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1


def outcomes_list_canonical_hash_v1(outcomes_json: list[dict[str, Any]] | None) -> str:
    """Deterministic SHA-256 over canonical JSON of outcome dicts (order preserved)."""
    raw = outcomes_json or []
    s = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _emit_student_lane_traces_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    intent: dict[str, Any],
    status_line: str,
    student_full_control_lane: bool = False,
) -> None:
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import _emit

    if not (job_id or "").strip():
        return
    digest = str(intent.get("student_execution_intent_digest_v1") or "")
    srcd = str(intent.get("source_student_output_digest_v1") or "")
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_EXECUTION_MODE_BASELINE_GATED_V1,
        STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1,
        normalize_student_reasoning_mode_v1,
        student_lane_authority_truth_v1,
    )

    pnorm = normalize_student_reasoning_mode_v1(
        str((intent.get("student_brain_profile_v1") or "") or "memory_context_student")
    )
    mode_for_truth = (
        STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1
        if student_full_control_lane
        else STUDENT_EXECUTION_MODE_BASELINE_GATED_V1
    )
    truth = student_lane_authority_truth_v1(
        student_execution_mode_v1=mode_for_truth,
        student_controlled_execution=True,
        profile=pnorm,
    )
    auth = (
        EXECUTION_AUTHORITY_STUDENT_FULL_CONTROL_V1
        if student_full_control_lane
        else EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1
    )
    eng = "024D_student_full_control" if student_full_control_lane else "024C_baseline_gated"
    summ = (
        "Student execution intent accepted (024D: student_full_control lane including fusion-veto path)."
        if student_full_control_lane
        else "Student execution intent accepted (024C: baseline_gated_student)."
    )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_execution_intent_consumed",
        status="pass",
        summary=summ,
        producer="student_controlled_replay_v1",
        scenario_id=scenario_id,
        evidence_payload={
            "execution_authority_v1": auth,
            "execution_authority_v1_engine_v1": eng,
            "student_lane_authority_truth_v1": truth[:2000],
            "student_execution_intent_digest_v1": digest,
            "source_student_output_digest_v1": srcd,
            "action": intent.get("action"),
            "direction": intent.get("direction"),
        },
    )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_controlled_replay_started",
        status="pass",
        summary=status_line[:2000],
        producer="student_controlled_replay_v1",
        scenario_id=scenario_id,
        evidence_payload={
            "execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
            "execution_authority_v1": auth,
        },
    )


def _emit_student_lane_complete_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    summary: str,
    student_outcomes_hash: str,
    execution_authority_v1: str = EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1,
) -> None:
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import _emit

    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="student_controlled_replay_completed",
        status="pass",
        summary=summary[:2000],
        producer="student_controlled_replay_v1",
        scenario_id=scenario_id,
        evidence_payload={
            "execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
            "execution_authority_v1": execution_authority_v1,
            "student_outcomes_hash_v1": student_outcomes_hash,
        },
    )


def _emit_referee_used_student_thesis_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    execution_authority_v1: str = EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1,
) -> None:
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import _emit

    summ = (
        "Student full-control lane completed (024D) — may include fusion no_trade + aligned-signal path."
        if execution_authority_v1 == EXECUTION_AUTHORITY_STUDENT_FULL_CONTROL_V1
        else "Student lane completed (024C: baseline_gated when fusion is directional; fusion-veto not used on this path)."
    )
    _emit(
        job_id=job_id,
        fingerprint=fingerprint,
        stage="referee_used_student_output",
        status="true",
        summary=summ,
        producer="student_controlled_replay_v1",
        scenario_id=scenario_id,
        evidence_payload={
            "execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
            "execution_authority_v1": execution_authority_v1,
            "referee_used_student_output": True,
        },
    )


def attach_student_controlled_replay_v1(
    scenario: dict[str, Any],
    result_row: dict[str, Any],
    *,
    job_id: str | None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Run Student-controlled replay in the **parent** process and attach to ``result_row``.

    **Does not** mutate baseline fields on ``result_row`` (control remains worker-produced).
    """
    from renaissance_v4.core.outcome_record import outcome_record_to_jsonable
    from renaissance_v4.game_theory.candle_timeframe_runtime import (
        extract_candle_timeframe_minutes_for_replay,
    )
    from renaissance_v4.game_theory.evaluation_window_runtime import (
        extract_calendar_months_for_replay,
    )
    from renaissance_v4.game_theory.pattern_game import (
        json_summary,
        prepare_effective_manifest_for_replay,
        score_binary_outcomes,
    )
    from renaissance_v4.game_theory.scenario_contract import referee_session_outcome
    from renaissance_v4.game_theory.student_proctor.student_execution_intent_v1 import (
        validate_student_execution_intent_v1,
    )
    from renaissance_v4.research.replay_runner import run_manifest_replay

    intent = scenario.get("student_execution_intent_v1")
    sid = str(scenario.get("scenario_id") or result_row.get("scenario_id") or "unknown")
    j_id = (job_id or scenario.get("_batch_job_id_v1") or sid or "unscoped").strip()
    full_lane = bool(scenario.get("student_full_control_lane_v1"))
    lane_auth = (
        EXECUTION_AUTHORITY_STUDENT_FULL_CONTROL_V1
        if full_lane
        else EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1
    )

    control_json = list(result_row.get("replay_outcomes_json") or [])
    control_h = outcomes_list_canonical_hash_v1(control_json)

    base_out: dict[str, Any] = {
        "execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
        "execution_authority_v1": lane_auth,
        "student_full_control_lane_v1": full_lane,
        "control_outcomes_hash_v1": control_h,
        "student_outcomes_hash_v1": control_h,
        "outcomes_hash_v1": control_h,
        "student_lane_status_v1": "not_run",
    }

    if not isinstance(intent, dict):
        base_out["student_lane_status_v1"] = "not_run"
        return base_out

    v_err = validate_student_execution_intent_v1(intent)
    if v_err:
        base_out["student_lane_status_v1"] = "intent_invalid"
        base_out["student_lane_error_detail_v1"] = "; ".join(v_err)[:2000]
        return base_out

    mbp = scenario.get("memory_bundle_path")
    if mbp:
        mbp = str(Path(mbp).expanduser().resolve())
    else:
        mbp = None

    bar_m = extract_calendar_months_for_replay(scenario)
    candle_tf = extract_candle_timeframe_minutes_for_replay(scenario)

    _emit_student_lane_traces_v1(
        job_id=j_id,
        fingerprint=fingerprint,
        scenario_id=sid,
        intent=intent,
        status_line="Starting run_manifest_replay with student_execution_intent_v1 (DCR off).",
        student_full_control_lane=full_lane,
    )

    prep = prepare_effective_manifest_for_replay(
        scenario["manifest_path"],
        atr_stop_mult=scenario.get("atr_stop_mult"),
        atr_target_mult=scenario.get("atr_target_mult"),
        memory_bundle_path=mbp,
        use_groundhog_auto_resolve=False,
    )
    try:
        st_out = run_manifest_replay(
            prep.replay_path,
            emit_baseline_artifacts=False,
            verbose=False,
            bar_window_calendar_months=bar_m,
            candle_timeframe_minutes=candle_tf,
            decision_context_recall_enabled=False,
            student_execution_intent_v1=intent,
            student_full_control_lane_v1=full_lane,
        )
    except Exception as e:
        base_out["student_lane_status_v1"] = "replay_error"
        base_out["student_lane_error_detail_v1"] = f"{type(e).__name__}: {e}"[:2000]
        return base_out
    finally:
        prep.cleanup()

    st_json: list[dict[str, Any]] = []
    for item in st_out.get("outcomes") or []:
        if hasattr(item, "trade_id") and not isinstance(item, dict):
            st_json.append(outcome_record_to_jsonable(item))
        elif isinstance(item, dict):
            st_json.append(item)
    st_h = outcomes_list_canonical_hash_v1(st_json)
    summ = json_summary(st_out, scenario=scenario)
    bcard = score_binary_outcomes(list(st_out.get("outcomes") or []))
    st_session = referee_session_outcome(True, summ)
    ex = float((summ or {}).get("expectancy", 0.0) or 0.0) if isinstance(summ, dict) else 0.0
    trades = int(bcard.get("trades") or 0) if isinstance(bcard, dict) else 0
    base_summ = result_row.get("summary")
    base_ex = 0.0
    if isinstance(base_summ, dict):
        try:
            base_ex = float(base_summ.get("expectancy", 0.0) or 0.0)
        except (TypeError, ValueError):
            base_ex = 0.0

    sfc_audit = st_out.get("student_full_control_replay_audit_v1")
    base_out.update(
        {
            "execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
            "execution_authority_v1": lane_auth,
            "student_execution_intent_digest_v1": intent.get("student_execution_intent_digest_v1"),
            "source_student_output_digest_v1": intent.get("source_student_output_digest_v1"),
            "outcomes_hash_v1": st_h,
            "control_outcomes_hash_v1": control_h,
            "student_outcomes_hash_v1": st_h,
            "student_lane_status_v1": "completed",
            "student_replay_outcomes_v1": st_json,
            "student_replay_summary_v1": summ,
            "student_replay_binary_scorecard_v1": bcard,
            "student_replay_validation_checksum_v1": st_out.get("validation_checksum"),
            "student_referee_session_v1": st_session,
            "student_baseline_outcomes_differ_v1": st_h != control_h,
            "student_controlled_referee_win_pct_v1": (float(bcard.get("win_rate") or 0.0) * 100.0)
            if isinstance(bcard, dict) and trades
            else None,
            "student_controlled_expectancy_per_trade_v1": round(ex, 6),
            "student_controlled_total_trades_v1": trades,
            "student_controlled_outcomes_hash_v1": st_h,
            "student_controlled_execution_authority_v1": lane_auth,
            "student_controlled_execution_lane_v1": EXECUTION_LANE_STUDENT_CONTROLLED_V1,
            "student_baseline_e_expectancy_v1": base_ex,
            "student_thesis_e_expectancy_v1": ex,
            "student_vs_baseline_expectancy_delta_v1": round(ex - base_ex, 6),
        }
    )
    if isinstance(sfc_audit, dict):
        base_out["student_full_control_replay_audit_v1"] = sfc_audit
    if j_id:
        _emit_student_lane_complete_v1(
            job_id=j_id,
            fingerprint=fingerprint,
            scenario_id=sid,
            summary="Student-controlled replay completed.",
            student_outcomes_hash=st_h,
            execution_authority_v1=lane_auth,
        )
        _emit_referee_used_student_thesis_v1(
            job_id=j_id,
            fingerprint=fingerprint,
            scenario_id=sid,
            execution_authority_v1=lane_auth,
        )
    return base_out


def apply_automated_student_lanes_from_exam_contract_v1(
    *,
    results: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    seam_audit: dict[str, Any] | None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    After ``student_loop_seam_after_parallel_batch_v1`` sealed ``student_output_v1`` per scenario, build
    ``student_execution_intent_v1`` and run the Student lane **without** operator-authored scenario JSON.

    Respects ``student_execution_mode_v1`` — **baseline_gated** (024C) or **student_full_control** (024D).
    """
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        STUDENT_EXECUTION_MODE_BASELINE_GATED_V1,
        STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1,
        normalize_student_reasoning_mode_v1,
        resolved_llm_for_exam_contract_v1,
    )
    from renaissance_v4.game_theory.student_proctor.student_execution_intent_v1 import (
        build_student_execution_intent_from_sealed_output_v1,
    )

    ex = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    seam = seam_audit if isinstance(seam_audit, dict) else None
    audit: dict[str, Any] = {
        "schema": "automated_student_lane_batch_audit_v1",
        "automation_ran_v1": False,
        "scenarios_with_student_lane_attempted_v1": 0,
        "scenarios_with_student_lane_completed_v1": 0,
        "errors_v1": [],
    }
    if not ex or not ex.get("student_controlled_execution_v1"):
        audit["skip_reason_v1"] = "student_controlled_execution_v1_false_or_absent"
        return audit
    sem = str(ex.get("student_execution_mode_v1") or "")
    if sem not in (
        STUDENT_EXECUTION_MODE_BASELINE_GATED_V1,
        STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1,
    ):
        audit["skip_reason_v1"] = "student_execution_mode_v1_not_baseline_gated_or_student_full_control"
        return audit
    prof = normalize_student_reasoning_mode_v1(
        str(ex.get("student_brain_profile_v1") or ex.get("student_reasoning_mode") or "")
    )
    if prof not in (
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    ):
        audit["skip_reason_v1"] = "profile_not_memory_context_student_or_llm"
        return audit
    sealed = (seam or {}).get("student_output_sealed_by_scenario_id_v1")
    if not isinstance(sealed, dict) or not sealed:
        audit["skip_reason_v1"] = "no_student_output_sealed_by_scenario"
        return audit

    fp = (fingerprint or "").strip()
    if not fp:
        audit["errors_v1"] = ["fingerprint_empty_automation_skipped"]
        return audit
    j = (job_id or "").strip()
    if not j:
        audit["errors_v1"] = ["job_id_empty_automation_skipped"]
        return audit

    llm_model: str | None = None
    if prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        llm_model, _, _, _ = resolved_llm_for_exam_contract_v1(ex)

    rows_by_sid: dict[str, dict[str, Any]] = {}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        sik = str(r.get("scenario_id") or "")
        if sik:
            rows_by_sid[sik] = r
    sc_by_sid: dict[str, dict[str, Any]] = {}
    for s in scenarios or []:
        if not isinstance(s, dict):
            continue
        s_id = str(s.get("scenario_id") or "")
        if s_id:
            sc_by_sid[s_id] = s

    audit["automation_ran_v1"] = True
    attempted = 0
    completed = 0
    errs: list[str] = []
    for sid, so in sealed.items():
        if not isinstance(so, dict):
            continue
        s_id = str(sid)
        row = rows_by_sid.get(s_id)
        if not row or not row.get("ok"):
            continue
        scen = sc_by_sid.get(s_id, {})
        if scen.get("enable_student_controlled_replay_v1"):
            br = row.get("student_controlled_replay_v1")
            if isinstance(br, dict) and str(br.get("student_lane_status_v1") or "") == "completed":
                continue
        intent, build_errs = build_student_execution_intent_from_sealed_output_v1(
            student_output_v1=so,
            job_id=j,
            fingerprint=fp,
            student_brain_profile_v1=prof,
            scenario_id=s_id,
            trade_id=None,
            llm_model=llm_model,
            created_at_utc=None,
        )
        if not intent or build_errs:
            errs.append(
                f"{s_id}: intent_build_failed: {'; '.join(build_errs or ['unknown'])}"
            )
            continue
        attempted += 1
        scen_aug = dict(scen)
        scen_aug["student_execution_intent_v1"] = intent
        is_fc = sem == STUDENT_EXECUTION_MODE_STUDENT_FULL_CONTROL_V1
        if is_fc:
            scen_aug["student_full_control_lane_v1"] = True
        out = attach_student_controlled_replay_v1(scen_aug, row, job_id=j, fingerprint=fp)
        out["automation_source_v1"] = "exam_contract_v1"
        out["execution_authority_v1"] = (
            EXECUTION_AUTHORITY_STUDENT_FULL_CONTROL_V1 if is_fc else EXECUTION_AUTHORITY_BASELINE_GATED_STUDENT_V1
        )
        row["student_controlled_replay_v1"] = out
        if str(out.get("student_lane_status_v1") or "") == "completed":
            completed += 1
    audit["scenarios_with_student_lane_attempted_v1"] = attempted
    audit["scenarios_with_student_lane_completed_v1"] = completed
    audit["errors_v1"] = errs
    return audit


def apply_student_controlled_scorecard_rollup_v1(
    results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """
    Aggregate Student-lane session metrics for ``pattern_game_batch_scorecard_v1`` (additive fields).
    """
    if not results:
        return {
            "student_controlled_replay_ran_v1": 0,
            "student_controlled_referee_win_pct_v1": None,
            "student_controlled_expectancy_mean_v1": None,
            "student_controlled_total_trades_sum_v1": 0,
        }
    wins = 0
    losses = 0
    exps: list[float] = []
    trades_sum = 0
    ran = 0
    for r in results:
        if not r.get("ok"):
            continue
        blk = r.get("student_controlled_replay_v1")
        if not isinstance(blk, dict):
            continue
        if str(blk.get("student_lane_status_v1") or "") != "completed":
            continue
        ran += 1
        rs = str(blk.get("student_referee_session_v1") or "")
        if rs == "WIN":
            wins += 1
        elif rs == "LOSS":
            losses += 1
        e = blk.get("student_controlled_expectancy_per_trade_v1")
        if e is not None:
            try:
                exps.append(float(e))
            except (TypeError, ValueError):
                pass
        try:
            trades_sum += int(blk.get("student_controlled_total_trades_v1") or 0)
        except (TypeError, ValueError):
            pass
    judged = wins + losses
    ref_pct = round(100.0 * wins / judged, 1) if judged else None
    ex_mean = round(sum(exps) / len(exps), 6) if exps else None
    return {
        "student_controlled_replay_ran_v1": ran,
        "student_controlled_referee_win_pct_v1": ref_pct,
        "student_controlled_expectancy_mean_v1": ex_mean,
        "student_controlled_total_trades_sum_v1": trades_sum,
    }
