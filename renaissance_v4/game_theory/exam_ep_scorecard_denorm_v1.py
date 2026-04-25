"""
GT_DIRECTIVE_019 — Denormalize **exam-pack grading** (E / P / pass) onto ``batch_scorecard`` lines.

Values are copied **only** from :func:`renaissance_v4.game_theory.exam_grading_service_v1.compute_exam_grade_v1`
outputs — no recomputation, no proxy substitution in this module.
"""

from __future__ import annotations

from typing import Any

from renaissance_v4.game_theory.exam_decision_frame_schema_v1 import get_committed_timeline_v1
from renaissance_v4.game_theory.exam_deliberation_capture_v1 import get_frame0_deliberation_v1
from renaissance_v4.game_theory.exam_grading_service_v1 import (
    compute_exam_grade_v1,
    get_exam_pack_grading_config_v1,
)
from renaissance_v4.game_theory.exam_state_machine_v1 import get_exam_unit_v1


def _economic_scalar_from_grade_v1(economic_result: Any) -> float | None:
    if not isinstance(economic_result, dict) or "value" not in economic_result:
        return None
    try:
        return float(economic_result["value"])
    except (TypeError, ValueError):
        return None


def merge_exam_grading_into_scorecard_record_v1(record: dict[str, Any]) -> dict[str, Any]:
    """
    When ``record`` carries ``exam_unit_id`` and exam grading is available, set:

    * ``exam_e_score_v1`` — ``economic_result["value"]`` from ``compute_exam_grade_v1``
    * ``exam_p_score_v1`` — ``process_score``
    * ``exam_pass_v1`` — ``pass``
    * ``exam_grade_audit_v1`` — grading audit blob (subset of grade payload)

    Idempotent when ``exam_e_score_v1`` is already set.
    """
    uid = str(record.get("exam_unit_id") or "").strip()
    if not uid:
        return record
    if record.get("exam_e_score_v1") is not None:
        return record

    u = get_exam_unit_v1(uid)
    if u is None:
        return record
    raw_t = get_committed_timeline_v1(uid)
    delib = get_frame0_deliberation_v1(uid)
    if raw_t is None or delib is None:
        return record
    if u.exam_pack_id is None or u.exam_pack_version is None:
        return record
    cfg = get_exam_pack_grading_config_v1(u.exam_pack_id, u.exam_pack_version)
    if cfg is None:
        return record
    try:
        grade = compute_exam_grade_v1(
            exam_unit_id=uid,
            exam_phase=u.phase,
            enter=u.enter,
            exam_pack_id=u.exam_pack_id,
            exam_pack_version=u.exam_pack_version,
            timeline_committed=raw_t,
            deliberation_export=delib,
            pack_config=cfg,
        )
    except (ValueError, TypeError):
        return record

    e_scalar = _economic_scalar_from_grade_v1(grade.get("economic_result"))
    if e_scalar is None:
        return record

    record["exam_e_score_v1"] = e_scalar
    record["exam_p_score_v1"] = float(grade["process_score"])
    record["exam_pass_v1"] = bool(grade.get("pass"))
    aud = grade.get("audit")
    if isinstance(aud, dict):
        record["exam_grade_audit_v1"] = dict(aud)
    return record


def annotate_l1_ep_value_sources_v1(record: dict[str, Any]) -> None:
    """
    Operator-visible **source** labels so L1 / UI never silently mix exam vs proxy scalars.

    Written for every **done** scorecard line (including runs without ``exam_unit_id``).
    """
    if record.get("exam_e_score_v1") is not None:
        record["l1_e_value_source_v1"] = "exam_pack_grading_v1"
    else:
        record["l1_e_value_source_v1"] = "expectancy_per_trade_proxy_v1"
    if record.get("exam_p_score_v1") is not None:
        record["l1_p_value_source_v1"] = "exam_pack_grading_v1"
    elif record.get("student_l1_process_score_v1") is not None:
        record["l1_p_value_source_v1"] = "student_l1_process_score_proxy_v1"
    else:
        record["l1_p_value_source_v1"] = "data_gap"

    sac = bool(record.get("student_controlled_execution_v1"))
    sem = str(record.get("student_execution_mode_v1") or "")
    if sac and sem == "baseline_gated":
        record["l1_execution_authority_v1"] = "baseline_gated_student"
    else:
        record["l1_execution_authority_v1"] = "baseline_control"
    sfc = str(record.get("student_full_control_v1") or "").strip()
    record["l1_student_full_control_v1"] = sfc or "not_implemented"


__all__ = [
    "annotate_l1_ep_value_sources_v1",
    "merge_exam_grading_into_scorecard_record_v1",
]
