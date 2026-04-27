"""
Governed Student Decision Authority (GT — student_decision_authority_v1).

**Shadow mode (default):** computes the override that *would* apply under rules, emits trace, does **not**
mutate ``entry_reasoning_eval_v1``.

**Active mode:** when ``PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1=active`` and all gates pass, patches
``decision_synthesis_v1`` + ``confidence_01`` on the sealed entry reasoning dict **before** LLM / seal merge.

**Follow-up gap (not v1):** governed **lifecycle exit** authority (timing / exit code) — entry-only rules
today; lifecycle exits remain in ``lifecycle_reasoning_engine_v1`` without this layer.

Env:

* ``PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1`` — ``shadow`` (default) | ``active`` | ``off``
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.student_proctor.lifecycle_deterministic_learning_026c_v1 import (
    FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C,
)

SCHEMA_STUDENT_DECISION_AUTHORITY_V1 = "student_decision_authority_v1"
SCHEMA_STUDENT_DECISION_AUTHORITY_BINDING_V1 = "student_decision_authority_binding_v1"
CONTRACT_VERSION = 1
DECISION_SOURCE_REASONING_MODEL_V1 = "reasoning_model"

# Tunable thresholds (deterministic; documented for operators).
_SUPPRESS_ENTRY_MAX_SCORE_01 = 0.42
_PROMOTE_ENTRY_MIN_SCORE_01 = 0.88


def student_brain_profile_requires_decision_authority_mandate_v1(student_brain_profile_v1: str | None) -> bool:
    """Non-baseline Student profiles must run ``student_decision_authority_v1`` with persisted trace (no bypass)."""
    from renaissance_v4.game_theory.exam_run_contract_v1 import (
        STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
        normalize_student_reasoning_mode_v1,
    )

    p = normalize_student_reasoning_mode_v1(str(student_brain_profile_v1 or "").strip() or None)
    return p != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1


def validate_student_decision_authority_mandate_preconditions_v1(
    *,
    exam_run_contract_request_v1: dict[str, Any] | None,
    job_id: str,
    student_brain_profile_v1: str,
    student_llm_gate_blocked_batch_v1: bool = False,
) -> list[str]:
    """
    Returns human-readable errors; empty list means mandate preconditions satisfied for this batch.

    Call once before the Student seam trade loop when profile is non-baseline.
    """
    if not student_brain_profile_requires_decision_authority_mandate_v1(student_brain_profile_v1):
        return []
    errs: list[str] = []
    if not str(job_id or "").strip():
        errs.append(
            "STUDENT_DECISION_AUTHORITY_MANDATE_V1: job_id is required so student_decision_authority_v1 can persist per trade."
        )
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import learning_trace_instrumentation_enabled_v1

    if not learning_trace_instrumentation_enabled_v1():
        errs.append(
            "STUDENT_DECISION_AUTHORITY_MANDATE_V1: learning trace instrumentation is disabled "
            "(PATTERN_GAME_LEARNING_TRACE_EVENTS) — Student mode cannot prove authority; refuse seam."
        )
    if student_decision_authority_mode_v1(exam_run_contract_request_v1) == "off":
        errs.append(
            "STUDENT_DECISION_AUTHORITY_MANDATE_V1: authority mode is off (contract or env) — "
            "non-baseline Student runs must use shadow or active."
        )
    if student_llm_gate_blocked_batch_v1:
        errs.append(
            "STUDENT_DECISION_AUTHORITY_MANDATE_V1: LLM profile batch gate failed — no sealed Student lines "
            "can be produced; fix Ollama config before running Student mode."
        )
    return errs


def student_decision_authority_mode_v1(exam_run_contract_request_v1: dict[str, Any] | None = None) -> str:
    if isinstance(exam_run_contract_request_v1, dict):
        ov = str(exam_run_contract_request_v1.get("student_decision_authority_mode_v1") or "").strip().lower()
        if ov in ("active", "shadow", "off"):
            return ov
    v = (os.environ.get("PATTERN_GAME_STUDENT_DECISION_AUTHORITY_V1") or "shadow").strip().lower()
    if v in ("active", "on", "true", "1"):
        return "active"
    if v in ("off", "0", "false", "no"):
        return "off"
    return "shadow"


def _decision_snapshot_v1(ere: dict[str, Any]) -> dict[str, Any]:
    ds = ere.get("decision_synthesis_v1") if isinstance(ere.get("decision_synthesis_v1"), dict) else {}
    act = str(ds.get("action") or "no_trade").strip().lower()
    return {
        "decision_action_v1": act,
        "confidence_01": float(ere.get("confidence_01") or 0.5),
    }


def _router_decision_summary_v1(ere: dict[str, Any], *, unified_router_enabled: bool) -> dict[str, Any]:
    d = ere.get("reasoning_router_decision_v1")
    if not isinstance(d, dict):
        return {
            "router_evaluated_v1": False,
            "final_route_v1": None,
            "unified_router_enabled_v1": bool(unified_router_enabled),
            "note_v1": "No reasoning_router_decision_v1 on entry_reasoning_eval_v1 (router off or not emitted).",
        }
    return {
        "router_evaluated_v1": True,
        "unified_router_enabled_v1": bool(unified_router_enabled),
        "final_route_v1": d.get("final_route_v1"),
        "escalation_decision_v1": d.get("escalation_decision_v1"),
        "schema": d.get("schema"),
    }


def _026c_record_ids(pkt: dict[str, Any]) -> list[str]:
    raw = pkt.get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C) if isinstance(pkt, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        rid = str(x.get("record_id_026c") or "").strip()
        if rid:
            out.append(rid)
    return out


def _026c_scores(pkt: dict[str, Any]) -> list[float]:
    raw = pkt.get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C) if isinstance(pkt, dict) else None
    if not isinstance(raw, list):
        return []
    s: list[float] = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        v = x.get("overall_score_01")
        if isinstance(v, (int, float)):
            s.append(float(v))
    return s


def _side_from_pattern_key_v1(pk: str | None) -> str | None:
    if not pk or not isinstance(pk, str):
        return None
    parts = pk.split(":")
    if len(parts) >= 3:
        side = str(parts[2]).strip().lower()
        if side in ("long", "short"):
            return side
    return None


def _referee_safety_check_v1(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
    ere: dict[str, Any],
    would_apply: bool,
) -> dict[str, Any]:
    """v1 symbolic safety — blocks impossible transitions only."""
    blocks: list[str] = []
    aa = str(after.get("decision_action_v1") or "")
    if aa not in ("no_trade", "enter_long", "enter_short", ""):
        blocks.append("invalid_after_action_v1")
    if would_apply and str(before.get("decision_action_v1") or "") == str(after.get("decision_action_v1") or ""):
        blocks.append("no_material_change_v1")
    passed = len(blocks) == 0
    return {
        "schema": "referee_safety_check_v1",
        "contract_version": 1,
        "passed_v1": passed,
        "blocks_v1": blocks,
        "notes_v1": "Symbolic v1 gate: valid action set; before!=after only when would_apply.",
        "digest_echo_v1": str((ere.get("entry_reasoning_eval_digest_v1") or ""))[:16] or None,
    }


def compute_student_decision_authority_payload_v1(
    *,
    ere: dict[str, Any],
    pkt: dict[str, Any],
    unified_router_enabled: bool,
    exam_run_contract_request_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Pure computation — returns ``student_decision_authority_v1`` evidence document (no I/O).
    """
    mode = student_decision_authority_mode_v1(exam_run_contract_request_v1)
    before = _decision_snapshot_v1(ere)
    rec_ids = _026c_record_ids(pkt)
    scores = _026c_scores(pkt)
    router_sum = _router_decision_summary_v1(ere, unified_router_enabled=unified_router_enabled)

    after = copy.deepcopy(before)
    reason_codes: list[str] = []
    action = "maintain_v1"
    would = False

    ba = before["decision_action_v1"]
    min_sc = min(scores) if scores else None
    max_sc = max(scores) if scores else None

    raw = pkt.get(FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C) if isinstance(pkt, dict) else None
    has026 = isinstance(raw, list) and len(raw) > 0

    if mode == "off":
        reason_codes.append("authority_mode_off_v1")
    elif has026 and ba in ("enter_long", "enter_short") and min_sc is not None and min_sc < _SUPPRESS_ENTRY_MAX_SCORE_01:
        after["decision_action_v1"] = "no_trade"
        action = "shadow_suppress_entry_026c_weak_evidence_v1"
        reason_codes.append("026c_retrieved_min_score_below_suppress_threshold_v1")
        would = True
    elif has026 and ba == "no_trade" and max_sc is not None and max_sc >= _PROMOTE_ENTRY_MIN_SCORE_01:
        pk0 = None
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            pk0 = raw[0].get("pattern_key_026c_v1")
        side = _side_from_pattern_key_v1(str(pk0) if pk0 else "") or "long"
        after["decision_action_v1"] = f"enter_{side}"
        after["confidence_01"] = max(float(before.get("confidence_01") or 0.5), 0.55)
        action = "shadow_promote_entry_026c_strong_evidence_v1"
        reason_codes.append("026c_retrieved_max_score_above_promote_threshold_v1")
        would = True
    else:
        action = "maintain_v1"
        if not has026:
            reason_codes.append("no_026c_retrieval_slices_v1")
        else:
            reason_codes.append("026c_scores_within_no_override_band_v1")

    if mode == "active" and would and unified_router_enabled and not isinstance(
        ere.get("reasoning_router_decision_v1"), dict
    ):
        would = False
        after = copy.deepcopy(before)
        action = "maintain_v1"
        reason_codes.append("active_requires_router_decision_when_router_enabled_v1")

    safety = _referee_safety_check_v1(before=before, after=after, ere=ere, would_apply=would)
    if would and not safety["passed_v1"]:
        would = False
        after = copy.deepcopy(before)
        action = "maintain_v1"
        reason_codes.append("safety_blocked_would_apply_v1")
        safety = _referee_safety_check_v1(before=before, after=after, ere=ere, would_apply=False)

    return {
        "schema": SCHEMA_STUDENT_DECISION_AUTHORITY_V1,
        "contract_version": CONTRACT_VERSION,
        "authority_mode_v1": mode,
        "authority_applied_v1": False,
        "authority_would_apply_v1": bool(would),
        "authority_action_v1": action,
        "authority_reason_codes_v1": reason_codes,
        "before_decision_snapshot_v1": before,
        "after_decision_snapshot_v1": after,
        "referee_safety_check_v1": safety,
        "retrieved_026c_record_ids_v1": rec_ids,
        "router_decision_summary_v1": router_sum,
    }


