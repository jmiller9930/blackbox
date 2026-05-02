"""
FinQuant — Decision Explainer

At decision time, every decision must be explainable in terms of:
  - what learning units were retrieved
  - which one (if any) drove the decision
  - what the evidence behind that unit looked like
  - what alternatives existed
  - what was suppressed (negative knowledge)

This is what separates a learning system from "a black box with logs."
"""

from __future__ import annotations

from typing import Any

from .learning_unit import summarize_unit


def build_decision_explanation(
    *,
    pattern_id: str,
    human_label: str,
    competition: dict[str, Any],
    final_action: str,
    final_decision_source: str,
) -> dict[str, Any]:
    """
    Build a structured explanation for one lifecycle decision.

    Returns a dict suitable for embedding in the decision trace.
    """
    primary = competition.get("primary_unit_v1")
    challengers = competition.get("challengers_v1") or []
    observers = competition.get("observers_v1") or []
    suppressors = competition.get("suppressors_v1") or []

    if primary:
        primary_summary = summarize_unit(primary)
        attributable = primary.get("proposed_action_v1") == final_action
        narrative = _narrate_with_primary(primary, final_action, attributable)
    else:
        primary_summary = None
        attributable = False
        narrative = _narrate_without_primary(
            pattern_id=pattern_id,
            human_label=human_label,
            observer_count=len(observers),
            suppressor_count=len(suppressors),
            final_decision_source=final_decision_source,
        )

    return {
        "schema": "finquant_decision_explanation_v1",
        "pattern_id_v1": pattern_id,
        "human_label_v1": human_label,
        "primary_unit_v1": primary_summary,
        "primary_attributable_v1": attributable,
        "challenger_units_v1": [summarize_unit(u) for u in challengers],
        "observer_unit_count_v1": len(observers),
        "suppressor_units_v1": [summarize_unit(u) for u in suppressors],
        "competition_reason_v1": competition.get("reason_v1", ""),
        "final_action_v1": final_action,
        "final_decision_source_v1": final_decision_source,
        "narrative_v1": narrative,
    }


def _narrate_with_primary(primary: dict[str, Any], final_action: str, attributable: bool) -> str:
    label = str(primary.get("human_label_v1", "?"))
    proposed = str(primary.get("proposed_action_v1", "?"))
    confidence = float(primary.get("confidence_score_v1", 0.0))
    hits = int(primary.get("hit_count_v1", 0))
    misses = int(primary.get("miss_count_v1", 0))
    if attributable:
        return (
            f"Active learning unit matched [{label}]. "
            f"It proposed {proposed} with confidence {confidence:.2f} "
            f"based on {hits} confirmed and {misses} rejected prior observations. "
            f"The student followed the unit's proposal."
        )
    return (
        f"Active learning unit matched [{label}] proposing {proposed} "
        f"(confidence {confidence:.2f}, hits={hits}, misses={misses}), "
        f"but the student chose {final_action} instead. "
        f"The unit was logged but not followed."
    )


def _narrate_without_primary(
    *,
    pattern_id: str,
    human_label: str,
    observer_count: int,
    suppressor_count: int,
    final_decision_source: str,
) -> str:
    parts = [
        f"No ACTIVE learning unit matched signature [{human_label}] (id={pattern_id})."
    ]
    if observer_count > 0:
        parts.append(
            f"{observer_count} candidate/provisional unit(s) were observing — they cannot drive decisions yet."
        )
    if suppressor_count > 0:
        parts.append(
            f"{suppressor_count} retired unit(s) for this signature represent negative knowledge."
        )
    parts.append(
        f"The decision was driven by source={final_decision_source}, not by validated learning."
    )
    return " ".join(parts)
