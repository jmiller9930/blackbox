"""Quantitative Evaluation Layer (QEL) — shared constants and allowed edges."""

from __future__ import annotations

from typing import FrozenSet

# Formal subsystem name (Training Architect directive).
QEL_SUBSYSTEM_NAME = "Quantitative Evaluation Layer"
QEL_ENGINE_VERSION = "1"

# Stored lifecycle states (strategy_registry.lifecycle_state).
LIFECYCLE_EXPERIMENT = "experiment"
LIFECYCLE_TEST = "test"
LIFECYCLE_CANDIDATE = "candidate"
LIFECYCLE_VALIDATED_STRATEGY = "validated_strategy"
LIFECYCLE_PROMOTION_READY = "promotion_ready"
LIFECYCLE_PROMOTED = "promoted"
LIFECYCLE_ARCHIVED = "archived"

LIFECYCLE_STATES: FrozenSet[str] = frozenset(
    {
        LIFECYCLE_EXPERIMENT,
        LIFECYCLE_TEST,
        LIFECYCLE_CANDIDATE,
        LIFECYCLE_VALIDATED_STRATEGY,
        LIFECYCLE_PROMOTION_READY,
        LIFECYCLE_PROMOTED,
        LIFECYCLE_ARCHIVED,
    }
)

# Checkpoint control output is binary only (survive | drop). No third state in DB.
DECISION_SURVIVE = "survive"
DECISION_DROP = "drop"

CHECKPOINT_DECISIONS: FrozenSet[str] = frozenset({DECISION_SURVIVE, DECISION_DROP})

# Allowed transitions: (from_state, to_state) -> requires explicit policy in lifecycle.py
# (promotion_ready → promoted) requires actor human_promotion — enforced in lifecycle.apply_transition.
HUMAN_ONLY_TRANSITIONS: FrozenSet[tuple[str, str]] = frozenset(
    {(LIFECYCLE_PROMOTION_READY, LIFECYCLE_PROMOTED)}
)

_ALLOWED: set[tuple[str | None, str]] = {
    (LIFECYCLE_EXPERIMENT, LIFECYCLE_TEST),
    (LIFECYCLE_TEST, LIFECYCLE_CANDIDATE),
    (LIFECYCLE_CANDIDATE, LIFECYCLE_VALIDATED_STRATEGY),
    (LIFECYCLE_VALIDATED_STRATEGY, LIFECYCLE_PROMOTION_READY),
    (LIFECYCLE_PROMOTION_READY, LIFECYCLE_PROMOTED),
    (LIFECYCLE_EXPERIMENT, LIFECYCLE_ARCHIVED),
    (LIFECYCLE_TEST, LIFECYCLE_ARCHIVED),
    (LIFECYCLE_CANDIDATE, LIFECYCLE_ARCHIVED),
    (LIFECYCLE_VALIDATED_STRATEGY, LIFECYCLE_ARCHIVED),
    (LIFECYCLE_PROMOTION_READY, LIFECYCLE_ARCHIVED),
    (LIFECYCLE_PROMOTED, LIFECYCLE_ARCHIVED),
}


def transition_allowed(from_state: str | None, to_state: str) -> bool:
    fs = from_state if from_state in LIFECYCLE_STATES else None
    return (fs, to_state) in _ALLOWED


def promotion_requires_human_actor(to_state: str) -> bool:
    return to_state == LIFECYCLE_PROMOTED
