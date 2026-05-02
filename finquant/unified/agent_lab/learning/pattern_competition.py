"""
FinQuant — Pattern Competition

When multiple learning units match a scenario, only one wins.

Ranking:
  score = confidence * (1.0 if status == "active" else 0.6) * (1.0 if proposed_action != NO_TRADE else 0.95)

Conflict policy:
  - Only ACTIVE units can drive a decision
  - VALIDATED units may be logged as challengers but cannot drive
  - PROVISIONAL/CANDIDATE units are observation-only
  - RETIRED units explicitly suppress equivalent candidate suggestions

Returns a primary unit (or None), plus a list of challengers and suppressors.
"""

from __future__ import annotations

from typing import Any


STATUS_WEIGHT = {
    "active": 1.0,
    "validated": 0.6,
    "provisional": 0.0,
    "candidate": 0.0,
    "retired": 0.0,
}


def compute_unit_score(unit: dict[str, Any], match_quality: float = 1.0) -> float:
    """
    Architect-spec score: confidence * expectancy_multiplier * match_quality * status_weight

    expectancy_multiplier:
      - >0  → 1.0 + min(expectancy, 5.0) / 5.0   (rewards positive expectancy)
      - 0   → 0.5
      - <0  → 0.0  (negative expectancy must not drive)
    """
    confidence = float(unit.get("confidence_score_v1", 0.0))
    expectancy = float(unit.get("expectancy_v1", 0.0))
    sw = STATUS_WEIGHT.get(str(unit.get("status_v1", "")), 0.0)

    if expectancy > 0:
        exp_mult = 1.0 + min(expectancy, 5.0) / 5.0
    elif expectancy == 0:
        exp_mult = 0.5
    else:
        exp_mult = 0.0

    return confidence * exp_mult * match_quality * sw


def rank_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort units descending by spec-compliant score."""
    return sorted(units, key=compute_unit_score, reverse=True)


def select_primary(units: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the active unit with the highest score, or None."""
    actives = [u for u in units if str(u.get("status_v1", "")) == "active"]
    if not actives:
        return None
    return rank_units(actives)[0]


def resolve_competition(units: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Resolve all units matching a signature into a competition outcome.

    Returns:
      {
        "primary_unit_v1":  unit | None,           # the active driver, if any
        "challengers_v1":   [unit, ...],           # validated runners-up
        "observers_v1":     [unit, ...],           # provisional/candidate
        "suppressors_v1":   [unit, ...],           # retired (negative knowledge)
        "reason_v1":        "<plain text>"
      }
    """
    actives = [u for u in units if str(u.get("status_v1", "")) == "active"]
    validated = [u for u in units if str(u.get("status_v1", "")) == "validated"]
    provisional = [u for u in units if str(u.get("status_v1", "")) == "provisional"]
    candidate = [u for u in units if str(u.get("status_v1", "")) == "candidate"]
    retired = [u for u in units if str(u.get("status_v1", "")) == "retired"]

    primary: dict[str, Any] | None = None
    reason = "no eligible active unit"

    if actives:
        ranked_actives = rank_units(actives)
        primary = ranked_actives[0]
        reason = (
            f"primary={primary.get('pattern_id_v1')} "
            f"action={primary.get('proposed_action_v1')} "
            f"confidence={primary.get('confidence_score_v1')}"
        )

        # Negative knowledge: if a retired unit has the same proposed_action, log it
        if retired and any(r.get("proposed_action_v1") == primary.get("proposed_action_v1") for r in retired):
            reason += " (note: retired unit suggests same action — negative knowledge present)"

    return {
        "primary_unit_v1": primary,
        "challengers_v1": validated,
        "observers_v1": provisional + candidate,
        "suppressors_v1": retired,
        "reason_v1": reason,
    }
