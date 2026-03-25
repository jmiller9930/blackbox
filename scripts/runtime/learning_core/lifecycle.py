"""Lifecycle state machine for learning records."""

from __future__ import annotations

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"under_test"},
    "under_test": {"validated", "rejected"},
    "validated": set(),
    "rejected": set(),
}


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


def assert_valid_transition(from_state: str, to_state: str) -> None:
    if not can_transition(from_state, to_state):
        raise ValueError(f"invalid learning transition: {from_state} -> {to_state}")
