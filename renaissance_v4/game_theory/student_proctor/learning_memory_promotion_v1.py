"""
GT_DIRECTIVE_018 — **Memory promotion**: promote / hold / reject using L3 truth, scorecard economics,
and thesis/process signals. Governs **append** eligibility and **retrieval** eligibility.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_panel_d13 import _ordered_parallel_rows
from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    build_student_panel_l3_payload_v1,
)

SCHEMA_LEARNING_GOVERNANCE_V1 = "learning_governance_v1"

GOVERNANCE_PROMOTE = "promote"
GOVERNANCE_HOLD = "hold"
GOVERNANCE_REJECT = "reject"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def promotion_expectancy_min_v1() -> float:
    """Trades with ``expectancy_per_trade`` above this are **not** held for weak E (strict >)."""
    return _float_env("PATTERN_GAME_STUDENT_PROMOTION_E_MIN", 0.0)


def promotion_process_score_min_v1() -> float:
    """When ``student_l1_process_score_v1`` is present on the scorecard, promote requires ``P >=`` this."""
    return _float_env("PATTERN_GAME_STUDENT_PROMOTION_P_MIN", 0.5)


def promotion_min_scenarios_v1() -> int:
    """Runs with ``total_processed`` below this are **held** for insufficient sample (when field present)."""
    return max(1, _int_env("PATTERN_GAME_STUDENT_PROMOTION_MIN_SCENARIOS", 1))


def fingerprint_from_scorecard_entry_v1(entry: dict[str, Any] | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    mci = entry.get("memory_context_impact_audit_v1")
    if isinstance(mci, dict):
        fp = str(mci.get("run_config_fingerprint_sha256_40") or "").strip()
        return fp or None
    return None


def memory_retrieval_eligible_v1(record: dict[str, Any]) -> bool:
    """
    **Retrieval governance:** only **promote** (or legacy rows without governance) participate
    in default cross-run retrieval.
    """
    if not isinstance(record, dict):
        return False
    lg = record.get("learning_governance_v1")
    if not isinstance(lg, dict):
        return True
    d = str(lg.get("decision") or "").strip().lower()
    if d == GOVERNANCE_REJECT:
        return False
    if d == GOVERNANCE_HOLD:
        return False
    if d == GOVERNANCE_PROMOTE:
        return True
    return True


def build_learning_governance_v1(
    *,
    decision: str,
    reason_codes: list[str],
    source_job_id: str,
    fingerprint: str | None,
    timestamp_utc: str | None = None,
    retrieval_weight_v1: float | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema": SCHEMA_LEARNING_GOVERNANCE_V1,
        "decision": decision,
        "reason_codes": list(reason_codes),
        "source_job_id": str(source_job_id).strip(),
        "fingerprint": fingerprint,
        "timestamp_utc": timestamp_utc or _utc_iso(),
    }
    if retrieval_weight_v1 is not None:
        out["retrieval_weight_v1"] = float(retrieval_weight_v1)
    return out


def classify_trade_memory_promotion_v1(
    *,
    l3_payload: dict[str, Any],
    scorecard_entry: dict[str, Any] | None,
) -> tuple[str, list[str], dict[str, Any]]:
    """
    Classify one **trade** (``l3_payload`` for ``job_id`` + ``trade_id``).

    Returns ``(decision, reason_codes, learning_governance_v1)``.
    """
    entry = scorecard_entry if isinstance(scorecard_entry, dict) else {}
    job_id = str(l3_payload.get("job_id") or entry.get("job_id") or "").strip()
    fp = fingerprint_from_scorecard_entry_v1(entry)
    ts = _utc_iso()

    reject_codes: list[str] = []
    gaps = l3_payload.get("data_gaps") if isinstance(l3_payload.get("data_gaps"), list) else []
    rec = l3_payload.get("decision_record_v1")

    if l3_payload.get("ok") is False:
        reject_codes.append("reject_l3_payload_not_ok_v1")
    if isinstance(rec, dict) and rec.get("ok") is False:
        reject_codes.append("reject_decision_record_incomplete_v1")

    for g in gaps:
        if not isinstance(g, dict):
            continue
        sev = str(g.get("severity") or "").lower()
        reason = str(g.get("reason") or "")
        if sev == SEVERITY_CRITICAL:
            reject_codes.append("reject_l3_critical_gap_v1")
        if reason == "llm_student_output_rejected_pre_seal_v1":
            reject_codes.append("reject_l3_llm_pre_seal_v1")
        if reason in (
            "student_directional_thesis_store_missing_for_llm_profile_v1",
            "student_directional_thesis_incomplete_for_llm_profile_v1",
        ):
            reject_codes.append("reject_l3_llm_thesis_gap_v1")
        if reason == "missing_downstream_frames_enter_parallel_v1":
            reject_codes.append("reject_l3_downstream_incomplete_v1")
        if reason == "batch_parallel_results_v1_missing":
            reject_codes.append("reject_l3_batch_incomplete_v1")

    if reject_codes:
        codes = sorted(set(reject_codes))
        return GOVERNANCE_REJECT, codes, build_learning_governance_v1(
            decision=GOVERNANCE_REJECT,
            reason_codes=codes,
            source_job_id=job_id,
            fingerprint=fp,
            timestamp_utc=ts,
            retrieval_weight_v1=0.0,
        )

    hold_codes: list[str] = []

    exp = entry.get("expectancy_per_trade")
    exp_f: float | None
    try:
        exp_f = float(exp) if exp is not None else None
    except (TypeError, ValueError):
        exp_f = None
    e_min = promotion_expectancy_min_v1()
    if exp_f is None:
        hold_codes.append("hold_expectancy_unavailable_v1")
    elif exp_f <= e_min:
        hold_codes.append("hold_weak_expectancy_v1")

    tp = entry.get("total_processed")
    try:
        tp_n = int(tp) if tp is not None else None
    except (TypeError, ValueError):
        tp_n = None
    min_s = promotion_min_scenarios_v1()
    if tp_n is not None and tp_n < min_s:
        hold_codes.append("hold_insufficient_sample_v1")

    p_score = entry.get("student_l1_process_score_v1")
    if p_score is not None:
        try:
            p_val = float(p_score)
        except (TypeError, ValueError):
            p_val = None
        if p_val is not None and p_val < promotion_process_score_min_v1():
            hold_codes.append("hold_process_score_below_threshold_v1")

    for g in gaps:
        if isinstance(g, dict) and str(g.get("severity") or "").lower() == SEVERITY_WARNING:
            hold_codes.append("hold_l3_warning_gap_v1")
            break

    if hold_codes:
        codes = sorted(set(hold_codes))
        return GOVERNANCE_HOLD, codes, build_learning_governance_v1(
            decision=GOVERNANCE_HOLD,
            reason_codes=codes,
            source_job_id=job_id,
            fingerprint=fp,
            timestamp_utc=ts,
            retrieval_weight_v1=0.35,
        )

    promo_codes = ["promote_clean_l3_positive_economics_v1"]
    return GOVERNANCE_PROMOTE, promo_codes, build_learning_governance_v1(
        decision=GOVERNANCE_PROMOTE,
        reason_codes=promo_codes,
        source_job_id=job_id,
        fingerprint=fp,
        timestamp_utc=ts,
        retrieval_weight_v1=1.0,
    )


def aggregate_run_memory_decision_v1(decisions: list[str]) -> str:
    """Worst wins: reject > hold > promote."""
    s = {str(d).strip().lower() for d in decisions if str(d).strip()}
    if not s:
        return GOVERNANCE_HOLD
    if GOVERNANCE_REJECT in s:
        return GOVERNANCE_REJECT
    if GOVERNANCE_HOLD in s:
        return GOVERNANCE_HOLD
    return GOVERNANCE_PROMOTE


def build_memory_promotion_context_v1(
    *,
    scorecard_entry: dict[str, Any] | None,
    student_output: dict[str, Any] | None,
    trade_id: str,
) -> dict[str, Any]:
    """Optional denormalized blob stored on promoted/hold rows for audit."""
    entry = scorecard_entry if isinstance(scorecard_entry, dict) else {}
    so = student_output if isinstance(student_output, dict) else {}
    llm_model = None
    llm = entry.get("student_llm_v1")
    if isinstance(llm, dict):
        llm_model = str(llm.get("llm_model") or "").strip() or None
    thesis_keys = (
        "confidence_band",
        "student_action_v1",
        "supporting_indicators",
        "conflicting_indicators",
        "context_fit",
        "invalidation_text",
        "reasoning_text",
    )
    present = [k for k in thesis_keys if k in so and so.get(k) is not None]
    return {
        "schema": "memory_promotion_context_v1",
        "trade_id": str(trade_id).strip(),
        "student_brain_profile_v1": str(
            entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or ""
        ).strip()
        or None,
        "llm_model": llm_model,
        "thesis_fields_present_v1": present,
        "expectancy_per_trade": entry.get("expectancy_per_trade"),
        "student_l1_process_score_v1": entry.get("student_l1_process_score_v1"),
    }


def trade_ids_for_job_from_batch_v1(job_id: str) -> list[str]:
    """Closed-trade ids from ``batch_parallel_results_v1`` when present."""
    jid = job_id.strip()
    if not jid:
        return []
    entry = find_scorecard_entry_by_job_id(jid)
    if not isinstance(entry, dict):
        return []
    batch_dir_s = entry.get("session_log_batch_dir")
    batch_dir, _sc, _err = build_scenario_list_for_batch(jid, batch_dir_s if isinstance(batch_dir_s, str) else None)
    if not batch_dir or not batch_dir.is_dir():
        return []
    payload = load_batch_parallel_results_v1(batch_dir)
    if not payload:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in _ordered_parallel_rows(payload):
        if not row.get("ok"):
            continue
        for oj in row.get("replay_outcomes_json") or []:
            if not isinstance(oj, dict):
                continue
            tid = str(oj.get("trade_id") or "").strip()
            if tid and tid not in seen:
                seen.add(tid)
                out.append(tid)
    return out


def build_student_panel_run_learning_payload_v1(job_id: str) -> dict[str, Any]:
    """
    Operator payload for ``GET /api/student-panel/run/<job_id>/learning`` (GT_DIRECTIVE_018).
    """
    from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
        list_student_learning_records_by_run_id,
    )

    jid = job_id.strip()
    if not jid:
        return {
            "schema": "student_panel_run_learning_payload_v1",
            "ok": False,
            "error": "job_id required",
            "job_id": "",
            "learning_governance_v1": build_learning_governance_v1(
                decision=GOVERNANCE_REJECT,
                reason_codes=["reject_missing_job_id_v1"],
                source_job_id="",
                fingerprint=None,
            ),
            "run_was_stored": False,
            "eligible_for_retrieval": False,
            "per_trade": [],
        }

    entry = find_scorecard_entry_by_job_id(jid)
    tids = trade_ids_for_job_from_batch_v1(jid)
    per_trade: list[dict[str, Any]] = []
    decisions: list[str] = []
    all_codes: list[str] = []

    for tid in tids:
        l3 = build_student_panel_l3_payload_v1(jid, tid)
        dec, codes, gov = classify_trade_memory_promotion_v1(l3_payload=l3, scorecard_entry=entry)
        decisions.append(dec)
        all_codes.extend(codes)
        per_trade.append({"trade_id": tid, "learning_governance_v1": gov})

    agg = aggregate_run_memory_decision_v1(decisions)
    fp = fingerprint_from_scorecard_entry_v1(entry)
    run_gov = build_learning_governance_v1(
        decision=agg,
        reason_codes=sorted(set(all_codes))[:48],
        source_job_id=jid,
        fingerprint=fp,
    )

    store_path = None
    try:
        from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
            default_student_learning_store_path_v1,
        )

        store_path = default_student_learning_store_path_v1()
        stored = list_student_learning_records_by_run_id(store_path, jid)
    except OSError:
        stored = []

    run_was_stored = bool(stored)
    eligible = any(memory_retrieval_eligible_v1(r) for r in stored)

    return {
        "schema": "student_panel_run_learning_payload_v1",
        "ok": True,
        "job_id": jid,
        "learning_governance_v1": run_gov,
        "run_was_stored": run_was_stored,
        "eligible_for_retrieval": eligible,
        "per_trade": per_trade,
        "stored_record_count_v1": len(stored),
    }


__all__ = [
    "GOVERNANCE_HOLD",
    "GOVERNANCE_PROMOTE",
    "GOVERNANCE_REJECT",
    "SCHEMA_LEARNING_GOVERNANCE_V1",
    "aggregate_run_memory_decision_v1",
    "build_learning_governance_v1",
    "build_memory_promotion_context_v1",
    "build_student_panel_run_learning_payload_v1",
    "classify_trade_memory_promotion_v1",
    "fingerprint_from_scorecard_entry_v1",
    "memory_retrieval_eligible_v1",
    "promotion_expectancy_min_v1",
    "promotion_min_scenarios_v1",
    "promotion_process_score_min_v1",
    "trade_ids_for_job_from_batch_v1",
]
