"""
GT_DIRECTIVE_017 — L3 ``data_gaps[]`` matrix: structured producer / severity / stage mapping.

Canonical response schema: ``student_panel_l3_response_v1`` (``GET /api/student-panel/run/<job_id>/l3``).
"""

from __future__ import annotations

import json
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
)
from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_panel_d13 import _ordered_parallel_rows
from renaissance_v4.game_theory.student_panel_d14 import build_student_decision_record_v1

SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1 = "student_panel_l3_response_v1"

PRODUCER_REPLAY_ENGINE = "replay_engine"
PRODUCER_STUDENT_REASONING = "student_reasoning"
PRODUCER_STUDENT_LLM = "student_llm"
PRODUCER_EXAM_DELIBERATION = "exam_deliberation"
PRODUCER_DOWNSTREAM_GENERATOR = "downstream_generator"
PRODUCER_GRADING_SERVICE = "grading_service"
PRODUCER_SCORECARD_WRITER = "scorecard_writer"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# Optional scorecard-line hints (fixtures / future denorm) drive "expected but missing" L3 rows.
_L3_FLAG_EXPECT_PROCESS_SCORE = "l3_expect_student_l1_process_score_v1"
_L3_FLAG_EXPECT_DELIBERATION = "l3_expect_exam_deliberation_on_scorecard_v1"
_L3_FLAG_EXPECT_DOWNSTREAM = "l3_expect_downstream_frames_for_enter_v1"
_L3_FLAG_EXPECT_GRADING = "l3_expect_exam_grading_on_scorecard_v1"
_L3_FLAG_UI_REFERENCES_THESIS = "l3_ui_references_thesis_fields_v1"

# Legacy string code → (field_name, producer, expected_stage, severity)
_GAP_REGISTRY: dict[str, tuple[str, str, str, str]] = {
    "batch_parallel_results_v1_missing": (
        "batch_parallel_results_v1",
        PRODUCER_REPLAY_ENGINE,
        "parallel_batch_complete",
        SEVERITY_CRITICAL,
    ),
    "decision_time_ohlc_not_in_outcome_metadata": (
        "decision_time_ohlc",
        PRODUCER_REPLAY_ENGINE,
        "replay_export",
        SEVERITY_WARNING,
    ),
    "student_confidence_01_missing": (
        "student_confidence_01",
        PRODUCER_STUDENT_REASONING,
        "student_seal",
        SEVERITY_WARNING,
    ),
    "student_store_record_missing_for_trade": (
        "student_learning_record_v1",
        PRODUCER_STUDENT_REASONING,
        "student_seam_post_reveal",
        SEVERITY_WARNING,
    ),
    "student_directional_thesis_store_missing_for_llm_profile_v1": (
        "student_output_thesis_bundle",
        PRODUCER_STUDENT_LLM,
        "student_seal",
        SEVERITY_CRITICAL,
    ),
    "student_directional_thesis_incomplete_for_llm_profile_v1": (
        "student_output_thesis_bundle",
        PRODUCER_STUDENT_LLM,
        "student_seal",
        SEVERITY_CRITICAL,
    ),
    "timeframe_not_exported": (
        "timeframe",
        PRODUCER_REPLAY_ENGINE,
        "replay_export",
        SEVERITY_INFO,
    ),
    "llm_student_output_rejected_pre_seal_v1": (
        "student_learning_record_v1",
        PRODUCER_STUDENT_LLM,
        "student_seal",
        SEVERITY_WARNING,
    ),
    "student_l1_process_score_v1_missing": (
        "student_l1_process_score_v1",
        PRODUCER_SCORECARD_WRITER,
        "scorecard_denorm",
        SEVERITY_WARNING,
    ),
    "exam_deliberation_not_on_parallel_scorecard_v1": (
        "exam_deliberation_digest",
        PRODUCER_EXAM_DELIBERATION,
        "exam_unit_api",
        SEVERITY_WARNING,
    ),
    "missing_downstream_frames_enter_parallel_v1": (
        "downstream_decision_frames",
        PRODUCER_DOWNSTREAM_GENERATOR,
        "parallel_replay_vs_exam_timeline",
        SEVERITY_WARNING,
    ),
    "missing_exam_grading_on_parallel_scorecard_v1": (
        "exam_pack_grade",
        PRODUCER_GRADING_SERVICE,
        "exam_grading",
        SEVERITY_WARNING,
    ),
    "missing_baseline_anchor_when_required_v1": (
        "cold_baseline_anchor_job_id_v1",
        PRODUCER_SCORECARD_WRITER,
        "scorecard_line_write",
        SEVERITY_WARNING,
    ),
    "non_llm_thesis_field_ui_reference_data_gap_v1": (
        "student_output_thesis_bundle",
        PRODUCER_STUDENT_REASONING,
        "student_export",
        SEVERITY_INFO,
    ),
}


