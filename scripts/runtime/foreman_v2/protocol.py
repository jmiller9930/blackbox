from __future__ import annotations

from dataclasses import dataclass, field


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
    artifact_missing: list[str] = field(default_factory=list)


def decide_state(
    *,
    directive_closed: bool,
    has_proof: bool,
    developer_handoff_back: bool,
    last_state: str,
    architect_verdict: str = "missing",
    architect_rejection_count: int = 0,
    architect_outcome: str = "missing",
    developer_artifact_gate_passed: bool = True,
    developer_artifact_missing: list[str] | None = None,
    architect_artifact_gate_passed: bool = True,
    architect_artifact_missing: list[str] | None = None,
) -> TransitionDecision:
    if architect_rejection_count >= 3:
        if architect_outcome in {"rejected", "blocked", "deferred", "closed_without_completion"}:
            return TransitionDecision(
                next_state="closed",
                next_actor="none",
                required_phrase="issue the next directive",
                reason=f"three_strikes_closed:{architect_outcome}",
            )
        return TransitionDecision(
            next_state="architect_action_required",
            next_actor="architect",
            required_phrase="have cursor validate shared-docs",
            reason="three_strikes_architect_closeout_required",
        )
    if architect_verdict == "not_met":
        return TransitionDecision(
            next_state="architect_action_required",
            next_actor="architect",
            required_phrase="have cursor validate shared-docs",
            reason="architect_not_met_remediation_required",
        )
    if directive_closed and architect_verdict == "met":
        if not architect_artifact_gate_passed:
            return TransitionDecision(
                next_state="architect_action_required",
                next_actor="architect",
                required_phrase="have cursor validate shared-docs",
                reason="architect_artifact_gate_failed_before_close",
                artifact_missing=architect_artifact_missing or [],
            )
        return TransitionDecision(
            next_state="closed",
            next_actor="none",
            required_phrase="issue the next directive",
            reason="directive_closed",
        )
    if directive_closed and architect_verdict != "met":
        return TransitionDecision(
            next_state="architect_action_required",
            next_actor="architect",
            required_phrase="have cursor validate shared-docs",
            reason="directive_closed_without_architect_met",
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
        if not developer_artifact_gate_passed:
            return TransitionDecision(
                next_state="developer_active",
                next_actor="developer",
                required_phrase="have the architect validate shared-docs",
                reason="developer_artifact_gate_failed",
                artifact_missing=developer_artifact_missing or [],
            )
        if architect_verdict == "met":
            if not architect_artifact_gate_passed:
                return TransitionDecision(
                    next_state="architect_action_required",
                    next_actor="architect",
                    required_phrase="have cursor validate shared-docs",
                    reason="architect_artifact_gate_failed",
                    artifact_missing=architect_artifact_missing or [],
                )
            return TransitionDecision(
                next_state="architect_validating",
                next_actor="architect",
                required_phrase="have cursor validate shared-docs",
                reason="architect_met_pending_directive_reconcile",
            )
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