def maybe_apply_student_decision_authority_to_ere_v1(
    *,
    ere: dict[str, Any],
    payload: dict[str, Any],
    exam_run_contract_request_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Mutates ``ere`` in place when mode is **active** and payload says would_apply after final safety.
    Returns the payload with ``authority_applied_v1`` updated.
    """
    if student_decision_authority_mode_v1(exam_run_contract_request_v1) != "active":
        return payload
    if not payload.get("authority_would_apply_v1"):
        return payload
    if not (payload.get("referee_safety_check_v1") or {}).get("passed_v1"):
        return payload
    out = copy.deepcopy(payload)
    snap = out.get("after_decision_snapshot_v1")
    if not isinstance(snap, dict):
        return payload
    ds = ere.setdefault("decision_synthesis_v1", {})
    if not isinstance(ds, dict):
        ere["decision_synthesis_v1"] = {}
        ds = ere["decision_synthesis_v1"]
    ds["action"] = str(snap.get("decision_action_v1") or "no_trade")
    if "confidence_01" in snap:
        ere["confidence_01"] = float(snap["confidence_01"])
    out["authority_applied_v1"] = True
    out["authority_mode_v1"] = "active"
    return out


def run_student_decision_authority_for_trade_v1(
    *,
    job_id: str,
    fingerprint: str | None,
    scenario_id: str,
    trade_id: str,
    ere: dict[str, Any],
    pkt: dict[str, Any],
    unified_router_enabled: bool,
    exam_run_contract_request_v1: dict[str, Any] | None = None,
    mandate_active_v1: bool = False,
) -> dict[str, Any]:
    """
    Compute authority, optionally patch ``ere`` (active), emit learning trace.
    Call after entry reasoning (+ optional lifecycle) is attached to ``ere``.

    When ``mandate_active_v1`` is True (non-baseline Student mode), a persisted trace line is
    **required**; otherwise raises ``RuntimeError``. On success, sets ``ere["student_decision_authority_binding_v1"]``.
    """
    if student_decision_authority_mode_v1(exam_run_contract_request_v1) == "off":
        return {
            "schema": SCHEMA_STUDENT_DECISION_AUTHORITY_V1,
            "contract_version": CONTRACT_VERSION,
            "authority_mode_v1": "off",
            "authority_skipped_v1": True,
        }
    pl = compute_student_decision_authority_payload_v1(
        ere=ere,
        pkt=pkt,
        unified_router_enabled=unified_router_enabled,
        exam_run_contract_request_v1=exam_run_contract_request_v1,
    )
    pl2 = maybe_apply_student_decision_authority_to_ere_v1(
        ere=ere, payload=pl, exam_run_contract_request_v1=exam_run_contract_request_v1
    )
    trace_emitted = False
    if str(job_id or "").strip():
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
            emit_student_decision_authority_v1,
        )

        trace_emitted = bool(
            emit_student_decision_authority_v1(
                job_id=str(job_id).strip(),
                fingerprint=fingerprint,
                scenario_id=scenario_id,
                trade_id=trade_id,
                payload=pl2,
            )
        )
    if mandate_active_v1:
        if not trace_emitted:
            raise RuntimeError(
                "STUDENT_DECISION_AUTHORITY_MANDATE_V1: student_decision_authority_v1 event was not persisted "
                "(empty job_id, learning trace disabled, or append failure). Student mode is invalid without trace proof."
            )
        if isinstance(ere, dict):
            ere["student_decision_authority_binding_v1"] = {
                "schema": SCHEMA_STUDENT_DECISION_AUTHORITY_BINDING_V1,
                "contract_version": CONTRACT_VERSION,
                "job_id": str(job_id).strip(),
                "scenario_id": str(scenario_id),
                "trade_id": str(trade_id),
                "decision_source_v1": DECISION_SOURCE_REASONING_MODEL_V1,
                "learning_trace_persisted_v1": True,
            }
    return pl2


def count_student_decision_authority_trace_lines_v1(
    job_id: str,
    *,
    path: Path | None = None,
) -> int:
    """Count persisted ``student_decision_authority_v1`` stages for ``job_id`` (optional custom JSONL path)."""
    from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1

    jid = str(job_id or "").strip()
    if not jid:
        return 0
    evs = read_learning_trace_events_for_job_v1(jid, path=path)
    return sum(1 for e in evs if str(e.get("stage") or "") == "student_decision_authority_v1")


__all__ = [
    "CONTRACT_VERSION",
    "DECISION_SOURCE_REASONING_MODEL_V1",
    "SCHEMA_STUDENT_DECISION_AUTHORITY_BINDING_V1",
    "SCHEMA_STUDENT_DECISION_AUTHORITY_V1",
    "compute_student_decision_authority_payload_v1",
    "count_student_decision_authority_trace_lines_v1",
    "maybe_apply_student_decision_authority_to_ere_v1",
    "run_student_decision_authority_for_trade_v1",
    "student_brain_profile_requires_decision_authority_mandate_v1",
    "student_decision_authority_mode_v1",
    "validate_student_decision_authority_mandate_preconditions_v1",
]