def _gap_entry_v1(
    *,
    field_name: str,
    producer: str,
    reason: str,
    expected_stage: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "producer": producer,
        "reason": reason,
        "expected_stage": expected_stage,
        "severity": severity,
    }


def _registry_entry_for_code(code: str) -> tuple[str, str, str, str] | None:
    return _GAP_REGISTRY.get(code)


def _default_entry_for_unknown_code(code: str) -> dict[str, Any]:
    return _gap_entry_v1(
        field_name="unspecified_field",
        producer=PRODUCER_REPLAY_ENGINE,
        reason=code,
        expected_stage="unknown_export_stage",
        severity=SEVERITY_INFO,
    )


def build_structured_data_gaps_v1(*, legacy_codes: list[str]) -> list[dict[str, Any]]:
    """Map legacy ``data_gaps`` string codes to structured matrix rows."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in legacy_codes:
        code = str(raw).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        row = _registry_entry_for_code(code)
        if row:
            fn, prod, stage, sev = row
            out.append(
                _gap_entry_v1(
                    field_name=fn,
                    producer=prod,
                    reason=code,
                    expected_stage=stage,
                    severity=sev,
                )
            )
        else:
            out.append(_default_entry_for_unknown_code(code))
    return out


def _truthy_flag(entry: dict[str, Any] | None, key: str) -> bool:
    if not isinstance(entry, dict):
        return False
    v = entry.get(key)
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return True
    try:
        return int(v) == 1  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("reason") or ""), str(row.get("field_name") or ""))


def derive_l3_validation_data_gaps_v1(
    *,
    rec: dict[str, Any],
    entry: dict[str, Any] | None,
    replay_outcome: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Directive minimum validation rows (beyond legacy D14 string codes).

    Uses optional scorecard hints ``l3_expect_*`` for operator/fixture-driven expectations.
    """
    out: list[dict[str, Any]] = []
    entry = entry if isinstance(entry, dict) else {}

    # --- LLM rejection (no fabricated store row) --------------------------------
    job_pf = str(
        entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or ""
    ).strip()
    llm_rej = 0
    try:
        llm_rej = int(entry.get("llm_student_output_rejections_v1") or 0)
    except (TypeError, ValueError):
        llm_rej = 0
    store_missing = "student_store_record_missing_for_trade" in (rec.get("data_gaps") or [])
    if llm_rej > 0 and job_pf == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        if store_missing:
            out.append(
                _gap_entry_v1(
                    field_name="student_learning_record_v1",
                    producer=PRODUCER_STUDENT_LLM,
                    reason="llm_student_output_rejected_pre_seal_v1",
                    expected_stage="student_seal",
                    severity=SEVERITY_WARNING,
                )
            )

    # --- Optional scorecard expectation flags (tests + future denorm) ----------
    if _truthy_flag(entry, _L3_FLAG_EXPECT_PROCESS_SCORE) and entry.get("student_l1_process_score_v1") is None:
        out.append(
            _gap_entry_v1(
                field_name="student_l1_process_score_v1",
                producer=PRODUCER_SCORECARD_WRITER,
                reason="student_l1_process_score_v1_missing",
                expected_stage="scorecard_denorm",
                severity=SEVERITY_WARNING,
            )
        )

    if _truthy_flag(entry, _L3_FLAG_EXPECT_DELIBERATION) and not str(
        entry.get("exam_deliberation_digest_v1") or entry.get("exam_deliberation_capture_digest_v1") or ""
    ).strip():
        out.append(
            _gap_entry_v1(
                field_name="exam_deliberation_digest",
                producer=PRODUCER_EXAM_DELIBERATION,
                reason="exam_deliberation_not_on_parallel_scorecard_v1",
                expected_stage="exam_unit_api",
                severity=SEVERITY_WARNING,
            )
        )

    if _truthy_flag(entry, _L3_FLAG_EXPECT_DOWNSTREAM):
        sa = str(rec.get("student_action") or "").strip().upper()
        meta = replay_outcome.get("metadata") if isinstance(replay_outcome, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        has_frames = bool(
            str(meta.get("downstream_frames_digest_v1") or meta.get("downstream_frames_present_v1") or "")
            .strip()
        )
        if sa == "ENTER" and not has_frames:
            out.append(
                _gap_entry_v1(
                    field_name="downstream_decision_frames",
                    producer=PRODUCER_DOWNSTREAM_GENERATOR,
                    reason="missing_downstream_frames_enter_parallel_v1",
                    expected_stage="parallel_replay_vs_exam_timeline",
                    severity=SEVERITY_WARNING,
                )
            )

    if _truthy_flag(entry, _L3_FLAG_EXPECT_GRADING) and not str(
        entry.get("exam_pack_grade_digest_v1") or entry.get("exam_pack_grade_v1") or ""
    ).strip():
        out.append(
            _gap_entry_v1(
                field_name="exam_pack_grade",
                producer=PRODUCER_GRADING_SERVICE,
                reason="missing_exam_grading_on_parallel_scorecard_v1",
                expected_stage="exam_grading",
                severity=SEVERITY_WARNING,
            )
        )

    # --- Baseline anchor (fingerprint present, cold baseline required) ----------
    mci = entry.get("memory_context_impact_audit_v1")
    fp = ""
    if isinstance(mci, dict):
        fp = str(mci.get("run_config_fingerprint_sha256_40") or "").strip()
    anchor = str(entry.get("cold_baseline_anchor_job_id_v1") or "").strip()
    skip_cold = bool(entry.get("skip_cold_baseline"))
    if fp and not anchor and not skip_cold and job_pf != "baseline_no_memory_no_llm":
        out.append(
            _gap_entry_v1(
                field_name="cold_baseline_anchor_job_id_v1",
                producer=PRODUCER_SCORECARD_WRITER,
                reason="missing_baseline_anchor_when_required_v1",
                expected_stage="scorecard_line_write",
                severity=SEVERITY_WARNING,
            )
        )

    # --- Non-LLM profile: thesis keys optional; info if UI references them -------
    if _truthy_flag(entry, _L3_FLAG_UI_REFERENCES_THESIS) and job_pf != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        thesis_keys = (
            "student_confidence_band",
            "student_action_v1",
            "student_supporting_indicators",
            "student_conflicting_indicators",
            "student_context_fit",
            "student_invalidation_text",
            "student_reasoning_text",
        )
        for k in thesis_keys:
            v = rec.get(k)
            if v == "data_gap" or v is None:
                out.append(
                    _gap_entry_v1(
                        field_name=k,
                        producer=PRODUCER_STUDENT_REASONING,
                        reason="non_llm_thesis_field_ui_reference_data_gap_v1",
                        expected_stage="student_export",
                        severity=SEVERITY_INFO,
                    )
                )

    return out


def _merge_gap_matrices(
    a: list[dict[str, Any]],
    b: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in a + b:
        if not isinstance(row, dict):
            continue
        k = _row_key(row)
        if k in seen or not k[0]:
            continue
        seen.add(k)
        out.append(row)
    return out


def _load_replay_outcome_json_v1(
    job_id: str, trade_id: str
) -> tuple[dict[str, Any] | None, str | None]:
    entry = find_scorecard_entry_by_job_id(job_id.strip())
    if not entry:
        return None, "scorecard_entry_missing"
    batch_dir_s = entry.get("session_log_batch_dir")
    batch_dir, _scenarios, _err = build_scenario_list_for_batch(
        job_id.strip(), batch_dir_s if isinstance(batch_dir_s, str) else None
    )
    if not batch_dir or not batch_dir.is_dir():
        return None, "batch_dir_missing"
    payload = load_batch_parallel_results_v1(batch_dir)
    if not payload:
        return None, "batch_parallel_results_v1_missing"
    for row in _ordered_parallel_rows(payload):
        if not row.get("ok"):
            continue
        for oj in row.get("replay_outcomes_json") or []:
            if isinstance(oj, dict) and str(oj.get("trade_id") or "").strip() == trade_id.strip():
                return dict(oj), None
    return None, "trade_not_in_replay_outcomes"


def build_l1_linkage_v1(job_id: str, entry: dict[str, Any] | None) -> dict[str, Any]:
    mci = entry.get("memory_context_impact_audit_v1") if isinstance(entry, dict) else None
    fp = ""
    if isinstance(mci, dict):
        fp = str(mci.get("run_config_fingerprint_sha256_40") or "").strip()
    prof = ""
    llm_model = None
    if isinstance(entry, dict):
        prof = str(entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or "").strip()
        llm = entry.get("student_llm_v1")
        if isinstance(llm, dict):
            llm_model = str(llm.get("llm_model") or "").strip() or None
    return {
        "schema": "student_panel_l1_linkage_v1",
        "job_id": job_id.strip(),
        "run_config_fingerprint_sha256_40": fp or None,
        "student_brain_profile_v1": prof or None,
        "llm_model": llm_model,
    }


def build_student_panel_l3_payload_v1(job_id: str, trade_id: str) -> dict[str, Any]:
    """
    Build L3 envelope: decision record, replay subset, scorecard subset, L1 linkage, structured ``data_gaps[]``.

    **Truth:** ``data_gaps`` is always a list (possibly empty). No silent omission.
    """
    jid = job_id.strip()
    tid = trade_id.strip()
    if not jid or not tid:
        return {
            "schema": SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1,
            "ok": False,
            "error": "job_id and trade_id required",
            "job_id": jid,
            "trade_id": tid,
            "decision_record_v1": None,
            "replay_outcome_v1": None,
            "scorecard_line_v1": None,
            "decision_frames_v1": None,
            "l1_linkage_v1": build_l1_linkage_v1(jid, None),
            "data_gaps": [
                _gap_entry_v1(
                    field_name="request",
                    producer=PRODUCER_SCORECARD_WRITER,
                    reason="missing_job_or_trade_id",
                    expected_stage="l3_api",
                    severity=SEVERITY_CRITICAL,
                )
            ],
        }

    entry = find_scorecard_entry_by_job_id(jid)
    rec = build_student_decision_record_v1(jid, tid)
    replay_oj, _replay_err = _load_replay_outcome_json_v1(jid, tid)

    if rec is None:
        return {
            "schema": SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1,
            "ok": False,
            "error": "trade_not_found",
            "job_id": jid,
            "trade_id": tid,
            "decision_record_v1": None,
            "replay_outcome_v1": _replay_public_subset_v1(replay_oj) if replay_oj else None,
            "scorecard_line_v1": _scorecard_public_subset_v1(entry) if entry else None,
            "decision_frames_v1": None,
            "l1_linkage_v1": build_l1_linkage_v1(jid, entry),
            "data_gaps": [
                _gap_entry_v1(
                    field_name="student_decision_record_v1",
                    producer=PRODUCER_REPLAY_ENGINE,
                    reason="trade_not_found_or_batch_incomplete",
                    expected_stage="l3_build",
                    severity=SEVERITY_CRITICAL,
                )
            ],
        }

    legacy: list[str] = []
    if isinstance(rec, dict):
        lg = rec.get("data_gaps")
        if isinstance(lg, list):
            legacy = [str(x) for x in lg if str(x).strip()]

    structured = build_structured_data_gaps_v1(legacy_codes=legacy)
    derived = derive_l3_validation_data_gaps_v1(rec=rec, entry=entry, replay_outcome=replay_oj)
    matrix = _merge_gap_matrices(structured, derived)

    sev_rank = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

    def _sort_key(row: dict[str, Any]) -> tuple[int, str]:
        s = str(row.get("severity") or "")
        return (sev_rank.get(s, 9), str(row.get("field_name") or ""))

    matrix.sort(key=_sort_key)

    replay_public = _replay_public_subset_v1(replay_oj) if replay_oj else None

    rec_ok = True
    if isinstance(rec, dict) and rec.get("ok") is False:
        rec_ok = False

    return {
        "schema": SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1,
        "ok": rec_ok,
        "job_id": jid,
        "trade_id": tid,
        "decision_record_v1": rec,
        "replay_outcome_v1": replay_public,
        "scorecard_line_v1": _scorecard_public_subset_v1(entry),
        "decision_frames_v1": None,
        "l1_linkage_v1": build_l1_linkage_v1(jid, entry),
        "data_gaps": matrix,
    }


def _replay_public_subset_v1(oj: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "trade_id",
        "symbol",
        "direction",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "pnl",
        "mfe",
        "mae",
        "exit_reason",
        "metadata",
    )
    return {k: oj.get(k) for k in keys}


def _scorecard_public_subset_v1(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    allow = (
        "job_id",
        "status",
        "student_brain_profile_v1",
        "student_reasoning_mode",
        "student_llm_v1",
        "student_llm_execution_v1",
        "llm_student_output_rejections_v1",
        "student_learning_rows_appended",
        "student_retrieval_matches",
        "student_output_fingerprint",
        "memory_context_impact_audit_v1",
        "cold_baseline_anchor_job_id_v1",
        "skip_cold_baseline",
        "student_l1_process_score_v1",
        "session_log_batch_dir",
        "expectancy_per_trade",
        "referee_win_pct",
        _L3_FLAG_EXPECT_PROCESS_SCORE,
        _L3_FLAG_EXPECT_DELIBERATION,
        _L3_FLAG_EXPECT_DOWNSTREAM,
        _L3_FLAG_EXPECT_GRADING,
        _L3_FLAG_UI_REFERENCES_THESIS,
        "exam_deliberation_digest_v1",
        "exam_deliberation_capture_digest_v1",
        "exam_pack_grade_digest_v1",
        "exam_pack_grade_v1",
    )
    out: dict[str, Any] = {"schema": "scorecard_line_public_subset_v1"}
    for k in allow:
        if k in entry:
            out[k] = entry.get(k)
    return out


def l3_payload_to_json_bytes_v1(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


__all__ = [
    "SCHEMA_STUDENT_PANEL_L3_RESPONSE_V1",
    "PRODUCER_REPLAY_ENGINE",
    "PRODUCER_STUDENT_REASONING",
    "PRODUCER_STUDENT_LLM",
    "PRODUCER_EXAM_DELIBERATION",
    "PRODUCER_DOWNSTREAM_GENERATOR",
    "PRODUCER_GRADING_SERVICE",
    "PRODUCER_SCORECARD_WRITER",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_CRITICAL",
    "_L3_FLAG_EXPECT_PROCESS_SCORE",
    "_L3_FLAG_EXPECT_DELIBERATION",
    "_L3_FLAG_EXPECT_DOWNSTREAM",
    "_L3_FLAG_EXPECT_GRADING",
    "_L3_FLAG_UI_REFERENCES_THESIS",
    "build_l1_linkage_v1",
    "build_structured_data_gaps_v1",
    "derive_l3_validation_data_gaps_v1",
    "build_student_panel_l3_payload_v1",
]
