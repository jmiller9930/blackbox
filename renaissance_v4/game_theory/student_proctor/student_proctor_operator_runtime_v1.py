"""
Directive 09 — Operator **execution seam**: after a parallel batch, run Student packet → shadow output
→ reveal → append ``student_learning_record_v1`` for each closed trade.

* Does not import replay_runner.
* Soft-fail: per-trade errors are collected; batch Referee results remain authoritative.
* Disable with env ``PATTERN_GAME_STUDENT_LOOP_SEAM=0`` (operations kill-switch; no UI toggle required).
"""

from __future__ import annotations

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
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
    resolved_llm_for_exam_contract_v1,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import (
    emit_shadow_stub_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.student_ollama_student_output_v1 import (
    _student_llm_max_trades_v1,
    emit_student_output_via_ollama_v1,
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
    emit_governance_decided_v1,
    emit_learning_record_appended_v1,
    emit_llm_called_v1,
    emit_llm_output_received_v1,
    emit_llm_output_rejected_v1,
    emit_memory_retrieval_completed_v1,
    emit_referee_used_student_output_batch_truth_v1,
    emit_student_output_sealed_v1,
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
        "retrieval_signature_key_format_v1": "student_entry_v1:{symbol}:{entry_time}",
        "note": (
            "Learning rows match by exact context_signature_v1.signature_key only — not feature-space "
            "similarity. Do not claim ‘the same pattern again’ from Student v1 retrieval; see ARCHITECTURE "
            "§C.2. Engine context_signature_memory is a separate approximate path."
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


def _signature_key_for_trade(o: OutcomeRecord) -> str:
    """v1 **exact** lookup key for the learning store (`context_signature_v1.signature_key`)."""
    return f"student_entry_v1:{o.symbol}:{o.entry_time}"


def _record_id_for_trade(*, run_id: str, scenario_id: str, trade_id: str) -> str:
    return str(uuid.uuid5(_NS_RECORD, f"{run_id}:{scenario_id}:{trade_id}"))


def _student_output_fingerprint_v1(so: dict[str, Any]) -> str:
    canonical = json.dumps(so, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def student_loop_seam_after_parallel_batch_v1(
    *,
    results: list[dict[str, Any]],
    run_id: str,
    db_path: Path | str | None = None,
    store_path: Path | str | None = None,
    strategy_id: str | None = None,
    exam_run_contract_request_v1: dict[str, Any] | None = None,
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
    first_packet_annex_present: bool | None = None

    ex_req = exam_run_contract_request_v1 if isinstance(exam_run_contract_request_v1, dict) else None
    profile = normalize_student_reasoning_mode_v1(
        str((ex_req or {}).get("student_brain_profile_v1") or (ex_req or {}).get("student_reasoning_mode") or "")
    )
    pv = str((ex_req or {}).get("prompt_version") or "shadow_student_stub_v1").strip()[:256]
    use_llm = profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    llm_cap = _student_llm_max_trades_v1()
    llm_model_resolved: str | None = None
    base_url_resolved: str | None = None
    llm_meta_echo: dict[str, Any] = {}
    if use_llm and ex_req:
        llm_model_resolved, base_url_resolved, llm_meta_echo = resolved_llm_for_exam_contract_v1(ex_req)
    ollama_attempts = 0
    ollama_ok = 0
    llm_trade_i = 0
    llm_student_output_rejections_v1 = 0

    fp_emit = fingerprint_for_parallel_job_v1(
        operator_batch_audit=None,
        fingerprint_preview=None,
        scorecard_line=scorecard_entry_effective if isinstance(scorecard_entry_effective, dict) else None,
    )

    for row in results:
        if not row.get("ok"):
            continue
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
            sk = _signature_key_for_trade(o)
            ctx_sig = {"schema": "context_signature_v1", "signature_key": sk}
            try:
                pkt, perr = build_student_decision_packet_v1_with_cross_run_retrieval(
                    db_path=db,
                    symbol=o.symbol,
                    decision_open_time_ms=int(o.entry_time),
                    store_path=store,
                    retrieval_signature_key=sk,
                )
                if perr or pkt is None:
                    errors.append(f"{sid} trade={o.trade_id}: packet {perr!r}")
                    continue
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
                )
                so: dict[str, Any] | None = None
                soe: list[str] = []
                over_cap = False
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
                    append_student_learning_record_v1(store, lr)
                    appended += 1
                    emit_learning_record_appended_v1(
                        job_id=str(run_id).strip(),
                        fingerprint=fp_emit,
                        scenario_id=sid,
                        trade_id=str(o.trade_id),
                        record_id=rid,
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
    if ex_req is not None:
        out_audit["student_llm_execution_v1"] = {
            "schema": "student_llm_execution_v1",
            "student_brain_profile_echo_v1": profile,
            "student_reasoning_mode_echo": profile,
            "student_llm_v1_echo": llm_meta_echo if use_llm else None,
            "prompt_version_resolved": pv if use_llm else None,
            "model_resolved": llm_model_resolved,
            "base_url_resolved": base_url_resolved,
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
    return out_audit


__all__ = [
    "SCHEMA_DELIVERABLE_VOCABULARY_ANNOTATION_V1",
    "SCHEMA_MEMORY_SEMANTICS_ANNOTATION_V1",
    "SCHEMA_PHASED_HONESTY_ANNOTATION_V1",
    "SCHEMA_WIRING_HONESTY_ANNOTATION_V1",
    "student_loop_seam_after_parallel_batch_v1",
]
