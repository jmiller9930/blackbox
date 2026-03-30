"""Participant-scoped consumption contract for Phase 5 market data reads.

Every market data consumer must present a valid ParticipantScope.  This contract
carries the Phase 5 identity fields required for downstream strategy, approval,
and audit artifacts.  The ``risk_tier`` field is operator-owned state — Anna must
not assign, escalate, or modify it.

Field definitions from docs/architect/development_plan.md §5.0:
  participant_id    — unique participant identifier
  participant_type  — "human" or "bot" (Phase 4.2 alignment)
  account_id        — logical trading account (Phase 4.2 — not a single wallet)
  wallet_context    — account/wallet context for operations
  risk_tier         — human-selected tier (tier_1 / tier_2 / tier_3)
  interaction_path  — how the participant interacts (e.g. "telegram", "api", "cli")
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

VALID_RISK_TIERS = frozenset({"tier_1", "tier_2", "tier_3"})
VALID_PARTICIPANT_TYPES = frozenset({"human", "bot"})

REQUIRED_FIELDS = (
    "participant_id",
    "participant_type",
    "account_id",
    "wallet_context",
    "risk_tier",
    "interaction_path",
)


@dataclass(frozen=True)
class ParticipantScope:
    """Immutable participant scope for market data consumption contracts.

    Aligned with Phase 4.2 wallet/account architecture and Phase 5.0 identity model.
    risk_tier is validated but never assigned by this layer — operator-owned only.
    """

    participant_id: str
    participant_type: str
    account_id: str
    wallet_context: str
    risk_tier: str
    interaction_path: str
    schema_version: str = "participant_scope_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_participant_scope(scope: ParticipantScope) -> None:
    """Validate all required fields deterministically.  Raises ValueError on failure."""
    missing = [
        name
        for name in REQUIRED_FIELDS
        if not str(getattr(scope, name, "") or "").strip()
    ]
    if missing:
        raise ValueError(f"participant_scope_missing_fields:{','.join(missing)}")

    if scope.participant_type not in VALID_PARTICIPANT_TYPES:
        raise ValueError(
            f"participant_scope_invalid_type:{scope.participant_type}"
            f" (valid: {', '.join(sorted(VALID_PARTICIPANT_TYPES))})"
        )

    if scope.risk_tier not in VALID_RISK_TIERS:
        raise ValueError(
            f"participant_scope_invalid_risk_tier:{scope.risk_tier}"
            f" (valid: {', '.join(sorted(VALID_RISK_TIERS))})"
        )
