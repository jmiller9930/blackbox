"""
FinQuant — Learning Unit

The unit of learning. Not a flat record — a falsifiable, evidence-accumulating,
status-promoted, decision-influencing entity.

A unit answers:
  "In THIS type of environment (signature), THIS action with THIS hypothesis
   has been seen N times: H confirmed, M rejected, K inconclusive,
   confidence C, status S."
"""

from __future__ import annotations

import datetime
from datetime import timezone
from typing import Any, Iterable

SCHEMA_LEARNING_UNIT = "finquant_learning_unit_v1"

VALID_STATUSES = {
    "candidate",       # 1-2 observations — never influences decisions
    "provisional",     # 3-9 observations — logged but does not gate decisions
    "validated",       # 10+ observations, hit_rate >= threshold
    "active",          # validated + recent consistency — allowed to influence
    "retired",         # negative knowledge — explicitly suppressed
}

VALID_VERDICTS = {"confirmed", "rejected", "inconclusive"}


def utc_now_iso() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_learning_unit(
    *,
    pattern_id: str,
    signature_components: dict[str, Any],
    human_label: str,
    proposed_action: str,
    hypothesis: str,
    expected_outcome: str,
    invalidation_condition: str,
    scope_notes: str = "",
) -> dict[str, Any]:
    """Construct a fresh candidate-status learning unit."""
    now = utc_now_iso()
    return {
        "schema": SCHEMA_LEARNING_UNIT,
        "pattern_id_v1": pattern_id,
        "signature_components_v1": dict(signature_components),
        "human_label_v1": human_label,
        "proposed_action_v1": proposed_action,
        "hypothesis_v1": hypothesis,
        "expected_outcome_v1": expected_outcome,
        "invalidation_condition_v1": invalidation_condition,
        "scope_notes_v1": scope_notes,

        # Evidence
        "hit_count_v1": 0,
        "miss_count_v1": 0,
        "inconclusive_count_v1": 0,
        "evidence_record_ids_v1": [],

        # Confidence
        "confidence_score_v1": 0.0,

        # Status / lifecycle
        "status_v1": "candidate",
        "first_seen_at_v1": now,
        "last_seen_at_v1": now,
        "last_status_change_at_v1": now,
        "status_history_v1": [
            {"at": now, "from": None, "to": "candidate", "reason": "initial"}
        ],

        # Negative knowledge bookkeeping
        "retired_reason_v1": None,
        "retired_at_v1": None,
    }


def record_observation(
    unit: dict[str, Any],
    *,
    verdict: str,
    evidence_record_id: str,
    note: str = "",
) -> dict[str, Any]:
    """
    Apply an observation outcome to the unit IN PLACE.

    verdict must be one of: confirmed | rejected | inconclusive
    """
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"verdict must be one of {VALID_VERDICTS}, got {verdict!r}")

    if verdict == "confirmed":
        unit["hit_count_v1"] += 1
    elif verdict == "rejected":
        unit["miss_count_v1"] += 1
    else:
        unit["inconclusive_count_v1"] += 1

    if evidence_record_id and evidence_record_id not in unit["evidence_record_ids_v1"]:
        unit["evidence_record_ids_v1"].append(evidence_record_id)

    unit["last_seen_at_v1"] = utc_now_iso()
    unit["confidence_score_v1"] = compute_confidence(unit)
    return unit


def compute_confidence(unit: dict[str, Any]) -> float:
    """
    Confidence = hit / (hit + miss), clamped, with a small-sample shrinkage.

    Inconclusive observations don't count for/against confidence but they DO
    age the unit (used by competition tie-break).
    """
    hits = int(unit.get("hit_count_v1", 0))
    misses = int(unit.get("miss_count_v1", 0))
    decided = hits + misses
    if decided == 0:
        return 0.0
    raw = hits / decided
    # Shrink toward 0.5 when sample is tiny (Wilson-style soft prior, simple form)
    shrink = max(0.0, 1.0 - (3.0 / (decided + 3.0)))
    shrunk = raw * shrink + 0.5 * (1.0 - shrink)
    return round(max(0.0, min(1.0, shrunk)), 4)


def total_observations(unit: dict[str, Any]) -> int:
    return (
        int(unit.get("hit_count_v1", 0))
        + int(unit.get("miss_count_v1", 0))
        + int(unit.get("inconclusive_count_v1", 0))
    )


def hit_rate(unit: dict[str, Any]) -> float:
    hits = int(unit.get("hit_count_v1", 0))
    misses = int(unit.get("miss_count_v1", 0))
    decided = hits + misses
    if decided == 0:
        return 0.0
    return hits / decided


def update_status(
    unit: dict[str, Any],
    *,
    new_status: str,
    reason: str,
) -> dict[str, Any]:
    """Transition a unit to a new status with audit log entry."""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {new_status!r}")
    old_status = unit.get("status_v1", "candidate")
    if old_status == new_status:
        return unit
    now = utc_now_iso()
    unit["status_v1"] = new_status
    unit["last_status_change_at_v1"] = now
    unit["status_history_v1"].append({
        "at": now,
        "from": old_status,
        "to": new_status,
        "reason": reason,
    })
    if new_status == "retired":
        unit["retired_reason_v1"] = reason
        unit["retired_at_v1"] = now
    return unit


def matches_signature(unit: dict[str, Any], pattern_id: str) -> bool:
    return str(unit.get("pattern_id_v1", "")) == str(pattern_id)


def filter_by_status(
    units: Iterable[dict[str, Any]],
    statuses: set[str],
) -> list[dict[str, Any]]:
    return [u for u in units if u.get("status_v1") in statuses]


def summarize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Compact summary for retrieval traces and operator output."""
    return {
        "pattern_id_v1": unit.get("pattern_id_v1"),
        "human_label_v1": unit.get("human_label_v1"),
        "proposed_action_v1": unit.get("proposed_action_v1"),
        "status_v1": unit.get("status_v1"),
        "hit_count_v1": unit.get("hit_count_v1", 0),
        "miss_count_v1": unit.get("miss_count_v1", 0),
        "inconclusive_count_v1": unit.get("inconclusive_count_v1", 0),
        "confidence_score_v1": unit.get("confidence_score_v1", 0.0),
        "hypothesis_v1": unit.get("hypothesis_v1", ""),
    }
