from __future__ import annotations

from dataclasses import dataclass


VALID_STATES = {
    "idle",
    "developer_action_required",
    "developer_active",
    "architect_action_required",
    "architect_validating",
    "closed",
    "sync_conflict",
}


@dataclass(frozen=True)
class TransitionDecision:
    next_state: str
    next_actor: str
    required_phrase: str
    reason: str


def decide_state(
    *,
    directive_closed: bool,
    has_proof: bool,
    developer_handoff_back: bool,
    last_state: str,
) -> TransitionDecision:
    if directive_closed:
        return TransitionDecision(
            next_state="closed",
            next_actor="none",
            required_phrase="issue the next directive",
            reason="directive_closed",
        )
    if not has_proof:
        # Developer lane remains active until proof lands.
        if last_state in {"developer_active", "developer_action_required"}:
            return TransitionDecision(
                next_state="developer_active",
                next_actor="developer",
                required_phrase="have the architect validate shared-docs",
                reason="developer_work_in_progress",
            )
        return TransitionDecision(
            next_state="developer_action_required",
            next_actor="developer",
            required_phrase="have the architect validate shared-docs",
            reason="proof_missing",
        )
    if has_proof and not developer_handoff_back:
        return TransitionDecision(
            next_state="developer_active",
            next_actor="developer",
            required_phrase="have the architect validate shared-docs",
            reason="proof_present_but_handoff_missing",
        )
    if has_proof and developer_handoff_back:
        if last_state == "architect_validating":
            return TransitionDecision(
                next_state="architect_validating",
                next_actor="architect",
                required_phrase="have cursor validate shared-docs",
                reason="awaiting_architect_validation",
            )
        return TransitionDecision(
            next_state="architect_action_required",
            next_actor="architect",
            required_phrase="have cursor validate shared-docs",
            reason="proof_ready_for_architect",
        )
    return TransitionDecision(
        next_state="sync_conflict",
        next_actor="none",
        required_phrase="resolve conflict",
        reason="unhandled_transition",
    )

