"""
FinQuant — Promotion Engine

Manages status transitions for learning units. Raw observations do NOT
immediately influence decisions. A unit must earn its status.

Default thresholds (overridable via config):
  candidate     → provisional   : >= 3 total observations
  provisional   → validated     : >= 10 decided observations AND hit_rate >= 0.6
  validated     → active        : last 3 decided observations all confirmed
  any           → retired       : decided observations >= 5 AND hit_rate <= 0.35

Negative knowledge: retired status is preserved — we explicitly remember
that a pattern doesn't work in this regime so we don't relearn it.
"""

from __future__ import annotations

from typing import Any

from .learning_unit import (
    hit_rate,
    total_observations,
    update_status,
)

# Architect-spec thresholds (PPLE):
#   candidate    → provisional   : total >= 5
#   provisional  → validated     : total >= 30 AND win_rate >= 0.55 AND expectancy > 0
#   validated    → active        : recent streak of confirmed observations
#   any          → retired       : total >= 10 AND win_rate <= 0.35
DEFAULT_THRESHOLDS = {
    "candidate_to_provisional_min_observations_v1": 5,
    "provisional_to_validated_min_total_v1": 30,
    "provisional_to_validated_min_win_rate_v1": 0.55,
    "provisional_to_validated_min_expectancy_v1": 0.0,
    "validated_to_active_recent_streak_v1": 3,
    "retire_min_total_v1": 10,
    "retire_max_win_rate_v1": 0.35,
}


def evaluate_promotion(
    unit: dict[str, Any],
    *,
    recent_verdicts: list[str] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Decide whether the unit should change status.

    `recent_verdicts` is the most recent N verdicts in chronological order
    (newest last). Used for active/retired transitions.

    Returns: { "transition": True/False, "to_status": "...", "reason": "..." }
    """
    th = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    status = str(unit.get("status_v1", "candidate"))
    total = int(unit.get("total_observations_v1") or total_observations(unit))
    win_rate = float(unit.get("win_rate_v1", 0.0))
    expectancy = float(unit.get("expectancy_v1", 0.0))

    # Retire from any non-retired status if win rate collapses on enough sample
    if status != "retired":
        if total >= int(th["retire_min_total_v1"]) and win_rate <= float(th["retire_max_win_rate_v1"]):
            return {
                "transition": True,
                "to_status": "retired",
                "reason": (
                    f"win_rate={win_rate:.2f} after total={total} observations "
                    f"<= retire_threshold={th['retire_max_win_rate_v1']}"
                ),
            }

    if status == "candidate":
        if total >= int(th["candidate_to_provisional_min_observations_v1"]):
            return {
                "transition": True,
                "to_status": "provisional",
                "reason": (
                    f"observations={total} "
                    f">= {th['candidate_to_provisional_min_observations_v1']}"
                ),
            }
        return {"transition": False, "to_status": status, "reason": "not enough observations"}

    if status == "provisional":
        if (
            total >= int(th["provisional_to_validated_min_total_v1"])
            and win_rate >= float(th["provisional_to_validated_min_win_rate_v1"])
            and expectancy > float(th["provisional_to_validated_min_expectancy_v1"])
        ):
            return {
                "transition": True,
                "to_status": "validated",
                "reason": (
                    f"total={total} win_rate={win_rate:.2f} expectancy={expectancy:.4f} "
                    f"meets validated thresholds"
                ),
            }
        return {"transition": False, "to_status": status, "reason": "thresholds not yet met"}

    if status == "validated":
        recent = list(recent_verdicts or [])
        streak_n = int(th["validated_to_active_recent_streak_v1"])
        recent_decided = [v for v in recent if v in {"confirmed", "rejected"}]
        if len(recent_decided) >= streak_n and all(v == "confirmed" for v in recent_decided[-streak_n:]):
            return {
                "transition": True,
                "to_status": "active",
                "reason": f"last {streak_n} decided observations all confirmed",
            }
        return {"transition": False, "to_status": status, "reason": "no recent confirming streak"}

    if status == "active":
        return {"transition": False, "to_status": status, "reason": "already active"}

    if status == "retired":
        return {"transition": False, "to_status": status, "reason": "negative knowledge preserved"}

    return {"transition": False, "to_status": status, "reason": "no transition rule applied"}


def apply_promotion_if_needed(
    store,
    *,
    pattern_id: str,
    recent_verdicts: list[str] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper: read unit, evaluate, transition via store if needed."""
    unit = store.get_unit(pattern_id)
    if not unit:
        return {"transition": False, "to_status": None, "reason": "unit not found"}
    decision = evaluate_promotion(
        unit,
        recent_verdicts=recent_verdicts,
        thresholds=thresholds,
    )
    if decision["transition"]:
        store.transition_status(
            pattern_id=pattern_id,
            new_status=decision["to_status"],
            reason=decision["reason"],
        )
    return decision
