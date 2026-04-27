"""
Directive 09 — Operator **execution seam**: after a parallel batch, run Student packet → shadow output
→ reveal → append ``student_learning_record_v1`` for each closed trade.

* Does not import replay_runner.
* Soft-fail: per-trade errors are collected; batch Referee results remain authoritative.
* Disable with env ``PATTERN_GAME_STUDENT_LOOP_SEAM=0`` (operations kill-switch; no UI toggle required).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_from_jsonable
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import (
    build_reveal_v1_from_outcome_and_student,
)
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
    resolved_llm_for_exam_contract_v1,
    STUDENT_LLM_APPROVED_MODEL_V1,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import (
    emit_shadow_stub_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    _student_llm_max_trades_v1,
    emit_student_output_via_ollama_v1,
    verify_ollama_model_tag_available_v1,
)
from renaissance_v4.game_theory.candle_timeframe_runtime import (
    effective_replay_timeframe_from_worker_replay_row_v1,
    is_allowed_candle_timeframe_minutes_v1,
)
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_panel_l3_datagap_matrix_v1 import build_student_panel_l3_payload_v1
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_REJECT,
    build_memory_promotion_context_v1,
    classify_trade_memory_promotion_v1,
)
from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
    emit_candle_timeframe_nexus_v1,
    emit_governance_decided_v1,
    emit_learning_record_appended_v1,
    emit_llm_called_v1,
    emit_llm_output_received_v1,
    emit_llm_output_rejected_v1,
    emit_memory_retrieval_completed_v1,
    emit_referee_used_student_output_batch_truth_v1,
    emit_student_output_sealed_v1,
    emit_student_reasoning_fault_map_v1,
    emit_timeframe_mismatch_detected_v1,
    fingerprint_for_parallel_job_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_loop_governance_v1 import (
    learning_loop_governance_audit_v1,
    resolved_max_retrieval_slices_v1,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
    FIELD_STUDENT_CONTEXT_ANNEX_V1,
    validate_student_learning_record_v1,
)
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import (
    apply_engine_authority_to_student_output_v1,
    run_entry_reasoning_pipeline_v1,
)
from renaissance_v4.game_theory.unified_agent_v1.external_api_l1_v1 import l1_fields_from_router_decision_v1
from renaissance_v4.game_theory.student_proctor.student_execution_intent_v1 import (
    build_student_execution_intent_from_sealed_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    merge_runtime_fault_nodes_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
    default_student_learning_store_path_v1,
)
from renaissance_v4.utils.db import DB_PATH

_NS_RECORD = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

SCHEMA_PHASED_HONESTY_ANNOTATION_V1 = "phased_honesty_annotation_v1"
SCHEMA_WIRING_HONESTY_ANNOTATION_V1 = "wiring_honesty_annotation_v1"
SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1 = "memory_semantics_annotation_v1"
SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1 = "deliverable_vocabulary_annotation_v1"


def _deliverable_vocabulary_annotation_v1(*, seam_attempted: bool) -> dict[str, Any]:
    """
    Directive **D9** — **trade** and **learned behavior** align with **§0.2** / **§0.3**.

    Referee execution / PnL alone are not the Student **trade** definition; raw metrics without a
    baseline are not **learned behavior** by themselves.
    """
    if not seam_attempted:
        return {
            "schema": SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1,
            "directive": "D9",
            "trade_is_contract_student_output_pre_reveal_v1": None,
            "referee_fill_not_trade_definition_v1": None,
            "learned_behavior_requires_baseline_v1": None,
            "authoritative_doc_anchor_v1": None,
            "note": "Student loop seam not executed — D9 vocabulary annotation N/A.",
        }
    return {
        "schema": SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1,
        "directive": "D9",
        "trade_is_contract_student_output_pre_reveal_v1": True,
        "referee_fill_not_trade_definition_v1": True,
        "learned_behavior_requires_baseline_v1": True,
        "authoritative_doc_anchor_v1": "ARCHITECTURE_BACKWARD_LADDER_STUDENT_TABLE.md §0.2 §0.3",
        "note": (
            "Per §0.2, the tradable deliverable is contract-valid student_output_v1 from legal pre-reveal "
            "context — not Referee fills alone. Per §0.3, learned behavior requires a pre-registered "
            "positive vs a declared baseline — not a lone metric."
        ),
    }


def _memory_semantics_annotation_v1(*, seam_attempted: bool) -> dict[str, Any]:
    """
    Directive **D8** — Student store retrieval is **exact-key**, not approximate pattern matching.

    Do not market “the same pattern came back” from Student memory; v1 matches
    ``student_entry_v1:{symbol}:{entry_time}`` on the learning store only (see **§C.2**).
    """
    if not seam_attempted:
        return {
            "schema": SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1,
            "directive": "D8",
            "student_retrieval_match_mode_v1": None,
            "same_chart_pattern_repeat_claim_supported_v1": None,
            "approximate_similarity_matching_student_store_v1": None,
            "retrieval_signature_key_format_v1": None,
            "note": "Student loop seam not executed — memory semantics annotation N/A.",
        }
    return {
        "schema": SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1,
        "directive": "D8",
        "student_retrieval_match_mode_v1": "exact_signature_key",
        "same_chart_pattern_repeat_claim_supported_v1": False,
        "approximate_similarity_matching_student_store_v1": False,
        "retrieval_signature_key_format_v1": "student_entry_v1:{symbol}:{entry_time}:{timeframe_minutes}",
        "note": (
            "Learning rows match by exact context_signature_v1.signature_key (including candle timeframe "
            "suffix) — not feature-space similarity. Do not claim ‘the same pattern again’ from Student v1 "
            "retrieval; see ARCHITECTURE §C.2. Engine context_signature_memory is a separate approximate path."
        ),
    }


def _wiring_honesty_annotation_v1(
    *,
    seam_attempted: bool,
    trades_seen: int,
    first_packet_annex_present: bool | None,
    retrieval_matches_total: int,
) -> dict[str, Any]:
    """
    Directive **D7** — do not claim “full trading context” on the Student path until attached + tested.

    The default operator seam builds packets via **cross-run retrieval** only; rich **TRADING_CONTEXT**
    buckets require an explicit, validated ``student_context_annex_v1`` (and tests), not marketing copy.
    """
    if not seam_attempted:
        return {
            "schema": SCHEMA_WIRING_HONESTY_ANNOTATION_V1,
            "directive": "D7",
            "as_built_student_pre_reveal_wiring_v1": None,
            "student_context_annex_v1_present_on_first_packet": None,
            "retrieved_student_experience_non_empty": None,
            "full_structured_trading_context_baseline_claim_supported_v1": None,
            "note": "Student loop seam not executed — wiring annotation N/A.",
        }
    rex_nonempty = int(retrieval_matches_total) > 0
    ab = (
        "causal OHLCV bars through decision time; optional retrieved_student_experience_v1; "
        "optional versioned student_context_annex_v1 for price/structure/indicator/time buckets."
    )
    return {
        "schema": SCHEMA_WIRING_HONESTY_ANNOTATION_V1,
        "directive": "D7",
        "as_built_student_pre_reveal_wiring_v1": ab,
        "student_context_annex_v1_present_on_first_packet": first_packet_annex_present,
        "retrieved_student_experience_non_empty": rex_nonempty if trades_seen > 0 else None,
        # False until annex buckets are product-filled **and** release/tests claim support (D7 gate).
        "full_structured_trading_context_baseline_claim_supported_v1": False,
        "note": (
            "Default seam uses bars + retrieval only; do not market ‘full indicator/regime context’ on the "
            "Student path without a validated student_context_annex_v1 (see TRADING_CONTEXT_REFERENCE_V1, §C.1)."
            if trades_seen > 0
            else "No trades processed — wiring flags partially N/A."
        ),
    }


def _phased_honesty_annotation_v1(
    *,
    seam_attempted: bool,
    student_emit_occurred: bool,
    trades_seen: int = 0,
) -> dict[str, Any]:
    """
    Directive **D6** — process-order honesty for telemetry / API consumers.

    The parallel batch supplies ``replay_outcomes_json`` **before** the Student seam runs; therefore
    **strict** “exam blind” ordering (Student commits with **no** ``OutcomeRecord`` in the pipeline)
    is **not** satisfied when this seam executes — even though the **pre-reveal packet** remains
    causal (bars through entry only).
    """
    if not seam_attempted:
        return {
            "schema": SCHEMA_PHASED_HONESTY_ANNOTATION_V1,
            "directive": "D6",
            "strict_exam_blind_process_order": None,
            "replay_outcomes_supplied_before_shadow_emit": None,
            "pre_reveal_student_inputs_are_causal_only": None,
            "student_shadow_emit_occurred": None,
            "note": "Student loop seam not executed (disabled).",
        }
    outcomes_before_emit = trades_seen > 0
    return {
        "schema": SCHEMA_PHASED_HONESTY_ANNOTATION_V1,
        "directive": "D6",
        "strict_exam_blind_process_order": False if outcomes_before_emit else None,
        "replay_outcomes_supplied_before_shadow_emit": True if outcomes_before_emit else None,
        "pre_reveal_student_inputs_are_causal_only": True if outcomes_before_emit else None,
        "student_shadow_emit_occurred": bool(student_emit_occurred),
        "trades_seen_by_seam": int(trades_seen),
        "note": (
            "When trades are processed, replay outcomes are read from batch results before shadow_student_v1 emit; "
            "decision packet still uses causal bars at entry_time only (no current-trade outcome in packet). "
            "Do not claim strict exam-blind process order for this pipeline until job order changes."
            if outcomes_before_emit
            else "No trades processed by seam in this invocation — phased-honesty flags N/A beyond causal-packet design."
        ),
    }


def _env_seam_enabled() -> bool:
    v = (os.environ.get("PATTERN_GAME_STUDENT_LOOP_SEAM") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _env_unified_agent_reasoning_router_v1() -> bool:
    """GT_DIRECTIVE_026AI — optional OpenAI review path (default off; local reasoning always runs)."""
    v = (os.environ.get("PATTERN_GAME_UNIFIED_AGENT_REASONING_ROUTER") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _signature_key_for_trade_v1(o: OutcomeRecord, *, candle_timeframe_minutes: int) -> str:
    """v1 **exact** lookup key for the learning store (`context_signature_v1.signature_key`) — includes TF."""
    return f"student_entry_v1:{o.symbol}:{o.entry_time}:{int(candle_timeframe_minutes)}"


def _record_id_for_trade(*, run_id: str, scenario_id: str, trade_id: str) -> str:
    return str(uuid.uuid5(_NS_RECORD, f"{run_id}:{scenario_id}:{trade_id}"))


def _student_output_fingerprint_v1(so: dict[str, Any]) -> str:
    canonical = json.dumps(so, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _merge_exam_lifecycle_026b_into_packet_v1(
    pkt: dict[str, Any], ex_req: dict[str, Any] | None
) -> dict[str, Any]:
    """GT_DIRECTIVE_026B — copy optional lifecycle tape fields from exam contract onto the student packet."""
    if not isinstance(pkt, dict) or not isinstance(ex_req, dict):
        return pkt
    keys = (
        "bars_trade_lifecycle_inclusive_v1",
        "entry_bar_index_for_lifecycle_v1",
        "unified_agent_router_lifecycle_v1",
        "max_hold_bars_lifecycle_v1",
    )
    for k in keys:
        if ex_req.get(k) is None:
            continue
        v = ex_req[k]
        pkt[k] = copy.deepcopy(v) if k == "bars_trade_lifecycle_inclusive_v1" else v
    return pkt


def student_loop_seam_after_parallel_batch_v1(
    *,
    results: list[dict[str, Any]],
    run_id: str,
    db_path: Path | str | None = None,
    store_path: Path | str | None = None,
    strategy_id: str | None = None,
    exam_run_contract_request_v1: dict[str, Any] | None = None,
    operator_batch_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    For each successful scenario row with ``replay_outcomes_json``, process each trade.

    Returns an audit dict suitable for merging into API ``result`` payloads (Directive 11 fields).
    """
    if not _env_seam_enabled():
        return {
            "schema": "student_loop_seam_audit_v1",
            "skipped": True,
            "reason": "PATTERN_GAME_STUDENT_LOOP_SEAM disabled",
            "student_learning_rows_appended": 0,
            "student_retrieval_matches": 0,
            "student_output_fingerprint": None,
            "shadow_student_enabled": False,
            "phased_honesty_annotation_v1": _phased_honesty_annotation_v1(
                seam_attempted=False, student_emit_occurred=False
            ),
            "wiring_honesty_annotation_v1": _wiring_honesty_annotation_v1(
                seam_attempted=False,
                trades_seen=0,
                first_packet_annex_present=None,
                retrieval_matches_total=0,
            ),
            "memory_semantics_annotation_v1": _memory_semantics_annotation_v1(seam_attempted=False),
            "deliverable_vocabulary_annotation_v1": _deliverable_vocabulary_annotation_v1(
                seam_attempted=False
            ),
            "llm_student_output_rejections_v1": 0,
        }

    ex_req_skip = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    _prof_skip = normalize_student_reasoning_mode_v1(
        str((ex_req_skip or {}).get("student_brain_profile_v1") or (ex_req_skip or {}).get("student_reasoning_mode") or "")
    )
    if _prof_skip == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
        return {
            "schema": "student_loop_seam_audit_v1",
            "skipped": True,
            "reason": "operator_run_mode_baseline_no_student_seam",
            "baseline_control_operator_mode_v1": True,
            "student_learning_rows_appended": 0,
            "student_retrieval_matches": 0,
            "student_output_fingerprint": None,
            "shadow_student_enabled": False,
            "phased_honesty_annotation_v1": _phased_honesty_annotation_v1(
                seam_attempted=False, student_emit_occurred=False
            ),
            "wiring_honesty_annotation_v1": _wiring_honesty_annotation_v1(
                seam_attempted=False,
                trades_seen=0,
                first_packet_annex_present=None,
                retrieval_matches_total=0,
            ),
            "memory_semantics_annotation_v1": _memory_semantics_annotation_v1(seam_attempted=False),
            "deliverable_vocabulary_annotation_v1": _deliverable_vocabulary_annotation_v1(
                seam_attempted=False
            ),
            "llm_student_output_rejections_v1": 0,
        }

    db = Path(str(db_path)) if db_path else DB_PATH
    store = Path(str(store_path)) if store_path else default_student_learning_store_path_v1()
    scorecard_entry_effective = find_scorecard_entry_by_job_id(str(run_id).strip())

    errors: list[str] = []
    appended = 0
    memory_promotion_batch_trades_v1: list[dict[str, Any]] = []
    trades_seen = 0
    retrieval_matches_total = 0
    primary_trade_shadow_student_v1: dict[str, Any] | None = None
    primary_student_output_v1: dict[str, Any] | None = None
    student_output_sealed_by_scenario_id_v1: dict[str, Any] = {}
    first_packet_annex_present: bool | None = None

    ex_req = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    oba = operator_batch_audit if isinstance(operator_batch_audit, dict) else {}

    def _resolved_candle_timeframe_minutes_v1() -> int:
        for cand in ((ex_req or {}).get("candle_timeframe_minutes"), oba.get("candle_timeframe_minutes")):
            if cand is not None:
                try:
                    t = int(cand)
                    if is_allowed_candle_timeframe_minutes_v1(t):
                        return t
                except (TypeError, ValueError):
                    pass
        return 5

    c_tf = _resolved_candle_timeframe_minutes_v1()
    exm = (ex_req or {}).get("candle_timeframe_minutes")
    obm = oba.get("candle_timeframe_minutes")
    if exm is not None and obm is not None and int(exm) != int(obm):
        emit_timeframe_mismatch_detected_v1(
            job_id=str(run_id).strip(),
            fingerprint=None,
            left_role="exam_run_contract",
            left_minutes=int(exm),
            right_role="operator_batch_audit",
            right_minutes=int(obm),
        )

    profile = normalize_student_reasoning_mode_v1(
        str((ex_req or {}).get("student_brain_profile_v1") or (ex_req or {}).get("student_reasoning_mode") or "")
    )
    pv = str((ex_req or {}).get("prompt_version") or "shadow_student_stub_v1").strip()[:256]
    use_llm = profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    llm_cap = _student_llm_max_trades_v1()
    llm_model_resolved: str | None = None
    base_url_resolved: str | None = None
    llm_meta_echo: dict[str, Any] = {}
    llm_resolution_errs: list[str] = []
    requested_model_echo: str | None = None
    if use_llm and ex_req:
        llm_model_resolved, base_url_resolved, llm_meta_echo, llm_resolution_errs = (
            resolved_llm_for_exam_contract_v1(ex_req)
        )
        rslv = (
            (llm_meta_echo.get("student_llm_resolution_v1") or {})
            if isinstance(llm_meta_echo, dict)
            else {}
        )
        if isinstance(rslv, dict):
            rm = rslv.get("requested_model")
            requested_model_echo = str(rm).strip() if isinstance(rm, str) and rm.strip() else None
        if not llm_resolution_errs and llm_model_resolved and base_url_resolved:
            probe_err = verify_ollama_model_tag_available_v1(
                base_url_resolved,
                str(llm_model_resolved),
            )
            if probe_err:
                llm_resolution_errs.append(probe_err)
    batch_student_llm_gate_failed = bool(
        use_llm and (llm_resolution_errs or not llm_model_resolved or not base_url_resolved)
    )
    if batch_student_llm_gate_failed and llm_resolution_errs:
        errors.append("student_llm_gate: " + "; ".join(llm_resolution_errs))
    ollama_attempts = 0
    ollama_ok = 0
    llm_trade_i = 0
    llm_student_output_rejections_v1 = 0
    last_external_api_l1_v1: dict[str, object | None] | None = None
    unified_router = _env_unified_agent_reasoning_router_v1()

    fp_emit = fingerprint_for_parallel_job_v1(
        operator_batch_audit=oba if oba else None,
        fingerprint_preview=None,
        scorecard_line=scorecard_entry_effective if isinstance(scorecard_entry_effective, dict) else None,
    )

    mandate_active_v1 = profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1
    _mandate_pre = []
    if mandate_active_v1:
        from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
            validate_student_decision_authority_mandate_preconditions_v1,
        )

        _mandate_pre = validate_student_decision_authority_mandate_preconditions_v1(
            exam_run_contract_request_v1=ex_req,
            job_id=str(run_id).strip(),
            student_brain_profile_v1=profile,
            student_llm_gate_blocked_batch_v1=bool(use_llm and batch_student_llm_gate_failed),
        )
    if _mandate_pre:
        return {
            "schema": "student_loop_seam_audit_v1",
            "skipped": True,
            "reason": "student_decision_authority_mandate_preconditions_failed_v1",
            "student_decision_authority_mandate_block_v1": True,
            "student_decision_authority_mandate_errors_v1": list(_mandate_pre),
            "student_learning_rows_appended": 0,
            "student_retrieval_matches": 0,
            "student_output_fingerprint": None,
            "shadow_student_enabled": False,
            "phased_honesty_annotation_v1": _phased_honesty_annotation_v1(
                seam_attempted=True, student_emit_occurred=False
            ),
            "wiring_honesty_annotation_v1": _wiring_honesty_annotation_v1(
                seam_attempted=True,
                trades_seen=0,
                first_packet_annex_present=None,
                retrieval_matches_total=0,
            ),
            "memory_semantics_annotation_v1": _memory_semantics_annotation_v1(seam_attempted=True),
            "deliverable_vocabulary_annotation_v1": _deliverable_vocabulary_annotation_v1(
                seam_attempted=True
            ),
            "llm_student_output_rejections_v1": 0,
            "errors": list(_mandate_pre),
        }

    emit_candle_timeframe_nexus_v1(
        job_id=str(run_id).strip(),
        fingerprint=fp_emit,
        nexus="run_contract",
        candle_timeframe_minutes=c_tf,
    )
    _replay_timeframe_traced = False
    for row in results:
        if not row.get("ok"):
            continue
        if not _replay_timeframe_traced:
            w_tf = effective_replay_timeframe_from_worker_replay_row_v1(row)
            emit_candle_timeframe_nexus_v1(
                job_id=str(run_id).strip(),
                fingerprint=fp_emit,
                nexus="replay",
                candle_timeframe_minutes=w_tf,
                scenario_id=str(row.get("scenario_id") or ""),
            )
            if w_tf != c_tf:
                emit_timeframe_mismatch_detected_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    left_role="run_contract",
                    left_minutes=c_tf,
                    right_role="replay_worker_row",
                    right_minutes=w_tf,
                    scenario_id=str(row.get("scenario_id") or ""),
                )
            _replay_timeframe_traced = True
        sid = str(row.get("scenario_id") or "unknown")
        raw_list = row.get("replay_outcomes_json")
        if not isinstance(raw_list, list) or not raw_list:
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                errors.append(f"{sid}: non-dict outcome")
                continue
            try:
                o = outcome_record_from_jsonable(raw)
            except (TypeError, ValueError) as e:
                errors.append(f"{sid}: outcome_from_json {e!r}")
                continue
            trades_seen += 1
            if use_llm and batch_student_llm_gate_failed:
                continue
            sk = _signature_key_for_trade_v1(o, candle_timeframe_minutes=c_tf)
            ctx_sig = {"schema": "context_signature_v1", "signature_key": sk}
            try:
                pkt, perr = build_student_decision_packet_v1_with_cross_run_retrieval(
                    db_path=db,
                    symbol=o.symbol,
                    decision_open_time_ms=int(o.entry_time),
                    candle_timeframe_minutes=c_tf,
                    store_path=store,
                    retrieval_signature_key=sk,
                )
                if perr or pkt is None:
                    errors.append(f"{sid} trade={o.trade_id}: packet {perr!r}")
                    continue
                pkt = _merge_exam_lifecycle_026b_into_packet_v1(pkt, ex_req)
                emit_candle_timeframe_nexus_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    nexus="student_packet",
                    candle_timeframe_minutes=c_tf,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                )
                if int(pkt.get("candle_timeframe_minutes") or 0) != int(c_tf):
                    emit_timeframe_mismatch_detected_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        left_role="run_contract",
                        left_minutes=c_tf,
                        right_role="student_packet",
                        right_minutes=int(pkt.get("candle_timeframe_minutes") or 0),
                        scenario_id=sid,
                    )
                if first_packet_annex_present is None:
                    first_packet_annex_present = isinstance(
                        pkt.get(FIELD_STUDENT_CONTEXT_ANNEX_V1), dict
                    )
                rx = pkt.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
                n_rx = len(rx) if isinstance(rx, list) else 0
                retrieval_matches_total += n_rx
                emit_memory_retrieval_completed_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                    retrieval_matches=n_rx,
                    candle_timeframe_minutes=c_tf,
                    retrieval_signature_key=sk,
                )
                rxx = rx if isinstance(rx, list) else []
                ere, ere_err, _ere_trace, pfm = run_entry_reasoning_pipeline_v1(
                    student_decision_packet=pkt,
                    retrieved_student_experience=rxx,
                    run_candle_timeframe_minutes=int(c_tf),
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    emit_traces=True,
                    unified_agent_router=unified_router,
                )
                if isinstance(ere, dict) and unified_router and ere.get("reasoning_router_decision_v1"):
                    last_external_api_l1_v1 = l1_fields_from_router_decision_v1(
                        ere.get("reasoning_router_decision_v1")
                    )
                brain_prof = str(
                    (ex_req or {}).get("student_brain_profile_v1")
                    or (ex_req or {}).get("student_reasoning_mode")
                    or ""
                ).strip() or str(STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1)
                if ere is None:
                    errors.append(
                        f"{sid} trade={o.trade_id}: entry_reasoning_engine_v1 required: {'; '.join(ere_err)}"
                    )
                    emit_student_reasoning_fault_map_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                        student_reasoning_fault_map_v1=pfm,
                    )
                    continue
                if isinstance(ere, dict) and isinstance(pfm, dict):
                    ere["student_reasoning_fault_map_v1"] = pfm
                # GT_DIRECTIVE_026B — optional full in-trade tape: ``bars_trade_lifecycle_inclusive_v1`` on packet
                if isinstance(ere, dict):
                    _lcy = pkt.get("bars_trade_lifecycle_inclusive_v1")
                    if isinstance(_lcy, list) and len(_lcy) >= 2:
                        _act0 = str((ere.get("decision_synthesis_v1") or {}).get("action") or "")
                        if _act0 in ("enter_long", "enter_short"):
                            _eb = pkt.get("bars_inclusive_up_to_t")
                            _dflt_e = (len(_eb) - 1) if isinstance(_eb, list) and _eb else 0
                            _eidx = int(pkt.get("entry_bar_index_for_lifecycle_v1", _dflt_e) or 0)
                            _eidx = max(0, min(_eidx, len(_lcy) - 1))
                            _side = "long" if _act0 == "enter_long" else "short"
                            _ur = bool(
                                pkt.get("unified_agent_router_lifecycle_v1", unified_router)
                            )
                            from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
                                FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C,
                            )
                            from renaissance_v4.game_theory.student_proctor.lifecycle_reasoning_engine_v1 import (
                                run_lifecycle_tape_v1,
                            )
                            from renaissance_v4.game_theory.unified_agent_v1.reasoning_router_config_v1 import (
                                load_reasoning_router_config_v1,
                            )

                            _raw026 = (pkt or {}).get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C)
                            _l026p: list[dict] | None = None
                            if isinstance(_raw026, list) and _raw026:
                                _l026p = [dict(x) for x in _raw026 if isinstance(x, dict)][:8]
                            _tape = run_lifecycle_tape_v1(
                                all_bars=[dict(b) for b in _lcy if isinstance(b, dict)],
                                entry_bar_index=_eidx,
                                side=_side,
                                entry_reasoning_eval_v1=ere,
                                run_candle_timeframe_minutes=int(c_tf),
                                symbol=str(pkt.get("symbol") or ""),
                                retrieved_student_experience=rxx,
                                max_hold_bars=int(pkt.get("max_hold_bars_lifecycle_v1") or 100),
                                unified_agent_router=_ur,
                                router_config=load_reasoning_router_config_v1(None) if _ur else None,
                                job_id=str(run_id).strip(),
                                fingerprint=fp_emit,
                                emit_lifecycle_traces=True,
                                trade_id=str(o.trade_id),
                                scenario_id=sid,
                                retrieved_lifecycle_deterministic_learning_026c_v1=_l026p,
                            )
                            ere["lifecycle_tape_result_v1"] = _tape
                            if _tape.get("closed_v1"):
                                from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
                                    process_closed_lifecycle_for_deterministic_learning_026c_v1,
                                )

                                _lt_base = _tape.get("final_fault_map_v1")
                                if not isinstance(_lt_base, dict):
                                    _lt_base = pfm
                                _r026 = bool(
                                    isinstance(
                                        (pkt or {}).get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C),
                                        list,
                                    )
                                    and len((pkt or {}).get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C) or []) > 0
                                )
                                _pfm_learn = process_closed_lifecycle_for_deterministic_learning_026c_v1(
                                    tape_result_v1=_tape,
                                    entry_reasoning_eval_v1=ere,
                                    outcome=o,
                                    job_id=str(run_id).strip(),
                                    scenario_id=sid,
                                    trade_id=str(o.trade_id),
                                    candle_timeframe_minutes=int(c_tf),
                                    context_signature_key=sk,
                                    symbol=str((pkt or {}).get("symbol") or o.symbol or ""),
                                    pfm=_lt_base,
                                    entry_bar_index_v1=_eidx,
                                    retrieval_in_path=_r026,
                                    fingerprint=fp_emit,
                                )
                                if _pfm_learn is not None:
                                    pfm = _pfm_learn
                                    ere["student_reasoning_fault_map_v1"] = pfm
                if isinstance(ere, dict):
                    from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
                        run_student_decision_authority_for_trade_v1,
                    )

                    run_student_decision_authority_for_trade_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                        ere=ere,
                        pkt=pkt,
                        unified_router_enabled=unified_router,
                        exam_run_contract_request_v1=ex_req if isinstance(ex_req, dict) else None,
                        mandate_active_v1=mandate_active_v1,
                    )
                allowed_mids = frozenset(
                    str(z.get("record_id") or "").strip()
                    for z in rxx
                    if isinstance(z, dict) and str(z.get("record_id") or "").strip()
                )
                so: dict[str, Any] | None = None
                soe: list[str] = []
                over_cap = False
                use_llm_attempt_v1 = bool(use_llm and llm_model_resolved and base_url_resolved)
                if use_llm and llm_model_resolved and base_url_resolved:
                    over_cap = llm_cap is not None and llm_trade_i >= llm_cap
                    if over_cap:
                        so, soe = emit_shadow_stub_student_output_v1(
                            pkt,
                            graded_unit_id=o.trade_id,
                            decision_at_ms=int(o.entry_time),
                        )
                        errors.append(
                            f"{sid} trade={o.trade_id}: llm_trade_cap_exceeded (cap={llm_cap}) — stub Student used"
                        )
                        emit_llm_output_rejected_v1(
                            job_id=str(run_id).strip(),
                            fingerprint=fp_emit,
                            scenario_id=sid,
                            trade_id=str(o.trade_id),
                            errors=[f"llm_trade_cap_exceeded cap={llm_cap}"],
                        )
                    else:
                        emit_llm_called_v1(
                            job_id=str(run_id).strip(),
                            fingerprint=fp_emit,
                            scenario_id=sid,
                            trade_id=str(o.trade_id),
                            model=llm_model_resolved,
                        )
                        ollama_attempts += 1
                        llm_trade_i += 1
                        so, soe = emit_student_output_via_ollama_v1(
                            pkt,
                            graded_unit_id=o.trade_id,
                            decision_at_ms=int(o.entry_time),
                            llm_model=llm_model_resolved,
                            ollama_base_url=base_url_resolved,
                            prompt_version=pv,
                            require_directional_thesis_v1=True,
                        )
                        if soe or so is None:
                            llm_student_output_rejections_v1 += 1
                            errors.append(
                                f"{sid} trade={o.trade_id}: llm_student_output_rejected: {'; '.join(soe)}"
                            )
                            emit_llm_output_rejected_v1(
                                job_id=str(run_id).strip(),
                                fingerprint=fp_emit,
                                scenario_id=sid,
                                trade_id=str(o.trade_id),
                                errors=list(soe) if isinstance(soe, list) else [str(soe)],
                            )
                            _llm_rej_fm = merge_runtime_fault_nodes_v1(
                                pfm,
                                use_llm_path=True,
                                llm_checked_pass=False,
                                llm_error_codes=[str(x) for x in (soe or [])],
                                llm_operator_message="The model did not return an answer that matched the required shape and field rules. Fix the prompt or the model output, then retry.",
                                student_sealed_pass=False,
                                student_seal_error_codes=[],
                                student_seal_message="The student line was not sealed because the model step failed first.",
                                execution_intent_pass=False,
                                execution_intent_error_codes=[],
                                execution_intent_message="No execution handoff was built because the model step did not return a valid student line.",
                            )
                            emit_student_reasoning_fault_map_v1(
                                job_id=str(run_id).strip(),
                                fingerprint=fp_emit,
                                scenario_id=sid,
                                trade_id=str(o.trade_id),
                                student_reasoning_fault_map_v1=_llm_rej_fm,
                            )
                            # No stub fallback for LLM profile — thesis or explicit failure (precondition for 017).
                            continue
                        ollama_ok += 1
                        emit_llm_output_received_v1(
                            job_id=str(run_id).strip(),
                            fingerprint=fp_emit,
                            scenario_id=sid,
                            trade_id=str(o.trade_id),
                        )
                else:
                    so, soe = emit_shadow_stub_student_output_v1(
                        pkt,
                        graded_unit_id=o.trade_id,
                        decision_at_ms=int(o.entry_time),
                    )
                if soe or so is None:
                    errors.append(f"{sid} trade={o.trade_id}: student_output {'; '.join(soe)}")
                    continue
                so, auth_errs = apply_engine_authority_to_student_output_v1(
                    so,
                    ere,
                    allowed_memory_ids=allowed_mids,
                )
                if so is None or auth_errs:
                    _seal_u = use_llm_attempt_v1 and not over_cap
                    _auth_fm = merge_runtime_fault_nodes_v1(
                        pfm,
                        use_llm_path=_seal_u,
                        llm_checked_pass=_seal_u,
                        llm_error_codes=[],
                        llm_operator_message="",
                        student_sealed_pass=False,
                        student_seal_error_codes=list(auth_errs) if auth_errs else ["null_student_output"],
                        student_seal_message="The model line could not be merged with the engine output. Cited memory, direction, and thesis must line up with the engine.",
                        execution_intent_pass=False,
                        execution_intent_error_codes=[],
                        execution_intent_message="No execution handoff was built because the merge step did not complete.",
                    )
                    emit_student_reasoning_fault_map_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                        student_reasoning_fault_map_v1=_auth_fm,
                    )
                    errors.append(
                        f"{sid} trade={o.trade_id}: entry_reasoning_authority_merge_failed: "
                        f"{'; '.join(auth_errs) if auth_errs else 'null_student_output'}"
                    )
                    continue
                if mandate_active_v1:
                    _bind = ere.get("student_decision_authority_binding_v1") if isinstance(ere, dict) else None
                    if not isinstance(_bind, dict) or not _bind.get("learning_trace_persisted_v1"):
                        errors.append(
                            f"{sid} trade={o.trade_id}: STUDENT_DECISION_AUTHORITY_MANDATE_V1: "
                            "missing student_decision_authority_binding_v1 after authority — bypass blocked"
                        )
                        continue
                if isinstance(so, dict) and isinstance(ere, dict):
                    _b = ere.get("student_decision_authority_binding_v1")
                    if isinstance(_b, dict) and _b.get("decision_source_v1"):
                        so["decision_source_v1"] = str(_b["decision_source_v1"])
                if isinstance(ere, dict) and not ere.get("student_reasoning_fault_map_v1") and isinstance(
                    pfm, dict
                ):
                    ere["student_reasoning_fault_map_v1"] = pfm
                ulm = bool(use_llm and llm_model_resolved and base_url_resolved and not over_cap)
                _intent, _ie = build_student_execution_intent_from_sealed_output_v1(
                    student_output_v1=so,
                    job_id=str(run_id).strip(),
                    fingerprint=str(fp_emit or ""),
                    student_brain_profile_v1=brain_prof,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                    llm_model=llm_model_resolved,
                )
                from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
                    attach_fault_map_v1,
                )

                _eim = (
                    "The execution handoff could not be built from the sealed line. Check thesis, direction, and confidence for this profile."
                    if _ie
                    else (
                        "A formal execution handoff was built from the sealed student line."
                        if _intent
                        else "No execution handoff was produced for this line (this can be normal for a flat or no-trade outcome)."
                    )
                )
                _full_fm = merge_runtime_fault_nodes_v1(
                    pfm,
                    use_llm_path=ulm,
                    llm_checked_pass=bool(ulm),
                    llm_error_codes=[],
                    llm_operator_message="",
                    student_sealed_pass=True,
                    student_seal_error_codes=[],
                    student_seal_message="The student line was merged with the engine and is ready to store.",
                    execution_intent_pass=not bool(_ie),
                    execution_intent_error_codes=[str(x) for x in (_ie or [])],
                    execution_intent_message=_eim,
                )
                attach_fault_map_v1(so, _full_fm)
                emit_student_reasoning_fault_map_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                    student_reasoning_fault_map_v1=so.get("student_reasoning_fault_map_v1")
                    if isinstance(so, dict)
                    else None,
                )
                if isinstance(so, dict) and sid not in student_output_sealed_by_scenario_id_v1:
                    student_output_sealed_by_scenario_id_v1[sid] = copy.deepcopy(so)
                via = (
                    "shadow_stub_llm_cap"
                    if over_cap
                    else ("ollama" if use_llm and llm_model_resolved and base_url_resolved else "shadow_stub")
                )
                emit_student_output_sealed_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                    via=via,
                )
                if primary_trade_shadow_student_v1 is None and isinstance(so, dict):
                    primary_student_output_v1 = so
                    pr_ids = so.get("pattern_recipe_ids")
                    primary_trade_shadow_student_v1 = {
                        "scenario_id": sid,
                        "trade_id": o.trade_id,
                        "signature_key_used": sk,
                        "retrieval_slice_count": n_rx,
                        "student_decision_ref": so.get("student_decision_ref"),
                        "pattern_recipe_ids": list(pr_ids) if isinstance(pr_ids, list) else pr_ids,
                        "confidence_01": so.get("confidence_01"),
                    }
                rev, re = build_reveal_v1_from_outcome_and_student(
                    student_output=so,
                    outcome=o,
                )
                if re or rev is None:
                    errors.append(f"{sid} trade={o.trade_id}: reveal {'; '.join(re)}")
                    continue
                rid = _record_id_for_trade(run_id=run_id, scenario_id=sid, trade_id=o.trade_id)
                lr, lre = build_student_learning_record_v1_from_reveal(
                    rev,
                    run_id=run_id,
                    record_id=rid,
                    context_signature_v1=ctx_sig,
                    candle_timeframe_minutes=c_tf,
                    strategy_id=strategy_id,
                )
                if lre or lr is None:
                    errors.append(f"{sid} trade={o.trade_id}: learning_row {'; '.join(lre)}")
                    continue
                l3 = build_student_panel_l3_payload_v1(str(run_id).strip(), str(o.trade_id))
                _mem_dec, _mem_rc, gov = classify_trade_memory_promotion_v1(
                    l3_payload=l3, scorecard_entry=scorecard_entry_effective
                )
                emit_governance_decided_v1(
                    job_id=str(run_id).strip(),
                    fingerprint=fp_emit,
                    scenario_id=sid,
                    trade_id=str(o.trade_id),
                    decision=str(gov.get("decision") or ""),
                    reason_codes=list(gov.get("reason_codes") or []),
                )
                lr["learning_governance_v1"] = gov
                lr["memory_promotion_context_v1"] = build_memory_promotion_context_v1(
                    scorecard_entry=scorecard_entry_effective,
                    student_output=so,
                    trade_id=str(o.trade_id),
                )
                post_gov_errs = validate_student_learning_record_v1(lr)
                if post_gov_errs:
                    errors.append(
                        f"{sid} trade={o.trade_id}: learning_record_post_governance_invalid: "
                        f"{'; '.join(post_gov_errs)}"
                    )
                    continue
                if str(gov.get("decision") or "") == GOVERNANCE_REJECT:
                    errors.append(
                        f"{sid} trade={o.trade_id}: memory_promotion_reject: {gov.get('reason_codes')}"
                    )
                    memory_promotion_batch_trades_v1.append(
                        {"trade_id": str(o.trade_id), "learning_governance_v1": gov, "stored": False}
                    )
                    continue
                try:
                    emit_candle_timeframe_nexus_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        nexus="memory_record",
                        candle_timeframe_minutes=c_tf,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                    )
                    append_student_learning_record_v1(store, lr)
                    appended += 1
                    emit_learning_record_appended_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                        record_id=rid,
                        candle_timeframe_minutes=c_tf,
                    )
                    memory_promotion_batch_trades_v1.append(
                        {"trade_id": str(o.trade_id), "learning_governance_v1": gov, "stored": True}
                    )
                except ValueError as ve:
                    if "record_id already present" in str(ve):
                        errors.append(
                            f"{sid} trade={o.trade_id}: skip duplicate record_id "
                            f"(replay or prior append): {rid}"
                        )
                    else:
                        raise
            except ValueError as ve:
                errors.append(f"{sid} trade={o.trade_id}: {ve!r}")
            except OSError as oe:
                errors.append(f"{sid} trade={o.trade_id}: {type(oe).__name__}: {oe}")

    if trades_seen <= 0:
        emit_referee_used_student_output_batch_truth_v1(
            job_id=str(run_id).strip(),
            fingerprint=fp_emit,
            student_influence_on_worker_replay_v1="unknown",
            detail="No trades entered Student seam loop (no replay outcomes or all failed before packet).",
        )
    else:
        emit_referee_used_student_output_batch_truth_v1(
            job_id=str(run_id).strip(),
            fingerprint=fp_emit,
            student_influence_on_worker_replay_v1="false",
            detail=(
                "Referee replay completed in parallel workers before this seam; Student output and "
                "learning rows do not change recorded worker replay outcomes for this job_id."
            ),
        )

    out_fp: str | None = None
    if primary_student_output_v1 is not None:
        out_fp = _student_output_fingerprint_v1(primary_student_output_v1)

    student_emit_occurred = primary_student_output_v1 is not None
    out_audit: dict[str, Any] = {
        "schema": "student_loop_seam_audit_v1",
        "run_id": run_id,
        "student_decision_authority_mandate_enforced_v1": bool(mandate_active_v1),
        "candle_timeframe_minutes_effective_v1": int(c_tf),
        "student_learning_store_path": str(store.resolve()),
        "database_path_used": str(db.resolve()),
        "trades_considered": trades_seen,
        "student_learning_rows_appended": appended,
        "student_retrieval_matches": retrieval_matches_total,
        "student_output_fingerprint": out_fp,
        "shadow_student_enabled": True,
        "primary_trade_shadow_student_v1": primary_trade_shadow_student_v1,
        "errors": errors,
        "soft_fail": bool(errors and appended == 0 and trades_seen > 0),
        "phased_honesty_annotation_v1": _phased_honesty_annotation_v1(
            seam_attempted=True,
            student_emit_occurred=student_emit_occurred,
            trades_seen=trades_seen,
        ),
        "wiring_honesty_annotation_v1": _wiring_honesty_annotation_v1(
            seam_attempted=True,
            trades_seen=trades_seen,
            first_packet_annex_present=first_packet_annex_present,
            retrieval_matches_total=retrieval_matches_total,
        ),
        "memory_semantics_annotation_v1": _memory_semantics_annotation_v1(seam_attempted=True),
        "deliverable_vocabulary_annotation_v1": _deliverable_vocabulary_annotation_v1(seam_attempted=True),
        "llm_student_output_rejections_v1": llm_student_output_rejections_v1,
    }
    if last_external_api_l1_v1 and isinstance(last_external_api_l1_v1, dict):
        for k, v in last_external_api_l1_v1.items():
            if v is not None:
                out_audit[str(k)] = v
    if ex_req is not None:
        out_audit["student_llm_execution_v1"] = {
            "schema": "student_llm_execution_v1",
            "student_brain_profile_echo_v1": profile,
            "student_reasoning_mode_echo": profile,
            "student_llm_v1_echo": llm_meta_echo if use_llm else None,
            "prompt_version_resolved": pv if use_llm else None,
            "approved_student_llm_model_v1": STUDENT_LLM_APPROVED_MODEL_V1,
            "requested_model": requested_model_echo,
            "resolved_model": llm_model_resolved,
            "ollama_base_url_used": base_url_resolved,
            "model_resolved": llm_model_resolved,
            "base_url_resolved": base_url_resolved,
            "llm_resolution_errors_v1": llm_resolution_errs,
            "batch_student_llm_gate_failed": batch_student_llm_gate_failed,
            "ollama_any_attempt": ollama_attempts > 0,
            "ollama_trades_attempted": ollama_attempts,
            "ollama_trades_succeeded": ollama_ok,
            "llm_trade_cap": llm_cap,
            "llm_student_output_rejections_v1": llm_student_output_rejections_v1,
        }
    out_audit["learning_loop_governance_v1"] = learning_loop_governance_audit_v1(
        max_retrieval_slices_resolved=resolved_max_retrieval_slices_v1(None),
    )
    out_audit["memory_promotion_batch_v1"] = {
        "schema": "memory_promotion_batch_v1",
        "per_trade": memory_promotion_batch_trades_v1,
    }
    if student_output_sealed_by_scenario_id_v1:
        out_audit["student_output_sealed_by_scenario_id_v1"] = student_output_sealed_by_scenario_id_v1
    if primary_student_output_v1 is not None:
        out_audit["primary_student_output_sealed_v1"] = copy.deepcopy(primary_student_output_v1)
    return out_audit


__all__ = [
    "SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1",
    "SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1",
    "SCHEMA_PHASED_HONESTY_ANNOTATION_V1",
    "SCHEMA_WIRING_HONESTY_ANNOTATION_V1",
    "student_loop_seam_after_parallel_batch_v1",
]
