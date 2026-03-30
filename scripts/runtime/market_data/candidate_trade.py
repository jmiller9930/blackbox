"""Phase 5.4 — Candidate trade artifact (v1).

Typed, deterministic input shape for future Layer 3 approval. Built from
Phase 5.3 evaluation + tier-aligned selection (+ optional pre-trade gate).
No orders, no venues, no approval state machine.

Intentional nondeterminism: ``candidate_built_at`` and ``expires_at_iso`` are
supplied by the caller; wall-clock anchors are not generated inside the pure
builder unless explicitly passed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from market_data.participant_scope import ParticipantScope, validate_participant_scope
from market_data.pre_trade_fast_gate import PreTradeGateV1, TIER_SIZE_CAP
from market_data.strategy_eval import StrategyEvaluationV1
from market_data.strategy_selection import StrategySelectionV1

CANDIDATE_TRADE_VERSION = "candidate_trade_v1"

VALID_SIDES = frozenset({"long", "short"})


@dataclass(frozen=True)
class CandidateTradeV1:
    """Participant-scoped trade candidate for Layer 3 (approval) consumption."""

    participant_scope: ParticipantScope
    symbol: str
    side: str
    notional_fraction: float
    tier_risk_cap_fraction: float
    strategy_profile: str
    strategy_version: str
    selection_version: str
    evaluation_outcome: str
    selection_outcome: str
    gate_outcome: str | None
    expires_at_iso: str
    source_evaluated_at: str
    source_selected_at: str
    source_gated_at: str | None
    candidate_built_at: str
    schema_version: str = CANDIDATE_TRADE_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["participant_scope"] = self.participant_scope.to_dict()
        return d


def _scope_aligned(a: ParticipantScope, b: ParticipantScope) -> bool:
    return (
        a.participant_id == b.participant_id
        and a.participant_type == b.participant_type
        and a.account_id == b.account_id
        and a.wallet_context == b.wallet_context
        and a.risk_tier == b.risk_tier
        and a.interaction_path == b.interaction_path
    )


def _outcome_to_side(evaluation_outcome: str) -> str:
    if evaluation_outcome == "long_bias":
        return "long"
    if evaluation_outcome == "short_bias":
        return "short"
    raise ValueError(f"candidate_trade_invalid_evaluation_outcome:{evaluation_outcome}")


def validate_candidate_trade_v1(c: CandidateTradeV1) -> None:
    """Enforce required fields and risk envelope vs tier cap (no tier mutation)."""
    validate_participant_scope(c.participant_scope)
    if c.side not in VALID_SIDES:
        raise ValueError(f"candidate_trade_invalid_side:{c.side}")
    if not str(c.expires_at_iso or "").strip():
        raise ValueError("candidate_trade_missing_expires_at_iso")
    if not str(c.strategy_profile or "").strip():
        raise ValueError("candidate_trade_missing_strategy_profile")
    tier = c.participant_scope.risk_tier
    cap = TIER_SIZE_CAP.get(tier)
    if cap is None:
        raise ValueError(f"candidate_trade_unknown_tier:{tier}")
    if c.tier_risk_cap_fraction != cap:
        raise ValueError("candidate_trade_tier_cap_snapshot_mismatch")
    if c.notional_fraction <= 0 or c.notional_fraction > c.tier_risk_cap_fraction + 1e-12:
        raise ValueError(
            f"candidate_trade_notional_out_of_envelope:{c.notional_fraction}>{c.tier_risk_cap_fraction}"
        )


def build_candidate_trade_v1(
    evaluation: StrategyEvaluationV1,
    selection: StrategySelectionV1,
    *,
    gate: PreTradeGateV1 | None = None,
    expires_at_iso: str,
    candidate_built_at: str,
    notional_fraction: float | None = None,
) -> CandidateTradeV1:
    """Build a v1 candidate from validated 5.3 artifacts.

    **Required inputs:** ``evaluation``, ``selection`` with
    ``selection_outcome == \"selected\"``, ``evaluation.error is None``, aligned
    symbol and participant scope, and consistent ``risk_tier`` (no escalation).

    **Size:** If ``gate`` is provided, ``notional_fraction`` defaults to
    ``gate.capped_size_fraction``. Otherwise pass ``notional_fraction`` explicitly
    (must be > 0 and ≤ tier risk cap).

    **Expiry:** Caller supplies ``expires_at_iso`` (approval / validity window).
    """
    if evaluation.error is not None:
        raise ValueError("candidate_trade_evaluation_has_error")
    if selection.selection_outcome != "selected":
        raise ValueError(f"candidate_trade_selection_not_selected:{selection.selection_outcome}")
    if selection.selected_strategy_profile is None:
        raise ValueError("candidate_trade_missing_strategy_profile_on_selection")
    if evaluation.symbol != selection.symbol:
        raise ValueError("candidate_trade_symbol_mismatch")
    if not _scope_aligned(evaluation.participant_scope, selection.participant_scope):
        raise ValueError("candidate_trade_participant_scope_mismatch")
    if selection.selected_risk_tier != evaluation.participant_scope.risk_tier:
        raise ValueError("candidate_trade_tier_mutation_or_mismatch")

    scope = evaluation.participant_scope
    tier = scope.risk_tier
    tier_cap = TIER_SIZE_CAP.get(tier)
    if tier_cap is None:
        raise ValueError(f"candidate_trade_unknown_tier:{tier}")

    if gate is not None:
        if gate.participant_scope.risk_tier != tier:
            raise ValueError("candidate_trade_gate_tier_mutation")
        if gate.symbol != evaluation.symbol:
            raise ValueError("candidate_trade_gate_symbol_mismatch")
        nf = notional_fraction if notional_fraction is not None else gate.capped_size_fraction
    else:
        if notional_fraction is None:
            raise ValueError("candidate_trade_notional_required_without_gate")
        nf = notional_fraction

    if nf <= 0 or nf > tier_cap + 1e-12:
        raise ValueError(f"candidate_trade_notional_out_of_envelope:{nf}>{tier_cap}")

    side = _outcome_to_side(evaluation.evaluation_outcome)

    c = CandidateTradeV1(
        participant_scope=scope,
        symbol=evaluation.symbol,
        side=side,
        notional_fraction=float(nf),
        tier_risk_cap_fraction=float(tier_cap),
        strategy_profile=selection.selected_strategy_profile,
        strategy_version=evaluation.strategy_version,
        selection_version=selection.selection_version,
        evaluation_outcome=evaluation.evaluation_outcome,
        selection_outcome=selection.selection_outcome,
        gate_outcome=gate.gate_outcome if gate else None,
        expires_at_iso=expires_at_iso.strip(),
        source_evaluated_at=evaluation.evaluated_at,
        source_selected_at=selection.selected_at,
        source_gated_at=gate.gated_at if gate else None,
        candidate_built_at=candidate_built_at.strip(),
    )
    validate_candidate_trade_v1(c)
    return c
